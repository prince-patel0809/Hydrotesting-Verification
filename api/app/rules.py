from datetime import date
from typing import Literal

HydrotestStatus = Literal["VALID", "EXPIRING_SOON", "EXPIRED", "NEEDS_REVIEW"]


def days_until_due(due_date: str | date | None, today: date | None = None) -> int | None:
    if due_date is None:
        return None
    try:
        parsed_due_date = (
            due_date if isinstance(due_date, date) else date.fromisoformat(due_date)
        )
    except ValueError:
        return None
    current_date = today if today is not None else date.today()
    return (parsed_due_date - current_date).days


def classify_hydrotest(
    due_date: str | date | None,
    today: date | None = None,
    expiring_soon_days: int = 30,
) -> tuple[HydrotestStatus, int | None]:
    remaining = days_until_due(due_date, today)
    if remaining is None:
        return "NEEDS_REVIEW", None
    if remaining < 0:
        return "EXPIRED", -remaining
    if remaining <= expiring_soon_days:
        return "EXPIRING_SOON", remaining
    return "VALID", remaining
