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


def test_sync_sends_only_temperature_and_humidity_even_when_feed_has_other_fields():
    observed_payloads: list[dict] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.thingspeak.test":
            return httpx.Response(200, json={
                "channel": {"id": 77},
                "feeds": [{
                    "entry_id": 9,
                    "created_at": datetime.now(UTC).isoformat(),
                    "field1": "22.0",
                    "field2": "55",
                    "field3": "3.1",
                    "field4": "800",
                }],
            })
        observed_payloads.append(__import__("json").loads(request.content))
        return httpx.Response(202, json={"received": 1, "inserted": 1, "alreadyPresent": 0})

    async def run():
        settings = Settings(
            java_api_url="http://java.test",
            thingspeak_channel_id="77",
            thingspeak_url="https://api.thingspeak.test",
            thingspeak_read_api_key="sensor-key",
            internal_api_key="x" * 40,
        )
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await DashboardService(settings, client).sync_latest()

    result = asyncio.run(run())
    assert result.inserted == 1
    assert observed_payloads[0]["readings"][0]["measurements"] == {"temperature": 22.0, "humidity": 55.0}


def test_sync_posts_large_feeds_in_batches_below_java_limit():
    batches: list[int] = []
    feeds = [
        {"entry_id": index, "created_at": datetime.now(UTC).isoformat(), "field1": "20", "field2": "60"}
        for index in range(1, 1201)
    ]

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.thingspeak.test":
            return httpx.Response(200, json={"channel": {"id": 77}, "feeds": feeds})
        size = len(__import__("json").loads(request.content)["readings"])
        batches.append(size)
        return httpx.Response(202, json={"received": size, "inserted": size, "alreadyPresent": 0})

    async def run():
        settings = Settings(
            java_api_url="http://java.test",
            thingspeak_channel_id="77",
            thingspeak_url="https://api.thingspeak.test",
            internal_api_key="x" * 40,
            thingspeak_results_limit=8000,
        )
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await DashboardService(settings, client).sync_latest()

    result = asyncio.run(run())
    assert batches == [500, 500, 200]
    assert max(batches) <= 1000
    assert result.inserted == 1200
    assert result.normalized == 1200
