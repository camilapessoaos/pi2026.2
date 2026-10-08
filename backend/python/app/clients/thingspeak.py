from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import logging
import re
from typing import Any

import httpx

from app.config import Settings
from app.errors import ServiceError
from app.models import NormalizedReading

logger = logging.getLogger(__name__)
METRIC_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")


class ThingSpeakClient:
    def __init__(self, settings: Settings, client: httpx.AsyncClient):
        self.settings = settings
        self.client = client

    async def fetch_feeds(self, *, start: datetime | None = None, end: datetime | None = None,
                          results: int | None = None) -> list[dict[str, Any]]:
        if not self.settings.thingspeak_configured:
            raise ServiceError(503, "ThingSpeak não está configurado. Informe THINGSPEAK_CHANNEL_ID.")
        limit = max(1, min(results or self.settings.thingspeak_results_limit, 8000))
        params: dict[str, str | int] = {"results": limit}
        if self.settings.thingspeak_key:
            params["api_key"] = self.settings.thingspeak_key
        if start:
            params["start"] = self._as_utc(start).isoformat().replace("+00:00", "Z")
        if end:
            params["end"] = self._as_utc(end).isoformat().replace("+00:00", "Z")
        channel = self.settings.thingspeak_channel_id
        url = f"{self.settings.thingspeak_url}/channels/{channel}/feeds.json"
        try:
            response = await self.client.get(url, params=params)
        except httpx.TimeoutException as exception:
            logger.warning("ThingSpeak timeout channel=%s", channel)
            raise ServiceError(503, "ThingSpeak excedeu o tempo de resposta.") from exception
        except httpx.RequestError as exception:
            logger.warning("ThingSpeak connection error channel=%s type=%s", channel, type(exception).__name__)
            raise ServiceError(503, "Não foi possível conectar ao ThingSpeak.") from exception

        if response.status_code in (401, 403):
            raise ServiceError(502, "ThingSpeak recusou o acesso ao canal; verifique a chave de leitura.")
        if response.status_code == 404:
            raise ServiceError(502, "O canal ThingSpeak configurado não foi encontrado.")
        if response.status_code >= 400:
            raise ServiceError(502, "ThingSpeak não conseguiu fornecer as leituras.")
        try:
            data = response.json()
        except ValueError as exception:
            raise ServiceError(502, "ThingSpeak retornou JSON inválido.") from exception
        if not isinstance(data, dict) or not isinstance(data.get("feeds"), list):
            raise ServiceError(502, "Formato de resposta ThingSpeak inválido.")
        response_channel = data.get("channel")
        if isinstance(response_channel, dict) and response_channel.get("id") is not None:
            if str(response_channel["id"]) != channel:
                raise ServiceError(502, "A resposta ThingSpeak não corresponde ao canal configurado.")
        return [feed for feed in data["feeds"] if isinstance(feed, dict)]

    def normalize_feeds(self, feeds: list[dict[str, Any]]) -> tuple[list[NormalizedReading], int]:
        accepted: list[NormalizedReading] = []
        rejected = 0
        for feed in feeds:
            reading = self._normalize_feed(feed)
            if reading is None:
                rejected += 1
            else:
                accepted.append(reading)
        return accepted, rejected

    def _normalize_feed(self, feed: dict[str, Any]) -> NormalizedReading | None:
        try:
            entry_id = int(feed.get("entry_id"))
            if entry_id <= 0:
                return None
            captured_at = self._parse_timestamp(feed.get("created_at"))
            if captured_at > datetime.now(UTC).replace(microsecond=0) + __import__("datetime").timedelta(minutes=5):
                return None
        except (TypeError, ValueError, OverflowError):
            return None

        measurements: dict[str, Decimal] = {}
        review = False
        for metric_name, field_name in self.settings.thingspeak_field_map.items():
            raw_value = feed.get(field_name)
            if raw_value is None or str(raw_value).strip() == "":
                continue
            if not METRIC_NAME.fullmatch(metric_name):
                review = True
                continue
            try:
                value = Decimal(str(raw_value).strip())
                if not value.is_finite():
                    raise InvalidOperation
                value = value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP).normalize()
            except (InvalidOperation, ValueError, TypeError):
                review = True
                continue
            if len(value.as_tuple().digits) > 12 or abs(value.as_tuple().exponent) > 4:
                review = True
                continue
            if not self._in_physical_range(metric_name, value):
                review = True
                continue
            measurements[metric_name] = value

        if not measurements:
            return None
        return NormalizedReading(
            channel_id=self.settings.thingspeak_channel_id,
            entry_id=entry_id,
            sensor_code=f"thingspeak-{self.settings.thingspeak_channel_id}",
            captured_at=captured_at,
            measurements=measurements,
            quality_status="REVIEW" if review else "VALID",
        )

    @staticmethod
    def _in_physical_range(metric_name: str, value: Decimal) -> bool:
        key = metric_name.lower().replace("_", "")
        if key in {"humidity", "relativehumidity", "soilhumidity"}:
            return Decimal("0") <= value <= Decimal("100")
        if key in {"temperature", "temperaturec", "tempc"}:
            return Decimal("-80") <= value <= Decimal("80")
        if "rain" in key or key == "precipitation" or key in {"luminosity", "light"}:
            return value >= Decimal("0")
        return True

    @staticmethod
    def _parse_timestamp(value: Any) -> datetime:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("created_at ausente")
        timestamp = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)
        return timestamp.astimezone(UTC)

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
