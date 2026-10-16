"""
FHIR R4 persistence layer.

Bundles are stored as JSON files under data/fhir_store/<id>.json.
An SQLite index table allows search by resource type, patient id, and date.
"""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator, TypeAlias, TypedDict

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_HERE = Path(__file__).parent

FHIR_DIR = Path(os.environ.get("FHIR_DIR", str(_HERE / ".." / "data" / "fhir_store")))
INDEX_DB = Path(os.environ.get("FHIR_INDEX_DB", str(_HERE / ".." / "data" / "fhir_index.db")))

# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------

# Any is justified: values come from sqlite3.Row which maps to Python scalars;
# the exact types depend on the column (TEXT → str | None, INTEGER → int).
FhirResource: TypeAlias = dict[str, Any]


class FhirIndexRow(TypedDict):
    id: str
    resource_type: str
    patient_id: str | None
    nhi_number: str | None
    date: str | None
    subject_name: str | None
    record_id: str | None
    stored_at: str
    summary: str | None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_INIT_SQL = """
    CREATE TABLE IF NOT EXISTS fhir_index (
        id              TEXT PRIMARY KEY,
        resource_type   TEXT NOT NULL,
        patient_id      TEXT,
        nhi_number      TEXT,
        date            TEXT,
        subject_name    TEXT,
        record_id       TEXT,    -- link back to clinical record
        stored_at       TEXT NOT NULL,
        summary         TEXT     -- one-line human description
    );

    CREATE INDEX IF NOT EXISTS idx_fhir_patient ON fhir_index (patient_id);
    CREATE INDEX IF NOT EXISTS idx_fhir_nhi     ON fhir_index (nhi_number);
    CREATE INDEX IF NOT EXISTS idx_fhir_type    ON fhir_index (resource_type);
    CREATE INDEX IF NOT EXISTS idx_fhir_date    ON fhir_index (date);
    CREATE INDEX IF NOT EXISTS idx_fhir_record  ON fhir_index (record_id);
"""


@contextmanager
def _index_conn() -> Generator[sqlite3.Connection, None, None]:
    """Open, yield, and reliably close an SQLite connection to the index DB."""
    INDEX_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(INDEX_DB), check_same_thread=False)
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


