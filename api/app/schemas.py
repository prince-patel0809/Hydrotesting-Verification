from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.rules import HydrotestStatus

AlertLevel = Literal["critical", "warning"]


class VerifyRequest(BaseModel):
    plate: str = Field(min_length=1, max_length=32)


class AlertBrief(BaseModel):
    id: int
    level: AlertLevel
    message: str


class VerifyResponse(BaseModel):
    check_id: int
    plate: str
    status: HydrotestStatus
    owner: str | None
    test_date: date | None
    next_due_date: date | None
    days_overdue_or_remaining: int | None
    message: str
    alert: AlertBrief | None


class Alert(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    check_id: int
    plate: str
    level: AlertLevel
    message: str
    days_overdue_or_remaining: int
    created_at: datetime
    last_seen_at: datetime
    seen_count: int
    acknowledged: bool
    acknowledged_at: datetime | None
    ack_note: str | None


class AlertAcknowledgeRequest(BaseModel):
    note: str | None = Field(default=None, max_length=1000)


class AlertSummary(BaseModel):
    open_critical: int
    open_warning: int


class AlertListResponse(BaseModel):
    items: list[Alert]
    total: int
    summary: AlertSummary


class TodayDashboard(BaseModel):
    scans: int
    valid: int
    expired: int
    expiring_soon: int
    needs_review: int


class OpenAlertCounts(BaseModel):
    critical: int
    warning: int


class UpcomingVehicle(BaseModel):
    plate: str
    owner: str | None
    next_due_date: date
    days_remaining: int


class FleetDashboard(BaseModel):
    expired: int
    expiring_30_days: int
    valid: int
    upcoming: list[UpcomingVehicle]


class DashboardResponse(BaseModel):
    today: TodayDashboard
    open_alerts: OpenAlertCounts
    recent_alerts: list[Alert]
    fleet: FleetDashboard
    all_clear: bool
