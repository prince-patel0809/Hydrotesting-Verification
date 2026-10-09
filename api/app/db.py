import os
import sqlite3
from contextlib import closing
from datetime import date, datetime
from pathlib import Path
from typing import Any


class Database:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(
            path
            if path is not None
            else os.getenv(
                "HYDROTEST_DB_PATH",
                str(Path(__file__).resolve().parents[1] / "hydrotest.sqlite3"),
            )
        )

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        with closing(self._connect()) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS vehicles (
                    plate TEXT PRIMARY KEY,
                    owner TEXT,
                    test_date TEXT,
                    next_due_date TEXT
                );
                CREATE TABLE IF NOT EXISTS checks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    plate TEXT NOT NULL,
                    owner TEXT,
                    test_date TEXT,
                    next_due_date TEXT,
                    status TEXT NOT NULL,
                    days_overdue_or_remaining INTEGER,
                    checked_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS checks_checked_at_idx
                    ON checks(checked_at);
                CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    check_id INTEGER NOT NULL REFERENCES checks(id),
                    plate TEXT NOT NULL,
                    level TEXT NOT NULL CHECK(level IN ('critical', 'warning')),
                    message TEXT NOT NULL,
                    days_overdue_or_remaining INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    seen_count INTEGER NOT NULL DEFAULT 1,
                    acknowledged INTEGER NOT NULL DEFAULT 0,
                    acknowledged_at TEXT,
                    ack_note TEXT
                );
                CREATE INDEX IF NOT EXISTS alerts_state_level_created_idx
                    ON alerts(acknowledged, level, created_at DESC);
                CREATE UNIQUE INDEX IF NOT EXISTS alerts_one_open_per_plate_level
                    ON alerts(plate, level) WHERE acknowledged = 0;
                """
            )

    def seed_fleet_if_empty(self) -> None:
        with closing(self._connect()) as connection:
            count = connection.execute("SELECT COUNT(*) FROM vehicles").fetchone()[0]
            if count == 0:
                today = date.today()
                from datetime import timedelta
                seed_data = [
                    ("DL3CBD3885", "Northern Highway Logistics", (today - timedelta(days=210)).isoformat(), (today + timedelta(days=155)).isoformat()),
                    ("DL3CCT8408", "Apex Logistics Ltd", (today - timedelta(days=180)).isoformat(), (today + timedelta(days=185)).isoformat()),
                    ("DL01AB1234", "Delhi Green Mobility", (today - timedelta(days=400)).isoformat(), (today - timedelta(days=35)).isoformat()),
                    ("DL01AB2345", "Northern Gas Carriers", (today - timedelta(days=350)).isoformat(), (today + timedelta(days=15)).isoformat()),
                    ("DL01AB3456", "Urban Fleet Services", (today - timedelta(days=120)).isoformat(), (today + timedelta(days=245)).isoformat()),
                    ("MH12AB1234", "Maharashtra Express Cargo", (today - timedelta(days=380)).isoformat(), (today - timedelta(days=15)).isoformat()),
                    ("HR26DQ5555", "National Eco Haulage", (today - timedelta(days=360)).isoformat(), (today + timedelta(days=5)).isoformat()),
                    ("KA01MJ9999", "Bangalore Gas Lines", (today - timedelta(days=90)).isoformat(), (today + timedelta(days=275)).isoformat()),
                ]
                connection.executemany(
                    "INSERT INTO vehicles (plate, owner, test_date, next_due_date) VALUES (?, ?, ?, ?)",
                    seed_data,
                )

    @staticmethod
    def _now() -> str:
        return datetime.now().astimezone().isoformat()

    @staticmethod
    def _as_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
        return dict(row) if row is not None else None

    def get_vehicle(self, plate: str) -> dict[str, Any] | None:
        with closing(self._connect()) as connection:
            return self._as_dict(
                connection.execute(
                    "SELECT plate, owner, test_date, next_due_date FROM vehicles WHERE plate = ?",
                    (plate,),
                ).fetchone()
            )

    def record_check(
        self,
        *,
        plate: str,
        owner: str | None,
        test_date: str | None,
        next_due_date: str | None,
        status: str,
        days_overdue_or_remaining: int | None,
        alert_level: str | None,
        alert_message: str | None,
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        now = self._now()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """
                INSERT INTO checks (
                    plate, owner, test_date, next_due_date, status,
                    days_overdue_or_remaining, checked_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    plate,
                    owner,
                    test_date,
                    next_due_date,
                    status,
                    days_overdue_or_remaining,
                    now,
                ),
            )
            check_id = cursor.lastrowid
            check = self._as_dict(
                connection.execute(
                    "SELECT * FROM checks WHERE id = ?", (check_id,)
                ).fetchone()
            )
            alert = None
            if alert_level is not None and alert_message is not None:
                existing = connection.execute(
                    """
                    SELECT * FROM alerts
                    WHERE plate = ? AND level = ? AND acknowledged = 0
                    """,
                    (plate, alert_level),
                ).fetchone()
                if existing is None:
                    alert_cursor = connection.execute(
                        """
                        INSERT INTO alerts (
                            check_id, plate, level, message,
                            days_overdue_or_remaining, created_at, last_seen_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            check_id,
                            plate,
                            alert_level,
                            alert_message,
                            days_overdue_or_remaining,
                            now,
                            now,
                        ),
                    )
                    alert_id = alert_cursor.lastrowid
                else:
                    alert_id = existing["id"]
                    connection.execute(
                        """
                        UPDATE alerts
                        SET check_id = ?, message = ?,
                            days_overdue_or_remaining = ?, last_seen_at = ?,
                            seen_count = seen_count + 1
                        WHERE id = ?
                        """,
                        (
                            check_id,
                            alert_message,
                            days_overdue_or_remaining,
                            now,
                            alert_id,
                        ),
                    )
                alert = self._as_dict(
                    connection.execute(
                        "SELECT * FROM alerts WHERE id = ?", (alert_id,)
                    ).fetchone()
                )
            connection.commit()
            if check is None:
                raise RuntimeError("The recorded hydrotest check could not be read.")
            return check, alert
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def list_alerts(
        self,
        *,
        state: str,
        level: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[dict[str, Any]], int, dict[str, int]]:
        conditions: list[str] = []
        parameters: list[Any] = []
        if state != "all":
            conditions.append("acknowledged = ?")
            parameters.append(1 if state == "acknowledged" else 0)
        if level is not None:
            conditions.append("level = ?")
            parameters.append(level)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        offset = (page - 1) * page_size
        with closing(self._connect()) as connection:
            items = [
                dict(row)
                for row in connection.execute(
                    f"""
                    SELECT * FROM alerts {where}
                    ORDER BY CASE level WHEN 'critical' THEN 0 ELSE 1 END,
                             last_seen_at DESC, id DESC
                    LIMIT ? OFFSET ?
                    """,
                    (*parameters, page_size, offset),
                ).fetchall()
            ]
            total = connection.execute(
                f"SELECT COUNT(*) FROM alerts {where}", parameters
            ).fetchone()[0]
            open_rows = connection.execute(
                """
                SELECT level, COUNT(*) AS count
                FROM alerts WHERE acknowledged = 0 GROUP BY level
                """
            ).fetchall()
        summary = {"open_critical": 0, "open_warning": 0}
        for row in open_rows:
            summary[f"open_{row['level']}"] = row["count"]
        return items, total, summary

    def get_alert(self, alert_id: int) -> dict[str, Any] | None:
        with closing(self._connect()) as connection:
            return self._as_dict(
                connection.execute(
                    "SELECT * FROM alerts WHERE id = ?", (alert_id,)
                ).fetchone()
            )

    def acknowledge_alert(self, alert_id: int, note: str | None) -> dict[str, Any] | None:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            alert = connection.execute(
                "SELECT * FROM alerts WHERE id = ?", (alert_id,)
            ).fetchone()
            if alert is None:
                connection.commit()
                return None
            if not alert["acknowledged"]:
                connection.execute(
                    """
                    UPDATE alerts
                    SET acknowledged = 1, acknowledged_at = ?, ack_note = ?
                    WHERE id = ?
                    """,
                    (self._now(), note, alert_id),
                )
            updated = self._as_dict(
                connection.execute(
                    "SELECT * FROM alerts WHERE id = ?", (alert_id,)
                ).fetchone()
            )
            connection.commit()
            return updated
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def dashboard_data(self, today: date) -> dict[str, Any]:
        with closing(self._connect()) as connection:
            today_rows = connection.execute(
                """
                SELECT status, COUNT(*) AS count FROM checks
                WHERE substr(checked_at, 1, 10) = ?
                GROUP BY status
                """,
                (today.isoformat(),),
            ).fetchall()
            open_alert_rows = connection.execute(
                """
                SELECT level, COUNT(*) AS count FROM alerts
                WHERE acknowledged = 0 GROUP BY level
                """
            ).fetchall()
            recent_alerts = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT * FROM alerts WHERE acknowledged = 0
                    ORDER BY CASE level WHEN 'critical' THEN 0 ELSE 1 END,
                             last_seen_at DESC, id DESC
                    LIMIT 5
                    """
                ).fetchall()
            ]
            vehicles = [
                dict(row)
                for row in connection.execute(
                    "SELECT plate, owner, test_date, next_due_date FROM vehicles"
                ).fetchall()
            ]
        return {
            "today": {row["status"]: row["count"] for row in today_rows},
            "open_alerts": {row["level"]: row["count"] for row in open_alert_rows},
            "recent_alerts": recent_alerts,
            "vehicles": vehicles,
        }