def _now_iso() -> str:
    """Current UTC instant as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _today_iso() -> str:
    """Current UTC date as YYYY-MM-DD."""
    return datetime.now(timezone.utc).date().isoformat()


def _display_from_codeable_concept(obj: FhirResource) -> str | None:
    """
    Return the best human-readable label from a FHIR CodeableConcept dict.

    Preference order: text → first coding.display → None.
    """
    if text := obj.get("text"):
        return str(text)
    codings: list[FhirResource] = obj.get("coding") or []
    if codings:
        return codings[0].get("display")
    return None


def _patient_fields(
    resource: FhirResource,
) -> tuple[str | None, str | None, str | None]:
    """
    Extract (patient_id, nhi_number, subject_name) from a Patient resource dict.
    """
    patient_id: str | None = resource.get("id")
    nhi_number: str | None = None
    for ident in resource.get("identifier", []):
        if "nhi-id" in ident.get("system", ""):
            nhi_number = ident.get("value")
            break

    subject_name: str | None = None
    names: list[FhirResource] = resource.get("name", [])
    if names:
        given = " ".join(names[0].get("given", []))
        family: str = names[0].get("family", "")
        subject_name = f"{given} {family}".strip() or None

    return patient_id, nhi_number, subject_name


def _date_from_clinical_resource(resource: FhirResource) -> str:
    """
    Return the most appropriate YYYY-MM-DD date for a non-Bundle, non-Patient resource.

    Tries each standard FHIR date field in priority order, falling back to today.
    """
    raw: str = (
        resource.get("effectiveDateTime")
        or resource.get("performedDateTime")
        or resource.get("occurrenceDateTime")
        or resource.get("authoredOn")
        or resource.get("recordedDate")
        or resource.get("date")
        or _today_iso()
    )
    # Dates may arrive as full datetimes; keep only the date portion.
    return raw[:10]


def _patient_ref_from_resource(resource: FhirResource) -> str | None:
    """Resolve the patient_id from a subject/patient reference on a clinical resource."""
    subject_ref = resource.get("subject", resource.get("patient", {}))
    if not isinstance(subject_ref, dict):
        return None
    ref_str: str = subject_ref.get("reference", "")
    if ref_str.startswith("Patient/"):
        return ref_str.removeprefix("Patient/")
    return ref_str or None


def _summary_for_clinical_resource(
    resource: FhirResource,
    resource_type: str,
    resource_id: str,
    date_val: str,
) -> str:
    """Build a one-line human summary for a clinical resource (not Bundle/Patient)."""
    match resource_type:
        case "Observation":
            code_obj: FhirResource = resource.get("code", {})
            label = _display_from_codeable_concept(code_obj) or resource_type
            vq: FhirResource = resource.get("valueQuantity", {})
            if vq:
                return f"{label}: {vq.get('value', '')} {vq.get('unit', '')}".strip()
            vcc: FhirResource | None = resource.get("valueCodeableConcept")
            if vcc:
                val_text = _display_from_codeable_concept(vcc) or ""
                return f"{label}: {val_text}".strip()
            return label

        case "Condition" | "AllergyIntolerance":
            code_obj = resource.get("code", {})
            return _display_from_codeable_concept(code_obj) or resource_type

        case "MedicationStatement":
            med_obj: FhirResource = resource.get("medicationCodeableConcept", {})
            return _display_from_codeable_concept(med_obj) or resource_type

        case "Immunization":
            vc: FhirResource = resource.get("vaccineCode", {})
            return _display_from_codeable_concept(vc) or resource_type

        case "Encounter":
            cls: FhirResource = resource.get("class", {})
            cls_display = cls.get("display") or cls.get("code") or "Encounter"
            period_start = (resource.get("period") or {}).get("start", date_val)
            return f"{cls_display} on {period_start}"

        case "Composition":
            return resource.get("title") or resource_type

        case _:
            return f"{resource_type}/{resource_id}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def init_fhir_store() -> None:
    """Create the storage directory and index table if they do not already exist."""
    FHIR_DIR.mkdir(parents=True, exist_ok=True)
    with _index_conn() as conn:
        conn.executescript(_INIT_SQL)
    _purge_orphaned_index_entries()


def save_resource(resource: FhirResource, record_id: str | None = None) -> str:
    """
    Persist a single FHIR resource (or Bundle) to disk and update the index.

    Returns the resource id.
    Raises ValueError if the resource has no ``id`` field.
    """
    resource_id: str | None = resource.get("id")
    if not resource_id:
        raise ValueError("FHIR resource must have an id field")

    resource_type: str = resource.get("resourceType", "Unknown")

    FHIR_DIR.mkdir(parents=True, exist_ok=True)
    path = FHIR_DIR / f"{resource_id}.json"
    path.write_text(json.dumps(resource, indent=2, ensure_ascii=False), encoding="utf-8")

    # Derive index fields from the resource type.
    patient_id: str | None = None
    nhi_number: str | None = None
    date_val: str
    subject_name: str | None = None
    summary: str

    match resource_type:
        case "Bundle":
            for entry in resource.get("entry", []):
                r: FhirResource = entry.get("resource", {})
                if r.get("resourceType") == "Patient":
                    patient_id, nhi_number, subject_name = _patient_fields(r)
                    break
            date_val = (resource.get("timestamp") or _today_iso())[:10]
            summary = f"Bundle for {subject_name or 'unknown'} on {date_val}"

        case "Patient":
            patient_id, nhi_number, subject_name = _patient_fields(resource)
            date_val = _today_iso()
            summary = f"Patient: {subject_name}"

        case _:
            patient_id = _patient_ref_from_resource(resource)
            date_val = _date_from_clinical_resource(resource)
            summary = _summary_for_clinical_resource(
                resource, resource_type, resource_id, date_val
            )

    with _index_conn() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO fhir_index
                (id, resource_type, patient_id, nhi_number, date,
                 subject_name, record_id, stored_at, summary)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                resource_id,
                resource_type,
                patient_id,
                nhi_number,
                date_val,
                subject_name,
                record_id,
                _now_iso(),
                summary,
            ),
        )

    return resource_id


def get_resource(resource_id: str) -> FhirResource | None:
    """
    Load a FHIR resource from disk by id.

    Returns ``None`` if the file does not exist, and removes any stale index entry.
    """
    path = FHIR_DIR / f"{resource_id}.json"
    if not path.exists():
        with _index_conn() as conn:
            conn.execute("DELETE FROM fhir_index WHERE id = ?", (resource_id,))
        return None
    return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[return-value]  # external JSON


def search_resources(
    resource_type: str | None = None,
    patient_id: str | None = None,
    nhi_number: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    subject_name: str | None = None,
    record_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[FhirIndexRow]:
    """
    Search the FHIR index and return matching rows (not full resources).

    All parameters are ANDed together. ``subject_name`` is a case-insensitive
    substring match; all others are exact.
    """
    conditions: list[str] = []
    params: list[Any] = []  # sqlite3 parameterisation mixes str and int

    if resource_type:
        conditions.append("resource_type = ?")
        params.append(resource_type)
    if patient_id:
        conditions.append("patient_id = ?")
        params.append(patient_id)
    if nhi_number:
        conditions.append("nhi_number = ?")
        params.append(nhi_number)
    if date_from:
        conditions.append("date >= ?")
        params.append(date_from)
    if date_to:
        conditions.append("date <= ?")
        params.append(date_to)
    if subject_name:
        conditions.append("LOWER(subject_name) LIKE ?")
        params.append(f"%{subject_name.lower()}%")
    if record_id:
        conditions.append("record_id = ?")
        params.append(record_id)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params += [limit, offset]

    with _index_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM fhir_index {where} ORDER BY date DESC LIMIT ? OFFSET ?",
            params,
        ).fetchall()

    return [dict(r) for r in rows]  # type: ignore[return-value]  # sqlite3.Row → TypedDict


def list_all_index(limit: int = 100, offset: int = 0) -> list[FhirIndexRow]:
    """Return all index rows ordered by insertion time, most recent first."""
    with _index_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM fhir_index ORDER BY stored_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
    return [dict(r) for r in rows]  # type: ignore[return-value]  # sqlite3.Row → TypedDict


def count_resources() -> int:
    """Return the total number of indexed resources."""
    with _index_conn() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM fhir_index").fetchone()
    return int(row["n"])


def _purge_orphaned_index_entries() -> int:
    """
    Remove index rows whose backing JSON file no longer exists.

    Returns the number of entries removed.
    """
    with _index_conn() as conn:
        rows = conn.execute("SELECT id FROM fhir_index").fetchall()
        orphan_ids = [
            r["id"]
            for r in rows
            if not (FHIR_DIR / f"{r['id']}.json").exists()
        ]
        if orphan_ids:
            conn.executemany(
                "DELETE FROM fhir_index WHERE id = ?",
                [(oid,) for oid in orphan_ids],
            )
    return len(orphan_ids)
