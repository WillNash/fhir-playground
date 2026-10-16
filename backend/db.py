"""
SQLite persistence layer for raw clinical records.
The FHIR store is separate (fhir_store.py).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypedDict

# ---------------------------------------------------------------------------
# Path / connection
# ---------------------------------------------------------------------------

import os

_DB_PATH: Path = Path(
    os.environ.get(
        "DB_PATH",
        Path(__file__).parent.parent / "data" / "clinical.db",
    )
)


def _get_conn() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


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
    with _get_conn() as conn:
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
    """
    Insert a new patient record.

    ``record_dict`` is mutated in place (timestamps added) and returned.
    The full dict — including timestamps — is stored as the payload so that
    the payload always mirrors the canonical record state.
    """
    now = _now()
    record_dict["created_at"] = now
    record_dict["updated_at"] = now

    with _get_conn() as conn:
        conn.execute(
            """
            INSERT INTO patient_records
                (record_id, nhi_number, family_name, given_names, date_of_birth,
                 sex, encounter_date, encounter_type, payload, created_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                record_dict["record_id"],
                record_dict.get("nhi_number"),
                record_dict["family_name"],
                record_dict["given_names"],
                record_dict["date_of_birth"],
                record_dict["sex"],
                record_dict["encounter_date"],
                record_dict.get("encounter_type", "ambulatory"),
                json.dumps(record_dict),
                now,
                now,
            ),
        )

    record_dict["fhir_bundle_id"] = None
    return record_dict


def get_record(record_id: str) -> dict[str, Any] | None:
    with _get_conn() as conn:
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

    with _get_conn() as conn:
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
    with _get_conn() as conn:
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

    with _get_conn() as conn:
        rows = conn.execute(
            f"SELECT payload, fhir_bundle_id FROM patient_records"
            f" {where}"
            f" ORDER BY encounter_date DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()

    return [_row_to_dict(row) for row in rows]


def set_fhir_bundle_id(record_id: str, bundle_id: str) -> None:
    """Link a FHIR Bundle to an existing patient record."""
    with _get_conn() as conn:
        conn.execute(
            "UPDATE patient_records SET fhir_bundle_id = ? WHERE record_id = ?",
            (bundle_id, record_id),
        )


def count_records() -> int:
    with _get_conn() as conn:
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
