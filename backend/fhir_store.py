"""
FHIR R4 persistence layer.

Bundles are stored as JSON files under data/fhir_store/<id>.json
An SQLite index table allows search by resource type, patient id, and date.
"""
import sqlite3
import json
import os
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

FHIR_DIR = os.environ.get("FHIR_DIR", os.path.join(os.path.dirname(__file__), "..", "data", "fhir_store"))
INDEX_DB = os.environ.get("FHIR_INDEX_DB", os.path.join(os.path.dirname(__file__), "..", "data", "fhir_index.db"))


def _get_index_conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(os.path.abspath(INDEX_DB)), exist_ok=True)
    conn = sqlite3.connect(INDEX_DB, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_fhir_store() -> None:
    os.makedirs(FHIR_DIR, exist_ok=True)
    with _get_index_conn() as conn:
        conn.executescript("""
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
            CREATE INDEX IF NOT EXISTS idx_fhir_nhi ON fhir_index (nhi_number);
            CREATE INDEX IF NOT EXISTS idx_fhir_type ON fhir_index (resource_type);
            CREATE INDEX IF NOT EXISTS idx_fhir_date ON fhir_index (date);
            CREATE INDEX IF NOT EXISTS idx_fhir_record ON fhir_index (record_id);
        """)
    _purge_orphaned_index_entries()


def save_resource(resource: Dict[str, Any], record_id: Optional[str] = None) -> str:
    """Persist a single FHIR resource (or Bundle) and index it."""
    resource_id = resource.get("id")
    if not resource_id:
        raise ValueError("FHIR resource must have an id field")

    resource_type = resource.get("resourceType", "Unknown")
    os.makedirs(FHIR_DIR, exist_ok=True)
    path = os.path.join(FHIR_DIR, f"{resource_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(resource, f, indent=2, ensure_ascii=False)

    # Extract index fields
    patient_id = None
    nhi_number = None
    date_val = None
    subject_name = None

    if resource_type == "Bundle":
        for entry in resource.get("entry", []):
            r = entry.get("resource", {})
            if r.get("resourceType") == "Patient":
                patient_id = r.get("id")
                for ident in r.get("identifier", []):
                    if "nhi-id" in ident.get("system", ""):
                        nhi_number = ident.get("value")
                names = r.get("name", [])
                if names:
                    given = " ".join(names[0].get("given", []))
                    family = names[0].get("family", "")
                    subject_name = f"{given} {family}".strip()
                break
        date_val = resource.get("timestamp", _now())[:10]
        summary = f"Bundle for {subject_name or 'unknown'} on {date_val}"

    elif resource_type == "Patient":
        patient_id = resource.get("id")
        for ident in resource.get("identifier", []):
            if "nhi-id" in ident.get("system", ""):
                nhi_number = ident.get("value")
        names = resource.get("name", [])
        if names:
            given = " ".join(names[0].get("given", []))
            family = names[0].get("family", "")
            subject_name = f"{given} {family}".strip()
        date_val = _now()[:10]
        summary = f"Patient: {subject_name}"

    else:
        subject_ref = resource.get("subject", resource.get("patient", {}))
        if isinstance(subject_ref, dict):
            ref_str = subject_ref.get("reference", "")
            patient_id = ref_str.replace("Patient/", "") if ref_str.startswith("Patient/") else ref_str
        date_val = (
            resource.get("effectiveDateTime")
            or resource.get("performedDateTime")
            or resource.get("occurrenceDateTime")
            or resource.get("authoredOn")
            or resource.get("recordedDate")
            or resource.get("date")
            or _now()
        )[:10]

        if resource_type == "Observation":
            code_obj = resource.get("code", {})
            label = (
                code_obj.get("text")
                or (code_obj.get("coding") or [{}])[0].get("display")
                or resource_type
            )
            vq = resource.get("valueQuantity", {})
            if vq:
                summary = f"{label}: {vq.get('value', '')} {vq.get('unit', '')}".strip()
            elif resource.get("valueCodeableConcept"):
                vcc = resource["valueCodeableConcept"]
                val_text = vcc.get("text") or (vcc.get("coding") or [{}])[0].get("display", "")
                summary = f"{label}: {val_text}".strip()
            else:
                summary = label
        elif resource_type == "Condition":
            code_obj = resource.get("code", {})
            summary = code_obj.get("text") or (code_obj.get("coding") or [{}])[0].get("display") or resource_type
        elif resource_type == "MedicationStatement":
            med_obj = resource.get("medicationCodeableConcept", {})
            summary = med_obj.get("text") or (med_obj.get("coding") or [{}])[0].get("display") or resource_type
        elif resource_type == "AllergyIntolerance":
            code_obj = resource.get("code", {})
            summary = code_obj.get("text") or (code_obj.get("coding") or [{}])[0].get("display") or resource_type
        elif resource_type == "Immunization":
            vc = resource.get("vaccineCode", {})
            summary = vc.get("text") or (vc.get("coding") or [{}])[0].get("display") or resource_type
        elif resource_type == "Encounter":
            cls = resource.get("class", {})
            cls_display = cls.get("display") or cls.get("code") or "Encounter"
            period_start = (resource.get("period") or {}).get("start", date_val)
            summary = f"{cls_display} on {period_start}"
        elif resource_type == "Composition":
            summary = resource.get("title") or resource_type
        else:
            summary = f"{resource_type}/{resource_id}"

    with _get_index_conn() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO fhir_index
               (id, resource_type, patient_id, nhi_number, date, subject_name, record_id, stored_at, summary)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (resource_id, resource_type, patient_id, nhi_number, date_val,
             subject_name, record_id, _now(), summary),
        )
    return resource_id


def _purge_orphaned_index_entries() -> int:
    """Remove index rows whose JSON file no longer exists. Returns count removed."""
    with _get_index_conn() as conn:
        rows = conn.execute("SELECT id FROM fhir_index").fetchall()
    orphans = [r["id"] for r in rows if not os.path.exists(os.path.join(FHIR_DIR, f"{r['id']}.json"))]
    if orphans:
        with _get_index_conn() as conn:
            conn.executemany("DELETE FROM fhir_index WHERE id = ?", [(oid,) for oid in orphans])
    return len(orphans)


def get_resource(resource_id: str) -> Optional[Dict[str, Any]]:
    path = os.path.join(FHIR_DIR, f"{resource_id}.json")
    if not os.path.exists(path):
        # Clean up the stale index entry if present
        with _get_index_conn() as conn:
            conn.execute("DELETE FROM fhir_index WHERE id = ?", (resource_id,))
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def search_resources(
    resource_type: Optional[str] = None,
    patient_id: Optional[str] = None,
    nhi_number: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    subject_name: Optional[str] = None,
    record_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """Search the FHIR index and return matching index rows (not full resources)."""
    conditions = []
    params: List[Any] = []

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

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    params += [limit, offset]

    with _get_index_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM fhir_index {where} ORDER BY date DESC LIMIT ? OFFSET ?",
            params,
        ).fetchall()

    return [dict(r) for r in rows]


def list_all_index(limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
    with _get_index_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM fhir_index ORDER BY stored_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
    return [dict(r) for r in rows]


def count_resources() -> int:
    with _get_index_conn() as conn:
        row = conn.execute("SELECT COUNT(*) as n FROM fhir_index").fetchone()
    return row["n"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
