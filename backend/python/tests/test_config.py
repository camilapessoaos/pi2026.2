import pytest
from pydantic import ValidationError

from app.config import Settings


def test_default_field_map_uses_only_temperature_field1_and_humidity_field2():
    assert Settings().thingspeak_field_map == {"temperature": "field1", "humidity": "field2"}


def test_field_map_accepts_the_two_active_channel_fields_with_normalized_names():
    settings = Settings(thingspeak_field_map={" temperature ": "FIELD1", "humidity": "field2"})
    assert settings.thingspeak_field_map == {"temperature": "field1", "humidity": "field2"}


def test_field_map_rejects_any_other_metric_or_field_assignment():
    with pytest.raises(ValidationError):
        Settings(thingspeak_field_map={"temperature": "field1", "humidity": "field2", "rainfall": "field3"})
    with pytest.raises(ValidationError):
        Settings(thingspeak_field_map={"temperature": "field3", "humidity": "field2"})
    with pytest.raises(ValidationError):
        Settings(thingspeak_field_map={"temperature": "field1"})


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
