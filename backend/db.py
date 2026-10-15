"""
SQLite persistence layer for raw clinical records.
The FHIR store is separate (fhir_store.py).
"""
import sqlite3
import json
import os
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "..", "data", "clinical.db"))


def _get_conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    """Create tables if they do not exist."""
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

            CREATE INDEX IF NOT EXISTS idx_nhi ON patient_records (nhi_number);
            CREATE INDEX IF NOT EXISTS idx_dob ON patient_records (date_of_birth);
            CREATE INDEX IF NOT EXISTS idx_encounter ON patient_records (encounter_date);
        """)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    """Convert a DB row to a dict, merging fhir_bundle_id into the payload."""
    data = json.loads(row["payload"])
    data["fhir_bundle_id"] = row["fhir_bundle_id"]
    return data


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def create_record(record_dict: Dict[str, Any]) -> Dict[str, Any]:
    now = _now()
    record_dict["created_at"] = now
    record_dict["updated_at"] = now
    with _get_conn() as conn:
        conn.execute(
            """INSERT INTO patient_records
               (record_id, nhi_number, family_name, given_names, date_of_birth,
                sex, encounter_date, encounter_type, payload, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
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


def get_record(record_id: str) -> Optional[Dict[str, Any]]:
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT payload, fhir_bundle_id FROM patient_records WHERE record_id = ?", (record_id,)
        ).fetchone()
    return _row_to_dict(row) if row else None


def update_record(record_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    existing = get_record(record_id)
    if not existing:
        return None
    existing.update({k: v for k, v in updates.items() if v is not None})
    existing["updated_at"] = _now()
    with _get_conn() as conn:
        conn.execute(
            """UPDATE patient_records
               SET nhi_number=?, family_name=?, given_names=?, date_of_birth=?,
                   sex=?, encounter_date=?, encounter_type=?, payload=?, updated_at=?
               WHERE record_id=?""",
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
    with _get_conn() as conn:
        c = conn.execute("DELETE FROM patient_records WHERE record_id=?", (record_id,))
    return c.rowcount > 0


def list_records(
    nhi: Optional[str] = None,
    family_name: Optional[str] = None,
    encounter_date: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    conditions = []
    params: List[Any] = []
    if nhi:
        conditions.append("nhi_number = ?")
        params.append(nhi)
    if family_name:
        conditions.append("LOWER(family_name) LIKE ?")
        params.append(f"%{family_name.lower()}%")
    if encounter_date:
        conditions.append("encounter_date = ?")
        params.append(encounter_date)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    params += [limit, offset]

    with _get_conn() as conn:
        rows = conn.execute(
            f"SELECT payload, fhir_bundle_id FROM patient_records {where} ORDER BY encounter_date DESC LIMIT ? OFFSET ?",
            params,
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def set_fhir_bundle_id(record_id: str, bundle_id: str) -> None:
    with _get_conn() as conn:
        conn.execute(
            "UPDATE patient_records SET fhir_bundle_id=? WHERE record_id=?",
            (bundle_id, record_id),
        )


def count_records() -> int:
    with _get_conn() as conn:
        row = conn.execute("SELECT COUNT(*) as n FROM patient_records").fetchone()
    return row["n"]
