from datetime import date
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request

from app.db import Database
from app.rules import classify_hydrotest
from app.schemas import (
    Alert,
    AlertAcknowledgeRequest,
    AlertListResponse,
    DashboardResponse,
    FleetDashboard,
    OpenAlertCounts,
    TodayDashboard,
    UpcomingVehicle,
)

router = APIRouter(prefix="/api")


@router.get("/alerts", response_model=AlertListResponse)
def get_alerts(
    request: Request,
    state: Literal["open", "acknowledged", "all"] = "open",
    level: Literal["critical", "warning"] | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> AlertListResponse:
    database: Database = request.app.state.hydrotest_db
    items, total, summary = database.list_alerts(
        state=state,
        level=level,
        page=page,
        page_size=page_size,
    )
    return AlertListResponse(
        items=[Alert.model_validate(item) for item in items],
        total=total,
        summary=summary,
    )


@router.post("/alerts/{alert_id}/acknowledge", response_model=Alert)
def acknowledge_alert(
    alert_id: int,
    payload: AlertAcknowledgeRequest,
    request: Request,
) -> Alert:
    database: Database = request.app.state.hydrotest_db
    alert = database.acknowledge_alert(alert_id, payload.note)
    if alert is None:
        raise HTTPException(status_code=404, detail="ALERT_NOT_FOUND")
    return Alert.model_validate(alert)


@router.get("/dashboard", response_model=DashboardResponse)
def get_dashboard(request: Request) -> DashboardResponse:
    database: Database = request.app.state.hydrotest_db
    data = database.dashboard_data(date.today())
    today_counts = data["today"]
    open_alert_counts = data["open_alerts"]

    fleet_expired = 0
    fleet_expiring = 0
    fleet_valid = 0
    upcoming: list[UpcomingVehicle] = []
    today = date.today()
    for vehicle in data["vehicles"]:
        status, days = classify_hydrotest(vehicle["next_due_date"], today)
        if status == "EXPIRED":
            fleet_expired += 1
        elif status == "EXPIRING_SOON":
            fleet_expiring += 1
            if days is not None:
                upcoming.append(
                    UpcomingVehicle(
                        plate=vehicle["plate"],
                        owner=vehicle["owner"],
                        next_due_date=date.fromisoformat(vehicle["next_due_date"]),
                        days_remaining=days,
                    )
                )
        elif status == "VALID":
            fleet_valid += 1

    upcoming.sort(
        key=lambda vehicle: (vehicle.days_remaining, vehicle.plate)
    )
    open_alerts = OpenAlertCounts(
        critical=open_alert_counts.get("critical", 0),
        warning=open_alert_counts.get("warning", 0),
    )
    return DashboardResponse(
        today=TodayDashboard(
            scans=sum(today_counts.values()),
            valid=today_counts.get("VALID", 0),
            expired=today_counts.get("EXPIRED", 0),
            expiring_soon=today_counts.get("EXPIRING_SOON", 0),
            needs_review=today_counts.get("NEEDS_REVIEW", 0),
        ),
        open_alerts=open_alerts,
        recent_alerts=[
            Alert.model_validate(item) for item in data["recent_alerts"]
        ],
        fleet=FleetDashboard(
            expired=fleet_expired,
            expiring_30_days=fleet_expiring,
            valid=fleet_valid,
            upcoming=upcoming[:10],
        ),
        all_clear=open_alerts.critical == 0 and open_alerts.warning == 0,
    )
