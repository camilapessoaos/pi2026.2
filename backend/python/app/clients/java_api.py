from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

from app.config import Settings
from app.errors import ServiceError
from app.models import NormalizedReading


# A API Java aceita no máximo 1000 leituras por lote (@Size(max = 1000)); usamos lotes menores.
INGEST_BATCH_SIZE = 500


class JavaApiClient:
    """Conecta com a API Java; não acessa nem conhece o banco de dados."""

    def __init__(self, settings: Settings, client: httpx.AsyncClient):
        self.settings = settings
        self.client = client
        self.base_url = settings.java_api_url.rstrip("/")

    async def current_user(self, authorization: str) -> dict[str, Any]:
        return await self._request("GET", "/api/auth/me", authorization=authorization)

    async def plantations(self, authorization: str) -> list[dict[str, Any]]:
        result = await self._request("GET", "/api/plantations", authorization=authorization)
        if not isinstance(result, list):
            raise ServiceError(502, "A API Java retornou uma resposta inválida para plantações.")
        return result

    async def climate_history(
        self,
        authorization: str,
        start: datetime,
        end: datetime,
        channel_id: str | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, str] = {"from": _utc_instant(start), "to": _utc_instant(end)}
        if channel_id:
            params["channelId"] = channel_id
        result = await self._request("GET", "/api/climate/readings", authorization=authorization, params=params)
        if not isinstance(result, list):
            raise ServiceError(502, "A API Java retornou uma resposta inválida para leituras climáticas.")
        return result

    async def ingest_climate(self, readings: list[NormalizedReading]) -> dict[str, Any]:
        """Envia as leituras normalizadas à API Java em lotes e agrega o resultado."""
        if not self.settings.internal_key_configured:
            raise ServiceError(503, "A integração interna com a API Java não está configurada.")
        totals = {"received": 0, "inserted": 0, "alreadyPresent": 0}
        for start in range(0, len(readings), INGEST_BATCH_SIZE):
            batch = readings[start:start + INGEST_BATCH_SIZE]
            body = {"readings": [self._reading_payload(reading) for reading in batch]}
            result = await self._request(
                "POST", "/api/internal/climate-readings/batch", json=body,
                headers={"X-Internal-Api-Key": self.settings.internal_api_key.get_secret_value()},
            ) or {}
            for key in totals:
                totals[key] += int(result.get(key, 0) or 0)
        return totals

    @staticmethod
    def _reading_payload(reading: NormalizedReading) -> dict[str, Any]:
        return {
            "channelId": reading.channel_id,
            "entryId": reading.entry_id,
            "sensorCode": reading.sensor_code,
            "capturedAt": _utc_instant(reading.captured_at),
            "measurements": {name: float(value) for name, value in reading.measurements.items()},
            "qualityStatus": reading.quality_status,
        }

    async def _request(self, method: str, path: str, *, authorization: str | None = None,
                       params: dict[str, str] | None = None, json: dict[str, Any] | None = None,
                       headers: dict[str, str] | None = None) -> Any:
        request_headers = dict(headers or {})
        if authorization:
            request_headers["Authorization"] = authorization
        try:
            response = await self.client.request(method, f"{self.base_url}{path}", params=params,
                                                 json=json, headers=request_headers)
        except httpx.TimeoutException as exception:
            raise ServiceError(503, "A API Java excedeu o tempo de resposta.") from exception
        except httpx.RequestError as exception:
            raise ServiceError(503, "Não foi possível conectar à API Java.") from exception

        if response.status_code == 401:
            raise ServiceError(401, "Sessão inválida ou expirada.")
        if response.status_code == 403:
            raise ServiceError(403, "Seu perfil não tem permissão para este recurso.")
        if response.status_code >= 500:
            raise ServiceError(503, "A API Java está temporariamente indisponível.")
        if response.status_code >= 400:
            raise ServiceError(502, "A API Java rejeitou a solicitação entre serviços.")
        if not response.content:
            return None
        try:
            return response.json()
        except ValueError as exception:
            raise ServiceError(502, "A API Java retornou conteúdo inválido.") from exception


def _utc_instant(value: datetime) -> str:
    """Formato ISO 8601 UTC com sufixo Z, aceito pelo parser Instant do Spring."""
    aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return aware.strftime("%Y-%m-%dT%H:%M:%SZ")
