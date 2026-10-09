import re
from datetime import date
from typing import Any

from app.db import Database
from app.rules import classify_hydrotest
from app.schemas import AlertBrief, VerifyResponse


def normalize_plate(plate: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", plate.upper())


def verify_registered_plate(database: Database, raw_plate: str) -> dict[str, Any]:
    plate = normalize_plate(raw_plate)
    vehicle = database.get_vehicle(plate) if plate else None
    status, days = classify_hydrotest(
        vehicle["next_due_date"] if vehicle is not None else None,
        date.today(),
    )

    alert_level = None
    alert_message = None
    if status == "EXPIRED":
        alert_level = "critical"
        alert_message = f"Hydrotest expired {days} days ago. Do not fill."
    elif status == "EXPIRING_SOON":
        alert_level = "warning"
        alert_message = f"Hydrotest expires in {days} days. Advise the owner."
    elif status == "VALID":
        alert_message = "Hydrotest is valid today. OK to fill."
    else:
        alert_message = "Hydrotest information is unavailable. Refer to an operator."

    check, alert = database.record_check(
        plate=plate,
        owner=vehicle["owner"] if vehicle is not None else None,
        test_date=vehicle["test_date"] if vehicle is not None else None,
        next_due_date=vehicle["next_due_date"] if vehicle is not None else None,
        status=status,
        days_overdue_or_remaining=days,
        alert_level=alert_level,
        alert_message=alert_message if alert_level is not None else None,
    )
    alert_brief = (
        AlertBrief(
            id=alert["id"],
            level=alert["level"],
            message=alert["message"],
        )
        if alert is not None
        else None
    )
    result = VerifyResponse(
        check_id=check["id"],
        plate=plate,
        status=status,
        owner=vehicle["owner"] if vehicle is not None else None,
        test_date=vehicle["test_date"] if vehicle is not None else None,
        next_due_date=vehicle["next_due_date"] if vehicle is not None else None,
        days_overdue_or_remaining=days,
        message=alert_message,
        alert=alert_brief,
    ).model_dump(mode="json")
    if alert is not None:
        result["alert"] = database.get_alert(alert["id"])
    return result
