from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from app.clients.java_api import JavaApiClient
from app.clients.thingspeak import ThingSpeakClient
from app.config import Settings
from app.errors import ServiceError
from app.models import (
    ClimateSummary,
    DashboardSummary,
    PlantationByVariety,
    PlantationSummary,
    SourceAvailability,
    SyncSummary,
)
from app.services.analysis import summarize_climate, summarize_quality


class DashboardService:
    def __init__(self, settings: Settings, client: httpx.AsyncClient):
        self.settings = settings
        self.client = client
        self.java = JavaApiClient(settings, client)
        self.thingspeak = ThingSpeakClient(settings, client)

    async def sync_latest(self) -> SyncSummary:
        if not self.settings.thingspeak_configured:
            return SyncSummary(configured=False, message="ThingSpeak não está configurado.")
        feeds = await self.thingspeak.fetch_feeds(results=self.settings.thingspeak_results_limit)
        readings, rejected = self.thingspeak.normalize_feeds(feeds)
        if readings:
            outcome = await self.java.ingest_climate(readings)
        else:
            outcome = {"inserted": 0, "alreadyPresent": 0}
        return SyncSummary(
            configured=True,
            channel_id=self.settings.thingspeak_channel_id,
            received=len(feeds),
            normalized=len(readings),
            rejected=rejected,
            inserted=int(outcome.get("inserted", 0)),
            already_present=int(outcome.get("alreadyPresent", 0)),
            synchronized_at=datetime.now(UTC),
            message="Sincronização concluída." if readings else "Nenhuma leitura válida foi encontrada.",
        )

    async def climate_summary(self, authorization: str, start: datetime, end: datetime) -> tuple[ClimateSummary, list[dict[str, Any]]]:
        self._validate_range(start, end)
        readings = await self.java.climate_history(
            authorization, start, end,
            self.settings.thingspeak_channel_id if self.settings.thingspeak_channel_id else None,
        )
        rejected = 0
        if not readings and self.settings.thingspeak_configured:
            feeds = await self.thingspeak.fetch_feeds(start=start, end=end, results=self.settings.thingspeak_results_limit)
            normalized, rejected = self.thingspeak.normalize_feeds(feeds)
            if normalized:
                await self.java.ingest_climate(normalized)
                readings = [
                    {
                        "channelId": item.channel_id,
                        "entryId": item.entry_id,
                        "sensorCode": item.sensor_code,
                        "capturedAt": item.captured_at,
                        "measurements": {key: float(value) for key, value in item.measurements.items()},
                        "qualityStatus": item.quality_status,
                    }
                    for item in normalized
                ]
        summary = summarize_climate(readings, channel_id=self.settings.thingspeak_channel_id or None,
                                    rejected_records=rejected, source="ThingSpeak")
        return summary, readings

    async def plantation_summary(self, authorization: str) -> tuple[PlantationSummary, list[dict[str, Any]]]:
        plantations = await self.java.plantations(authorization)
        grouped: dict[str, dict[str, int]] = {}
        total_plants = growing = harvested = archived = 0
        for plantation in plantations:
            variety = str(plantation.get("variety") or "Não informado")
            quantity = self._int_value(plantation.get("quantity"))
            status = str(plantation.get("status", "")).casefold()
            is_archived = bool(plantation.get("archivedAt")) or "arquiv" in status
            is_harvested = bool(plantation.get("harvestedAt") or plantation.get("harvestDate")) or "colhid" in status or "harvest" in status
            total_plants += quantity
            if is_archived:
                archived += 1
            elif is_harvested:
                harvested += 1
            else:
                growing += 1
            bucket = grouped.setdefault(variety, {"plantations": 0, "plants": 0, "growing": 0, "harvested": 0})
            bucket["plantations"] += 1
            bucket["plants"] += quantity
            if not is_archived:
                bucket["harvested" if is_harvested else "growing"] += 1

        by_variety = [PlantationByVariety(variety=name, **values) for name, values in sorted(grouped.items())]
        result = PlantationSummary(total_plantations=len(plantations), growing=growing, harvested=harvested,
                                   archived=archived, total_plants=total_plants, by_variety=by_variety)
        return result, plantations

    async def dashboard_summary(self, authorization: str) -> DashboardSummary:
        now = datetime.now(UTC)
        climate_task = self.climate_summary(authorization, now - timedelta(hours=24), now)
        plantations_task = self.plantation_summary(authorization)
        (climate, _), (plantations, _) = await _gather(climate_task, plantations_task)
        sources = [
            SourceAvailability(source="ThingSpeak", available=climate.available,
                               configured=self.settings.thingspeak_configured,
                               message=climate.message or "Leituras atualizadas."),
            SourceAvailability(source="API Java", available=True, configured=True,
                               message="Autenticação, plantações e persistência servidas pela API Java."),
        ]
        return DashboardSummary(climate=climate, plantations=plantations, sources=sources)

    async def quality_summary(self, authorization: str, start: datetime, end: datetime) -> dict[str, Any]:
        _, readings = await self.climate_summary(authorization, start, end)
        return summarize_quality(readings, expected_metrics=set(self.settings.thingspeak_field_map))

    @staticmethod
    def _validate_range(start: datetime, end: datetime) -> None:
        if start.tzinfo is None or end.tzinfo is None:
            raise ServiceError(400, "As datas devem incluir fuso horário, por exemplo ISO 8601 com Z.")
        if start >= end:
            raise ServiceError(400, "A data inicial deve ser anterior à data final.")
        if end - start > timedelta(days=366):
            raise ServiceError(400, "O intervalo histórico não pode exceder 366 dias.")

    @staticmethod
    def _int_value(value: Any) -> int:
        try:
            return max(0, int(value))
        except (TypeError, ValueError, OverflowError):
            return 0


async def _gather(first, second):
    import asyncio

    results = await asyncio.gather(first, second, return_exceptions=True)
    for result in results:
        if isinstance(result, Exception):
            raise result
    return results[0], results[1]
