import asyncio
from datetime import UTC, datetime

import httpx

from app.config import Settings
from app.services.dashboard import DashboardService


def test_thingspeak_readings_are_normalized_and_posted_to_java_internal_api():
    observed: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        observed.append(request)
        if request.url.host == "api.thingspeak.test":
            return httpx.Response(200, json={
                "channel": {"id": 77},
                "feeds": [{
                    "entry_id": 6,
                    "created_at": datetime.now(UTC).isoformat(),
                    "field1": "23.5",
                    "field2": "61",
                }],
            })
        if request.url.path == "/api/internal/climate-readings/batch":
            assert request.headers["X-Internal-Api-Key"] == "x" * 40
            return httpx.Response(200, json={"received": 1, "inserted": 1, "alreadyPresent": 0})
        return httpx.Response(404)

    async def run():
        settings = Settings(
            java_api_url="http://java.test",
            thingspeak_channel_id="77",
            thingspeak_url="https://api.thingspeak.test",
            thingspeak_field_map={"temperature": "field1", "humidity": "field2"},
            thingspeak_read_api_key="sensor-key",
            internal_api_key="x" * 40,
        )
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await DashboardService(settings, client).sync_latest()

    result = asyncio.run(run())

    assert result.received == 1
    assert result.normalized == 1
    assert result.inserted == 1
    assert result.rejected == 0
    assert len(observed) == 2
    ingest = observed[1]
    payload = __import__("json").loads(ingest.content)
    reading = payload["readings"][0]
    assert reading["channelId"] == "77"
    assert reading["entryId"] == 6
    assert reading["measurements"] == {"temperature": 23.5, "humidity": 61.0}
