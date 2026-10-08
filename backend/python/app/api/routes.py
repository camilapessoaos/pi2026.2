from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, Header, Query, Request

from app.clients.java_api import JavaApiClient
from app.config import Settings
from app.errors import ServiceError
from app.models import (
    AnalystDashboard,
    ComparisonSummary,
    ForecastSummary,
    MarketSummary,
    QualitySummary,
    UserProfile,
)
from app.services.dashboard import DashboardService

router = APIRouter(prefix="/api/v1", tags=["Análises e dashboards"])


@dataclass(frozen=True)
class RequestContext:
    user: UserProfile
    authorization: str


def _service(request: Request) -> DashboardService:
    return DashboardService(request.app.state.settings, request.app.state.http_client)


def _java(request: Request) -> JavaApiClient:
    return JavaApiClient(request.app.state.settings, request.app.state.http_client)


async def current_context(
    request: Request,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> RequestContext:
    if not authorization or not authorization.lower().startswith("bearer ") or not authorization[7:].strip():
        raise ServiceError(401, "Autenticação Bearer obrigatória.")
    profile_data = await _java(request).current_user(authorization)
    try:
        profile = UserProfile.model_validate(profile_data)
    except Exception as exception:
        raise ServiceError(502, "A API Java retornou um perfil de usuário inválido.") from exception
    if profile.status.upper() not in {"ACTIVE", "ATIVO"}:
        raise ServiceError(401, "A conta não está ativa.")
    return RequestContext(user=profile, authorization=authorization)


def _require_role(context: RequestContext, allowed: set[str]) -> None:
    if context.user.role_key.upper() not in allowed:
        raise ServiceError(403, "Seu perfil não tem permissão para este recurso.")


def _date_window(start: datetime | None, end: datetime | None) -> tuple[datetime, datetime]:
    if start is None and end is None:
        end = datetime.now(UTC)
        start = end - timedelta(hours=24)
    elif start is None or end is None:
        raise ServiceError(400, "Informe as duas datas: start e end.")
    return start, end


@router.get("/climate/current")
async def current_climate(context: Annotated[RequestContext, Depends(current_context)], request: Request):
    end = datetime.now(UTC)
    start = end - timedelta(hours=24)
    summary, _ = await _service(request).climate_summary(context.authorization, start, end)
    return summary


@router.get("/climate/history")
async def climate_history(
    context: Annotated[RequestContext, Depends(current_context)],
    request: Request,
    start: datetime | None = Query(default=None, description="Data inicial ISO 8601 com fuso horário."),
    end: datetime | None = Query(default=None, description="Data final ISO 8601 com fuso horário."),
):
    start, end = _date_window(start, end)
    summary, _ = await _service(request).climate_summary(context.authorization, start, end)
    return summary


@router.get("/dashboard/summary")
async def dashboard_summary(context: Annotated[RequestContext, Depends(current_context)], request: Request):
    return await _service(request).dashboard_summary(context.authorization)


@router.get("/dashboard/producer")
async def producer_dashboard(context: Annotated[RequestContext, Depends(current_context)], request: Request):
    _require_role(context, {"PRODUCER", "ADMIN"})
    return await _service(request).dashboard_summary(context.authorization)


@router.get("/dashboard/analyst", response_model=AnalystDashboard)
async def analyst_dashboard(
    context: Annotated[RequestContext, Depends(current_context)],
    request: Request,
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
):
    _require_role(context, {"ANALYST", "ADMIN"})
    start, end = _date_window(start, end)
    service = _service(request)
    summary = await service.dashboard_summary(context.authorization)
    quality_data = await service.quality_summary(context.authorization, start, end)
    quality = QualitySummary.model_validate(quality_data)
    comparison = ComparisonSummary(
        available=summary.climate.available or summary.plantations.total_plantations > 0,
        climate_metrics=summary.climate.metrics,
        plantations_by_variety=summary.plantations.by_variety,
        limitation="Le leituras climáticas são agregadas por canal. Não há vínculo entre sensor e variedade no cadastro atual.",
    )
    return AnalystDashboard(summary=summary, quality=quality, comparison=comparison, generated_at=datetime.now(UTC))


@router.get("/dashboard/quality", response_model=QualitySummary)
async def climate_quality(
    context: Annotated[RequestContext, Depends(current_context)],
    request: Request,
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
):
    _require_role(context, {"ANALYST", "ADMIN"})
    start, end = _date_window(start, end)
    result = await _service(request).quality_summary(context.authorization, start, end)
    return QualitySummary.model_validate(result)


@router.get("/dashboard/comparison", response_model=ComparisonSummary)
async def comparison_dashboard(context: Annotated[RequestContext, Depends(current_context)], request: Request):
    _require_role(context, {"ANALYST", "ADMIN"})
    summary = await _service(request).dashboard_summary(context.authorization)
    return ComparisonSummary(
        available=summary.climate.available or summary.plantations.total_plantations > 0,
        climate_metrics=summary.climate.metrics,
        plantations_by_variety=summary.plantations.by_variety,
        limitation="Não existe associação entre leituras de canal e variedade; não são inferidos rendimentos por uva.",
    )


@router.get("/dashboard/market", response_model=MarketSummary)
async def market_dashboard(_: Annotated[RequestContext, Depends(current_context)]):
    return MarketSummary()


@router.get("/dashboard/forecast", response_model=ForecastSummary)
async def forecast_dashboard(_: Annotated[RequestContext, Depends(current_context)]):
    return ForecastSummary()


@router.get("/integrations/thingspeak/status")
async def thingspeak_status(context: Annotated[RequestContext, Depends(current_context)], request: Request):
    _require_role(context, {"ADMIN"})
    settings: Settings = request.app.state.settings
    return {
        "configured": settings.thingspeak_configured,
        "channelId": settings.thingspeak_channel_id or None,
        "readKeyConfigured": bool(settings.thingspeak_key),
        "internalSyncConfigured": settings.internal_key_configured,
        "fieldMap": settings.thingspeak_field_map,
    }


@router.post("/integrations/thingspeak/sync")
async def synchronize_thingspeak(context: Annotated[RequestContext, Depends(current_context)], request: Request):
    _require_role(context, {"ADMIN"})
    return await _service(request).sync_latest()
