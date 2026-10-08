import asyncio
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest

from app.clients.thingspeak import ThingSpeakClient
from app.config import Settings
from app.errors import ServiceError


def test_normalizes_configured_fields_and_marks_invalid_measurement_for_review():
    settings = Settings(
        thingspeak_channel_id="123456",
        thingspeak_field_map={"temperature": "field1", "humidity": "field2"},
    )
    http = httpx.AsyncClient()
    try:
        client = ThingSpeakClient(settings, http)
        feed = {
            "entry_id": 14,
            "created_at": datetime.now(UTC).isoformat(),
            "field1": "24.375",
            "field2": "145",
        }
        readings, rejected = client.normalize_feeds([feed])
    finally:
        asyncio.run(http.aclose())

    assert rejected == 0
    assert len(readings) == 1
    assert readings[0].channel_id == "123456"
    assert readings[0].entry_id == 14
    assert readings[0].measurements == {"temperature": Decimal("24.375")}
    assert readings[0].quality_status == "REVIEW"


def test_rejects_feed_without_any_usable_numeric_measurements():
    settings = Settings(thingspeak_channel_id="9", thingspeak_field_map={"humidity": "field2"})
    http = httpx.AsyncClient()
    try:
        readings, rejected = ThingSpeakClient(settings, http).normalize_feeds([{
            "entry_id": 7,
            "created_at": datetime.now(UTC).isoformat(),
            "field2": "not-a-number",
        }])
    finally:
        asyncio.run(http.aclose())

    assert readings == []
    assert rejected == 1


def test_requires_a_configured_channel_before_requesting_thingspeak():
    settings = Settings(thingspeak_channel_id="")
    http = httpx.AsyncClient()
    try:
        with pytest.raises(ServiceError) as error:
            asyncio.run(ThingSpeakClient(settings, http).fetch_feeds())
    finally:
        asyncio.run(http.aclose())

    assert error.value.status_code == 503


def test_fetches_configured_channel_and_sends_read_key_without_logging_it():
    observed: dict[str, str] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        observed["url"] = str(request.url)
        observed["channel"] = request.url.path.split("/")[2]
        observed["api_key"] = request.url.params["api_key"]
        return httpx.Response(200, json={
            "channel": {"id": 123456},
            "feeds": [{"entry_id": 1, "created_at": datetime.now(UTC).isoformat(), "field1": "21.5"}],
        })

    async def run():
        settings = Settings(
            thingspeak_channel_id="123456",
            thingspeak_read_api_key="sensor-read-secret",
            thingspeak_url="https://sensor.example.test",
        )
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            return await ThingSpeakClient(settings, http).fetch_feeds(results=10)

    feeds = asyncio.run(run())
    assert len(feeds) == 1
    assert observed["channel"] == "123456"
    assert observed["api_key"] == "sensor-read-secret"
    assert "results=10" in observed["url"]
