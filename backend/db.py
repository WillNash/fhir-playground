"""
SQLite persistence layer for raw clinical records.
The FHIR store is separate (fhir_store.py).
"""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator, TypedDict

_DB_PATH: Path = Path(
    os.environ.get(
        "DB_PATH",
        Path(__file__).parent.parent / "data" / "clinical.db",
    )
)


@contextmanager
def _db_conn() -> Generator[sqlite3.Connection, None, None]:
    """Open, yield, commit/rollback, and always close an SQLite connection."""
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Public type
# ---------------------------------------------------------------------------

# `Any` values in the payload come from externally-supplied JSON whose shape
# is validated upstream (by the FHIR layer), so Any is appropriate here.
class PatientRecordDict(TypedDict, total=False):
    record_id: str
    nhi_number: str | None
    family_name: str
    given_names: str
    date_of_birth: str
    sex: str
    encounter_date: str
    encounter_type: str
    fhir_bundle_id: str | None
    created_at: str
    updated_at: str


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def init_db() -> None:
    """Create tables and indexes if they do not exist."""
    with _db_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS patient_records (
                record_id       TEXT PRIMARY KEY,
                nhi_number      TEXT,
                family_name     TEXT NOT NULL,
                given_names     TEXT NOT NULL,
                date_of_birth   TEXT NOT NULL,
                sex             TEXT NOT NULL,
                encounter_date  TEXT NOT NULL,
                encounter_type  TEXT NOT NULL DEFAULT 'ambulatory',
                payload         TEXT NOT NULL,   -- full JSON of PatientRecord
                fhir_bundle_id  TEXT,            -- linked FHIR Bundle id
                created_at      TEXT NOT NULL,
                updated_at      TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_nhi       ON patient_records (nhi_number);
            CREATE INDEX IF NOT EXISTS idx_dob       ON patient_records (date_of_birth);
            CREATE INDEX IF NOT EXISTS idx_encounter ON patient_records (encounter_date);
        """)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    """Return the payload dict for a row, with fhir_bundle_id merged in."""
    data: dict[str, Any] = json.loads(row["payload"])
    data["fhir_bundle_id"] = row["fhir_bundle_id"]
    return data


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def create_record(record_dict: dict[str, Any]) -> dict[str, Any]:
    """Insert a new patient record and return it with timestamps added."""
    now = _now()
    record = {**record_dict, "created_at": now, "updated_at": now}

    with _db_conn() as conn:
        conn.execute(
            """
            INSERT INTO patient_records
                (record_id, nhi_number, family_name, given_names, date_of_birth,
                 sex, encounter_date, encounter_type, payload, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                record["record_id"],
                record.get("nhi_number"),
                record["family_name"],
                record["given_names"],
                record["date_of_birth"],
                record["sex"],
                record["encounter_date"],
                record.get("encounter_type", "ambulatory"),
                json.dumps(record),
                now,
                now,
            ),
        )

    record["fhir_bundle_id"] = None
    return record


def get_record(record_id: str) -> dict[str, Any] | None:
    with _db_conn() as conn:
        row = conn.execute(
            "SELECT payload, fhir_bundle_id FROM patient_records WHERE record_id = ?",
            (record_id,),
        ).fetchone()
    return _row_to_dict(row) if row else None


def update_record(record_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
    """
    Merge ``updates`` into the existing record and persist.

    Fields whose value is ``None`` in ``updates`` are skipped — this
    preserves the original behaviour where callers signal "no change" with
    ``None``. Use ``set_fhir_bundle_id`` to explicitly clear that field.
    """
    existing = get_record(record_id)
    if existing is None:
        return None

    existing.update({k: v for k, v in updates.items() if v is not None})
    existing["updated_at"] = _now()

    with _db_conn() as conn:
        conn.execute(
            """
            UPDATE patient_records
               SET nhi_number=?, family_name=?, given_names=?, date_of_birth=?,
                   sex=?, encounter_date=?, encounter_type=?, payload=?, updated_at=?
             WHERE record_id=?
            """,
            (
                existing.get("nhi_number"),
                existing["family_name"],
                existing["given_names"],
                existing["date_of_birth"],
                existing["sex"],
                existing["encounter_date"],
                existing.get("encounter_type", "ambulatory"),
                json.dumps(existing),
                existing["updated_at"],
                record_id,
            ),
        )

    return existing


def delete_record(record_id: str) -> bool:
    """Return ``True`` if a row was deleted, ``False`` if it did not exist."""
    with _db_conn() as conn:
        cursor = conn.execute(
            "DELETE FROM patient_records WHERE record_id = ?", (record_id,)
        )
        return cursor.rowcount > 0


def list_records(
    nhi: str | None = None,
    family_name: str | None = None,
    encounter_date: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    conditions: list[str] = []
    params: list[Any] = []  # mixed types required by sqlite3 parameter binding

    if nhi:
        conditions.append("nhi_number = ?")
        params.append(nhi)
    if family_name:
        conditions.append("LOWER(family_name) LIKE ?")
        params.append(f"%{family_name.lower()}%")
    if encounter_date:
        conditions.append("encounter_date = ?")
        params.append(encounter_date)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    with _db_conn() as conn:
        rows = conn.execute(
            f"SELECT payload, fhir_bundle_id FROM patient_records"
            f" {where}"
            f" ORDER BY encounter_date DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()

    return [_row_to_dict(row) for row in rows]


def set_fhir_bundle_id(record_id: str, bundle_id: str) -> None:
    """Link a FHIR Bundle to an existing patient record."""
    with _db_conn() as conn:
        conn.execute(
            "UPDATE patient_records SET fhir_bundle_id = ? WHERE record_id = ?",
            (bundle_id, record_id),
        )


def count_records() -> int:
    with _db_conn() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM patient_records").fetchone()
    return row["n"]


__all__ = [
    "init_db",
    "create_record",
    "get_record",
    "update_record",
    "delete_record",
    "list_records",
    "set_fhir_bundle_id",
    "count_records",
]
