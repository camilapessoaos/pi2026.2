from __future__ import annotations

import re
from urllib.parse import urlparse

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# O canal ThingSpeak possui apenas dois campos ativos: temperatura (field1) e umidade (field2).
# Essa correspondência é fixa: qualquer outro mapeamento é rejeitado na inicialização.
THINGSPEAK_METRIC_FIELDS: dict[str, str] = {
    "temperature": "field1",
    "humidity": "field2",
}
DEFAULT_FIELD_MAP = THINGSPEAK_METRIC_FIELDS


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    service_name: str = "AgroClima Analytics API"
    java_api_url: str = "http://localhost:8080"
    internal_api_key: SecretStr = SecretStr("")
    thingspeak_channel_id: str = ""
    thingspeak_read_api_key: SecretStr = SecretStr("")
    thingspeak_url: str = "https://api.thingspeak.com"
    thingspeak_field_map: dict[str, str] = Field(default_factory=lambda: DEFAULT_FIELD_MAP.copy())
    thingspeak_poll_interval_seconds: int = 300
    thingspeak_results_limit: int = 500
    request_timeout_seconds: float = 12.0
    cors_allowed_origins: str = (
        "http://localhost,http://localhost:3000,http://localhost:5173,http://localhost:5500,http://localhost:8081,"
        "http://127.0.0.1,http://127.0.0.1:3000,http://127.0.0.1:5173,http://127.0.0.1:5500,http://127.0.0.1:8081"
    )
    enable_background_sync: bool = True
    root_path: str = ""

    @field_validator("java_api_url", "thingspeak_url")
    @classmethod
    def validate_http_url(cls, value: str) -> str:
        parsed = urlparse(value.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("URL deve ser HTTP ou HTTPS e incluir host.")
        return value.strip().rstrip("/")

    @field_validator("thingspeak_channel_id")
    @classmethod
    def normalize_channel_id(cls, value: str) -> str:
        normalized = value.strip()
        if normalized and not re.fullmatch(r"[0-9]+", normalized):
            raise ValueError("THINGSPEAK_CHANNEL_ID deve conter apenas números.")
        return normalized

    @field_validator("thingspeak_field_map")
    @classmethod
    def validate_field_map(cls, value: dict[str, str]) -> dict[str, str]:
        normalized = {str(metric).strip(): str(field_name).strip().lower() for metric, field_name in value.items()}
        if normalized != THINGSPEAK_METRIC_FIELDS:
            raise ValueError(
                'THINGSPEAK_FIELD_MAP deve ser exatamente {"temperature":"field1","humidity":"field2"}. '
                "O canal possui apenas temperatura (field1) e umidade (field2)."
            )
        return dict(THINGSPEAK_METRIC_FIELDS)

    @field_validator("thingspeak_poll_interval_seconds")
    @classmethod
    def validate_poll_interval(cls, value: int) -> int:
        if value < 15 or value > 86_400:
            raise ValueError("THINGSPEAK_POLL_INTERVAL_SECONDS deve estar entre 15 e 86400.")
        return value

    @field_validator("thingspeak_results_limit")
    @classmethod
    def validate_results_limit(cls, value: int) -> int:
        if value < 1 or value > 8000:
            raise ValueError("THINGSPEAK_RESULTS_LIMIT deve estar entre 1 e 8000.")
        return value

    @field_validator("request_timeout_seconds")
    @classmethod
    def validate_timeout(cls, value: float) -> float:
        if value < 1 or value > 60:
            raise ValueError("REQUEST_TIMEOUT_SECONDS deve estar entre 1 e 60 segundos.")
        return value

    @property
    def configured_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]

    @property
    def thingspeak_configured(self) -> bool:
        return bool(self.thingspeak_channel_id and self.thingspeak_url)

    @property
    def internal_key_configured(self) -> bool:
        return len(self.internal_api_key.get_secret_value()) >= 32

    @property
    def thingspeak_key(self) -> str:
        return self.thingspeak_read_api_key.get_secret_value()
