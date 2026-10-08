"""Fluxo completo de temperatura e umidade: ThingSpeak -> Python -> API Java -> API Python -> Frontend.

ThingSpeak e API Java são simulados por um MockTransport; o restante (normalização, contrato
interno com INTERNAL_API_KEY, persistência em memória que imita a API Java e a resposta que o
frontend consome) é executado de verdade pela aplicação FastAPI.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta

import httpx
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

INTERNAL_KEY = "i" * 40
CHANNEL_ID = "3499301"
UTC_Z = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


class FakeJavaAndThingSpeak:
    """Simula a API Java (persistência e autenticação) e o canal ThingSpeak."""

    def __init__(self, feeds: list[dict], role_key: str = "PRODUCER"):
        self.feeds = feeds
        self.role_key = role_key
        self.stored: dict[tuple[str, int], dict] = {}
        self.internal_calls = 0

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.thingspeak.test":
            assert request.url.path == f"/channels/{CHANNEL_ID}/feeds.json"
            assert request.url.params["api_key"] == "ts-read-key"
            return httpx.Response(200, json={"channel": {"id": int(CHANNEL_ID)}, "feeds": self.feeds})

        if request.url.path == "/api/auth/me":
            return httpx.Response(200, json={
                "id": "11111111-1111-4111-8111-111111111111", "name": "Produtor", "email": "p@agro.test",
                "roleKey": self.role_key, "role": self.role_key, "status": "ACTIVE",
            })

        if request.url.path == "/api/internal/climate-readings/batch":
            self.internal_calls += 1
            assert request.headers["X-Internal-Api-Key"] == INTERNAL_KEY
            inserted = already = 0
            for item in json.loads(request.content)["readings"]:
                key = (item["channelId"], item["entryId"])
                if key in self.stored:
                    already += 1
                    continue
                self.stored[key] = item
                inserted += 1
            return httpx.Response(202, json={"received": inserted + already, "inserted": inserted,
                                             "alreadyPresent": already})

        if request.url.path == "/api/climate/readings":
            assert UTC_Z.match(request.url.params["from"]), request.url.params["from"]
            assert UTC_Z.match(request.url.params["to"]), request.url.params["to"]
            start = datetime.fromisoformat(request.url.params["from"].replace("Z", "+00:00"))
            end = datetime.fromisoformat(request.url.params["to"].replace("Z", "+00:00"))
            rows = []
            for item in self.stored.values():
                captured = datetime.fromisoformat(item["capturedAt"].replace("Z", "+00:00"))
                if start <= captured <= end and item["channelId"] == request.url.params.get("channelId", item["channelId"]):
                    rows.append({
                        "id": f"row-{item['entryId']}", "channelId": item["channelId"], "entryId": item["entryId"],
                        "sensorCode": item["sensorCode"], "capturedAt": item["capturedAt"],
                        "measurements": item["measurements"], "qualityStatus": item["qualityStatus"],
                    })
            rows.sort(key=lambda row: row["capturedAt"])
            return httpx.Response(200, json=rows)

        return httpx.Response(404, json={"message": "not found in fake"})


def _settings() -> Settings:
    return Settings(
        java_api_url="http://java.test",
        internal_api_key=INTERNAL_KEY,
        thingspeak_channel_id=CHANNEL_ID,
        thingspeak_read_api_key="ts-read-key",
        thingspeak_url="https://api.thingspeak.test",
        thingspeak_field_map={"temperature": "field1", "humidity": "field2"},
        enable_background_sync=False,
    )


def _feeds(now: datetime) -> list[dict]:
    return [
        {
            "entry_id": 101,
            "created_at": (now - timedelta(minutes=20)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "field1": "24.5",
            "field2": "68",
            "field3": "1.4",  # campo antigo de chuva: deve ser ignorado
        },
        {
            "entry_id": 102,
            "created_at": (now - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "field1": "26.0",
            "field2": "63.5",
        },
        {
            "entry_id": 103,
            "created_at": (now - timedelta(minutes=2)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "field1": "",  # sem leitura: a linha não deve ser gravada
            "field2": "",
        },
    ]


def _run_with_fake(fake: FakeJavaAndThingSpeak, path_calls):
    """Executa as chamadas HTTP da API Python usando o transporte simulado."""
    app = create_app(_settings(), start_poller=False)
    with TestClient(app) as client:
        app.state.http_client = httpx.AsyncClient(transport=httpx.MockTransport(fake))
        return [path_calls(client)]


def test_temperature_and_humidity_flow_from_thingspeak_to_frontend_response():
    now = datetime.now(UTC).replace(microsecond=0)
    fake = FakeJavaAndThingSpeak(_feeds(now), role_key="ADMIN")
    headers = {"Authorization": "Bearer admin-jwt"}

    def calls(client: TestClient):
        sync = client.post("/api/v1/integrations/thingspeak/sync", headers=headers)
        current = client.get("/api/v1/climate/current", headers={"Authorization": "Bearer producer-jwt"})
        return sync, current

    ((sync, current),) = _run_with_fake(fake, calls)

    # 1) Python sincronizou, normalizou e enviou ao Java via contrato interno (lote único).
    assert sync.status_code == 200, sync.text
    summary = sync.json()
    assert summary["configured"] is True
    assert summary["received"] == 3
    assert summary["normalized"] == 2
    assert summary["inserted"] == 2
    assert summary["rejected"] == 1
    assert fake.internal_calls == 1
    assert {key[1] for key in fake.stored} == {101, 102}
    assert fake.stored[(CHANNEL_ID, 102)]["measurements"] == {"temperature": 26.0, "humidity": 63.5}

    # 2) Dados gravados pelo Java: só temperatura e umidade (sem o campo antigo de chuva).
    assert all(set(item["measurements"]) == {"temperature", "humidity"} for item in fake.stored.values())

    # 3) API Python entrega ao frontend os campos e rótulos que as telas consomem.
    assert current.status_code == 200, current.text
    body = current.json()
    assert body["available"] is True
    assert body["records"] == 2
    assert body["channelId"] == CHANNEL_ID
    assert body["source"] == "ThingSpeak"
    assert set(body["metrics"]) == {"temperature", "humidity"}
    assert body["metrics"]["temperature"]["current"] == 26.0
    assert body["metrics"]["temperature"]["unit"] == "°C"
    assert body["metrics"]["temperature"]["minimum"] == 24.5
    assert body["metrics"]["humidity"]["current"] == 63.5
    assert body["metrics"]["humidity"]["unit"] == "%"
    assert [point["values"] for point in body["series"]] == [
        {"temperature": 24.5, "humidity": 68.0},
        {"temperature": 26.0, "humidity": 63.5},
    ]


def test_second_sync_is_idempotent_and_does_not_duplicate_readings():
    now = datetime.now(UTC).replace(microsecond=0)
    fake = FakeJavaAndThingSpeak(_feeds(now), role_key="ADMIN")
    headers = {"Authorization": "Bearer admin-jwt"}

    def calls(client: TestClient):
        first = client.post("/api/v1/integrations/thingspeak/sync", headers=headers).json()
        second = client.post("/api/v1/integrations/thingspeak/sync", headers=headers).json()
        return first, second

    ((first, second),) = _run_with_fake(fake, calls)
    assert first["inserted"] == 2
    assert second["inserted"] == 0
    assert second["alreadyPresent"] == 2
    assert len(fake.stored) == 2


def test_climate_history_request_to_java_uses_utc_z_timestamps_and_channel_filter():
    now = datetime.now(UTC).replace(microsecond=0)
    fake = FakeJavaAndThingSpeak(_feeds(now), role_key="PRODUCER")
    fake.stored[(CHANNEL_ID, 500)] = {
        "channelId": CHANNEL_ID, "entryId": 500, "sensorCode": f"thingspeak-{CHANNEL_ID}",
        "capturedAt": (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "measurements": {"temperature": 19.0, "humidity": 70.0}, "qualityStatus": "VALID",
    }
    start = (now - timedelta(hours=2)).isoformat().replace("+00:00", "Z")
    end = now.isoformat().replace("+00:00", "Z")

    def calls(client: TestClient):
        return client.get("/api/v1/climate/history", params={"start": start, "end": end},
                          headers={"Authorization": "Bearer producer-jwt"})

    (response,) = _run_with_fake(fake, calls)
    assert response.status_code == 200, response.text
    assert response.json()["records"] == 1
    assert response.json()["metrics"]["temperature"]["current"] == 19.0
