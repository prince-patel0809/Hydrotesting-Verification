from datetime import date, timedelta
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.db import Database
from app.main import app
from app.rules import classify_hydrotest


@pytest.fixture
def api_client(tmp_path):
    database = Database(tmp_path / "hydrotest-test.sqlite3")
    database.initialize()
    original_database = app.state.hydrotest_db
    app.state.hydrotest_db = database
    try:
        with TestClient(app) as client:
            yield client, database
    finally:
        app.state.hydrotest_db = original_database


def add_vehicle(
    database: Database,
    plate: str,
    next_due_date: date,
    owner: str = "Test Owner",
) -> None:
    with sqlite3.connect(database.path) as connection:
        connection.execute(
            """
            INSERT INTO vehicles (plate, owner, test_date, next_due_date)
            VALUES (?, ?, ?, ?)
            """,
            (
                plate,
                owner,
                (next_due_date - timedelta(days=365)).isoformat(),
                next_due_date.isoformat(),
            ),
        )


def verify(client: TestClient, plate: str) -> dict:
    response = client.post("/api/verify", json={"plate": plate})
    assert response.status_code == 200
    return response.json()


def test_expired_vehicle_creates_critical_alert(api_client) -> None:
    client, database = api_client
    add_vehicle(database, "DL01AB1234", date.today() - timedelta(days=5))

    result = verify(client, "DL01AB1234")

    assert result["status"] == "EXPIRED"
    assert result["days_overdue_or_remaining"] == 5
    assert result["alert"]["level"] == "critical"
    assert result["alert"]["message"] == "Hydrotest expired 5 days ago. Do not fill."


def test_expiring_soon_vehicle_creates_warning_alert(api_client) -> None:
    client, database = api_client
    add_vehicle(database, "DL01AB2345", date.today() + timedelta(days=7))

    result = verify(client, "DL01AB2345")

    assert result["status"] == "EXPIRING_SOON"
    assert result["alert"]["level"] == "warning"
    assert result["alert"]["message"] == "Hydrotest expires in 7 days. Advise the owner."


def test_valid_vehicle_creates_no_alert(api_client) -> None:
    client, database = api_client
    add_vehicle(database, "DL01AB3456", date.today() + timedelta(days=60))

    result = verify(client, "DL01AB3456")

    assert result["status"] == "VALID"
    assert result["alert"] is None
    assert client.get("/api/alerts").json()["total"] == 0


def test_repeated_verification_deduplicates_open_alert(api_client) -> None:
    client, database = api_client
    add_vehicle(database, "DL01AB4567", date.today() - timedelta(days=3))

    first = verify(client, "DL01AB4567")
    second = verify(client, "DL01AB4567")
    alerts = client.get("/api/alerts").json()

    assert first["alert"]["id"] == second["alert"]["id"]
    assert alerts["total"] == 1
    assert alerts["items"][0]["seen_count"] == 2
    assert alerts["items"][0]["check_id"] == second["check_id"]


def test_acknowledging_alert_removes_it_from_open_state(api_client) -> None:
    client, database = api_client
    add_vehicle(database, "DL01AB5678", date.today() - timedelta(days=1))
    result = verify(client, "DL01AB5678")

    response = client.post(
        f"/api/alerts/{result['alert']['id']}/acknowledge",
        json={"note": "Supervisor reviewed cylinder record"},
    )

    assert response.status_code == 200
    assert response.json()["acknowledged"] is True
    assert response.json()["ack_note"] == "Supervisor reviewed cylinder record"
    assert client.get("/api/alerts?state=open").json()["total"] == 0
    assert client.get("/api/alerts?state=acknowledged").json()["total"] == 1


def test_dashboard_all_clear_changes_with_open_alerts(api_client) -> None:
    client, database = api_client
    add_vehicle(database, "DL01AB6789", date.today() - timedelta(days=2))

    result = verify(client, "DL01AB6789")
    dashboard = client.get("/api/dashboard").json()
    assert dashboard["all_clear"] is False
    assert dashboard["open_alerts"]["critical"] == 1

    client.post(f"/api/alerts/{result['alert']['id']}/acknowledge", json={})

    dashboard = client.get("/api/dashboard").json()
    assert dashboard["all_clear"] is True
    assert dashboard["open_alerts"] == {"critical": 0, "warning": 0}


def test_dashboard_counts_today_and_sorts_upcoming_fleet_by_due_date(api_client) -> None:
    client, database = api_client
    add_vehicle(database, "DL01AB6001", date.today() - timedelta(days=2))
    add_vehicle(database, "DL01AB6002", date.today() + timedelta(days=9))
    add_vehicle(database, "DL01AB6003", date.today() + timedelta(days=2))
    add_vehicle(database, "DL01AB6004", date.today() + timedelta(days=90))

    verify(client, "DL01AB6001")
    verify(client, "DL01AB6002")
    verify(client, "DL01AB6003")
    verify(client, "DL01AB6004")

    dashboard = client.get("/api/dashboard").json()

    assert dashboard["today"] == {
        "scans": 4,
        "valid": 1,
        "expired": 1,
        "expiring_soon": 2,
        "needs_review": 0,
    }
    assert dashboard["fleet"]["expired"] == 1
    assert dashboard["fleet"]["expiring_30_days"] == 2
    assert dashboard["fleet"]["valid"] == 1
    assert [item["days_remaining"] for item in dashboard["fleet"]["upcoming"]] == [2, 9]
    assert [item["level"] for item in dashboard["recent_alerts"]] == [
        "critical",
        "warning",
        "warning",
    ]


def test_expired_due_date_never_classifies_as_valid() -> None:
    status, days = classify_hydrotest(
        date.today() - timedelta(days=1),
        today=date.today(),
    )

    assert status == "EXPIRED"
    assert days == 1


def test_unregistered_plate_requires_human_review(api_client) -> None:
    client, _ = api_client

    result = verify(client, "UNKNOWN")

    assert result["status"] == "NEEDS_REVIEW"
    assert result["alert"] is None
    assert "operator" in result["message"].lower()


def test_acknowledgement_is_idempotent_and_missing_alert_is_not_found(api_client) -> None:
    client, database = api_client
    add_vehicle(database, "DL01AB7890", date.today() - timedelta(days=4))
    result = verify(client, "DL01AB7890")
    alert_id = result["alert"]["id"]

    first = client.post(
        f"/api/alerts/{alert_id}/acknowledge",
        json={"note": "Reviewed"},
    )
    second = client.post(
        f"/api/alerts/{alert_id}/acknowledge",
        json={"note": "Changed note should not overwrite"},
    )
    missing = client.post("/api/alerts/99999/acknowledge", json={})

    assert first.json()["acknowledged_at"] == second.json()["acknowledged_at"]
    assert second.json()["ack_note"] == "Reviewed"
    assert missing.status_code == 404
    assert missing.json()["detail"] == "ALERT_NOT_FOUND"
