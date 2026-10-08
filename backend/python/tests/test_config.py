import pytest
from pydantic import ValidationError

from app.config import Settings


def test_field_mapping_is_configurable_and_limited_to_thingSpeak_fields():
    settings = Settings(thingspeak_field_map={"temperature": "field3", "soilHumidity": "field8"})
    assert settings.thingspeak_field_map == {"temperature": "field3", "soilHumidity": "field8"}


def test_rejects_invalid_channel_id_and_wildcard_origin_is_not_defaulted():
    with pytest.raises(ValidationError):
        Settings(thingspeak_channel_id="123/../../admin")
    assert "*" not in Settings().configured_origins


def test_local_defaults_use_loopback_java_api_and_explicit_local_origins():
    settings = Settings()

    assert settings.java_api_url == "http://localhost:8080"
    assert "http://localhost:5173" in settings.configured_origins
    assert "http://localhost:3000" in settings.configured_origins
    assert "http://127.0.0.1:5500" in settings.configured_origins
    assert "*" not in settings.configured_origins


def test_internal_key_must_be_long_enough_to_enable_service_to_service_ingestion():
    assert Settings(internal_api_key="short").internal_key_configured is False
    assert Settings(internal_api_key="x" * 32).internal_key_configured is True
