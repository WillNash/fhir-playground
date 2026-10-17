"""
SQLite persistence layer — EAV schema with longitudinal patient/encounter structure.

Tables:
  patients        — one row per unique patient (NHI = key)
  arms            — REDCap study arms
  events          — REDCap events (Baseline, Follow-up 1, …)
  encounters      — one row per visit (FK → patients, FK → events)
  redcap_data     — EAV rows: (record_id, field_name, value, instance)
  audit_log       — append-only field-level change log
  redcap_metadata — data dictionary (seeded from data_dictionary.py)

The FHIR store is separate (fhir_store.py).
"""

from __future__ import annotations

import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator, TypedDict

from . import data_dictionary as _dd
from .models import MISSING_CODES

_DB_PATH: Path = Path(
    os.environ.get(
        "DB_PATH",
        Path(__file__).parent.parent / "data" / "clinical.db",
    )
)

# ---------------------------------------------------------------------------
# Known numeric EAV prefixes / fields for _assemble_record
# ---------------------------------------------------------------------------

_NUMERIC_PREFIXES = ("vitals.",)
_NUMERIC_FIELDS = frozenset({
    "lab_results.value",
    "lab_results.reference_range_low",
    "lab_results.reference_range_high",
    "social_history.pack_years",
    "social_history.alcohol_units_per_week",
})

_BOOL_FIELDS = frozenset({"social_history.lives_alone"})

# Top-level scalars stored in EAV (not in patient/encounter table columns)
_TOP_LEVEL_EAV_FIELDS = frozenset({
    "gender_identity", "sex_at_birth", "phone", "email",
    "gp_name", "gp_practice", "pho",
    "presenting_complaint", "clinician_name", "clinician_role",
    "ethnicity_codes",
})

# Repeating instrument names
_REPEATING = ("conditions", "medications", "allergies",
              "lab_results", "immunizations", "clinical_notes")


# ---------------------------------------------------------------------------
# Connection helper
# ---------------------------------------------------------------------------

@contextmanager
def _db_conn() -> Generator[sqlite3.Connection, None, None]:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Public TypedDict
# ---------------------------------------------------------------------------

class PatientRecordDict(TypedDict, total=False):
    record_id: str
    patient_id: str
    nhi_number: str
    family_name: str
    given_names: str
    date_of_birth: str
    sex: str
    encounter_date: str
    encounter_type: str
    redcap_event_name: str | None
    fhir_bundle_id: str | None
    created_at: str
    updated_at: str


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def init_db() -> None:
    """Create tables, triggers, indexes, and seed reference data."""
    with _db_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS patients (
                patient_id      TEXT PRIMARY KEY,
                nhi_number      TEXT NOT NULL UNIQUE,
                family_name     TEXT NOT NULL,
                given_names     TEXT NOT NULL,
                date_of_birth   TEXT NOT NULL,
                sex             TEXT NOT NULL,
                gender_identity TEXT,
                sex_at_birth    TEXT,
                ethnicity_codes TEXT,
                address_street  TEXT,
                address_suburb  TEXT,
                address_city    TEXT,
                address_postcode TEXT,
                address_region  TEXT,
                phone           TEXT,
                email           TEXT,
                gp_name         TEXT,
                gp_practice     TEXT,
                pho             TEXT,
                created_at      TEXT NOT NULL,
                updated_at      TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_patients_family ON patients(LOWER(family_name));

            CREATE TABLE IF NOT EXISTS arms (
                arm_id  INTEGER PRIMARY KEY AUTOINCREMENT,
                arm_num INTEGER NOT NULL,
                name    TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS events (
                event_id          INTEGER PRIMARY KEY AUTOINCREMENT,
                arm_id            INTEGER NOT NULL REFERENCES arms(arm_id),
                unique_event_name TEXT NOT NULL UNIQUE,
                event_label       TEXT NOT NULL,
                event_order       INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS encounters (
                record_id         TEXT PRIMARY KEY,
                patient_id        TEXT NOT NULL REFERENCES patients(patient_id),
                event_id          INTEGER REFERENCES events(event_id),
                redcap_event_name TEXT,
                encounter_date    TEXT NOT NULL,
                encounter_type    TEXT NOT NULL DEFAULT 'ambulatory',
                fhir_bundle_id    TEXT,
                is_deleted        INTEGER NOT NULL DEFAULT 0,
                created_at        TEXT NOT NULL,
                updated_at        TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_enc_patient ON encounters(patient_id);
            CREATE INDEX IF NOT EXISTS idx_enc_date    ON encounters(encounter_date);
            CREATE INDEX IF NOT EXISTS idx_enc_event   ON encounters(event_id);

            CREATE TABLE IF NOT EXISTS redcap_data (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                record_id  TEXT    NOT NULL REFERENCES encounters(record_id),
                field_name TEXT    NOT NULL,
                value      TEXT,
                instance   INTEGER NOT NULL DEFAULT 0,
                UNIQUE (record_id, field_name, instance)
            );
            CREATE INDEX IF NOT EXISTS idx_rd_record ON redcap_data(record_id);

            CREATE TABLE IF NOT EXISTS audit_log (
                log_id      INTEGER PRIMARY KEY AUTOINCREMENT,
                ts          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                username    TEXT NOT NULL DEFAULT 'system',
                record_id   TEXT,
                field_name  TEXT,
                old_value   TEXT,
                new_value   TEXT,
                action      TEXT NOT NULL,
                description TEXT
            );

            CREATE TRIGGER IF NOT EXISTS audit_no_update
            BEFORE UPDATE ON audit_log
            BEGIN
                SELECT RAISE(ABORT, 'audit_log is append-only: UPDATE forbidden');
            END;

            CREATE TRIGGER IF NOT EXISTS audit_no_delete
            BEFORE DELETE ON audit_log
            BEGIN
                SELECT RAISE(ABORT, 'audit_log is append-only: DELETE forbidden');
            END;

            CREATE TABLE IF NOT EXISTS redcap_metadata (
                field_name                         TEXT PRIMARY KEY,
                form_name                          TEXT NOT NULL,
                section_header                     TEXT,
                field_type                         TEXT NOT NULL,
                field_label                        TEXT NOT NULL,
                choices_calculations_slider_labels TEXT,
                field_note                         TEXT,
                text_validation_type               TEXT,
                text_validation_min                TEXT,
                text_validation_max                TEXT,
                is_identifier                      INTEGER NOT NULL DEFAULT 0,
                branching_logic                    TEXT,
                is_required                        INTEGER NOT NULL DEFAULT 0,
                field_annotation                   TEXT,
                field_order                        INTEGER NOT NULL
            );
        """)

        # Migrate patients.nhi_number to NOT NULL UNIQUE if upgrading from older schema
        pragma = conn.execute("PRAGMA table_info(patients)").fetchall()
        nhi_col = next((c for c in pragma if c["name"] == "nhi_number"), None)
        if nhi_col is not None and nhi_col["notnull"] == 0:
            conn.execute("PRAGMA foreign_keys=OFF")
            conn.execute("""
                CREATE TABLE patients_v2 (
                    patient_id      TEXT PRIMARY KEY,
                    nhi_number      TEXT NOT NULL UNIQUE,
                    family_name     TEXT NOT NULL,
                    given_names     TEXT NOT NULL,
                    date_of_birth   TEXT NOT NULL,
                    sex             TEXT NOT NULL,
                    gender_identity TEXT,
                    sex_at_birth    TEXT,
                    ethnicity_codes TEXT,
                    address_street  TEXT,
                    address_suburb  TEXT,
                    address_city    TEXT,
                    address_postcode TEXT,
                    address_region  TEXT,
                    phone           TEXT,
                    email           TEXT,
                    gp_name         TEXT,
                    gp_practice     TEXT,
                    pho             TEXT,
                    created_at      TEXT NOT NULL,
                    updated_at      TEXT NOT NULL
                )
            """)
            conn.execute("""
                INSERT OR IGNORE INTO patients_v2
                    (patient_id, nhi_number, family_name, given_names,
                     date_of_birth, sex, created_at, updated_at)
                SELECT patient_id, nhi_number, family_name, given_names,
                       date_of_birth, sex, created_at, updated_at
                FROM patients WHERE nhi_number IS NOT NULL
            """)
            conn.execute("DROP TABLE patients")
            conn.execute("ALTER TABLE patients_v2 RENAME TO patients")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_patients_family ON patients(LOWER(family_name))"
            )
            conn.execute("PRAGMA foreign_keys=ON")

        # Migrate: add extended demographic columns to patients if not present
        existing_cols = {c["name"] for c in conn.execute("PRAGMA table_info(patients)").fetchall()}
        _new_patient_cols = [
            ("gender_identity",  "TEXT"),
            ("sex_at_birth",     "TEXT"),
            ("ethnicity_codes",  "TEXT"),
            ("address_street",   "TEXT"),
            ("address_suburb",   "TEXT"),
            ("address_city",     "TEXT"),
            ("address_postcode", "TEXT"),
            ("address_region",   "TEXT"),
            ("phone",            "TEXT"),
            ("email",            "TEXT"),
            ("gp_name",          "TEXT"),
            ("gp_practice",      "TEXT"),
            ("pho",              "TEXT"),
        ]
        for col_name, col_type in _new_patient_cols:
            if col_name not in existing_cols:
                conn.execute(f"ALTER TABLE patients ADD COLUMN {col_name} {col_type}")

        # Seed arm
        conn.execute("INSERT OR IGNORE INTO arms (arm_num, name) VALUES (1, 'Arm 1')")

        # Seed events
        arm_row = conn.execute("SELECT arm_id FROM arms WHERE arm_num=1").fetchone()
        arm_id = arm_row["arm_id"] if arm_row else 1
        for ev in _dd.EVENTS:
            conn.execute(
                "INSERT OR IGNORE INTO events "
                "(event_id, arm_id, unique_event_name, event_label, event_order) "
                "VALUES (?, ?, ?, ?, ?)",
                (ev["event_id"], arm_id, ev["unique_event_name"],
                 ev["event_label"], ev["event_order"]),
            )

        # Seed redcap_metadata
        for idx, f in enumerate(_dd.DATA_DICTIONARY):
            conn.execute(
                """
                INSERT OR IGNORE INTO redcap_metadata (
                    field_name, form_name, section_header, field_type, field_label,
                    choices_calculations_slider_labels, field_note,
                    text_validation_type, text_validation_min, text_validation_max,
                    is_identifier, branching_logic, is_required, field_annotation, field_order
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f["variable_field_name"],
                    f["form_name"],
                    f.get("section_header") or None,
                    f["field_type"],
                    f["field_label"],
                    f.get("choices_calculations_slider_labels") or None,
                    f.get("field_note") or None,
                    f.get("text_validation_type_or_show_slider_number") or None,
                    f.get("text_validation_min") or None,
                    f.get("text_validation_max") or None,
                    1 if f.get("identifier") == "y" else 0,
                    f.get("branching_logic") or None,
                    1 if f.get("required_field") == "y" else 0,
                    f.get("field_annotation") or None,
                    idx,
                ),
            )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _coerce_value(dotted_key: str, raw: str | None) -> Any:
    """Convert a raw EAV string to the appropriate Python type."""
    if raw is None:
        return None
    if dotted_key in _BOOL_FIELDS:
        return raw == "1"
    # Numeric fields — but pass missing codes through as strings
    is_numeric = (
        any(dotted_key.startswith(pfx) for pfx in _NUMERIC_PREFIXES)
        or dotted_key in _NUMERIC_FIELDS
    )
    if is_numeric:
        if raw in MISSING_CODES:
            return raw  # missing code string, not a number
        try:
            return float(raw)
        except (ValueError, TypeError):
            return raw
    return raw


def _flatten_record(record_dict: dict[str, Any]):
    """Yield (field_name, value_str, instance) for all storable fields.

    For non-repeating fields, instance=0 (not NULL) to ensure ON CONFLICT upsert
    works correctly (SQLite treats NULL as distinct from every other NULL in UNIQUE
    constraints, so two NULLs won't conflict).
    Repeating fields use 1-based positive integers.
    """
    skip = frozenset({
        "record_id", "patient_id", "fhir_bundle_id",
        "created_at", "updated_at",
    })
    # Encounter-level scalars stored as table columns (not EAV)
    encounter_cols = frozenset({
        "encounter_date", "encounter_type", "redcap_event_name",
        "family_name", "given_names", "nhi_number",
        "date_of_birth", "sex",
    })

    for key, v in record_dict.items():
        if key in skip or key in encounter_cols:
            continue
        if key == "address" and isinstance(v, dict):
            for ak, av in v.items():
                yield (f"address.{ak}", str(av) if av is not None else None, 0)
        elif key == "vitals" and isinstance(v, dict):
            for vk, vv in v.items():
                yield (f"vitals.{vk}", str(vv) if vv is not None else None, 0)
        elif key == "social_history" and isinstance(v, dict):
            for sk, sv in v.items():
                if isinstance(sv, bool):
                    yield (f"social_history.{sk}", "1" if sv else "0", 0)
                else:
                    yield (f"social_history.{sk}", str(sv) if sv is not None else None, 0)
        elif key == "ethnicity_codes" and isinstance(v, list):
            yield ("ethnicity_codes", "|".join(v) if v else None, 0)
        elif key in _REPEATING and isinstance(v, list):
            for idx, item in enumerate(v, start=1):
                if isinstance(item, dict):
                    for fk, fv in item.items():
                        if isinstance(fv, bool):
                            yield (f"{key}.{fk}", "1" if fv else "0", idx)
                        else:
                            yield (f"{key}.{fk}", str(fv) if fv is not None else None, idx)
        elif isinstance(v, (str, int, float, bool)):
            if isinstance(v, bool):
                yield (key, "1" if v else "0", 0)
            else:
                yield (key, str(v) if v is not None else None, 0)
        elif v is None:
            yield (key, None, 0)


def _assemble_record(
    patient_row: sqlite3.Row,
    encounter_row: sqlite3.Row,
    eav_rows: list[sqlite3.Row],
) -> dict[str, Any]:
    """Reconstruct the nested record dict from table rows + EAV rows."""
    pr = dict(patient_row)
    er = dict(encounter_row)

    result: dict[str, Any] = {
        # From encounter
        "record_id":         er["record_id"],
        "patient_id":        er["patient_id"],
        "encounter_date":    er["encounter_date"],
        "encounter_type":    er["encounter_type"],
        "redcap_event_name": er.get("redcap_event_name"),
        "fhir_bundle_id":    er.get("fhir_bundle_id"),
        "created_at":        er["created_at"],
        "updated_at":        er["updated_at"],
        # From patient
        "nhi_number":        pr.get("nhi_number"),
        "family_name":       pr["family_name"],
        "given_names":       pr["given_names"],
        "date_of_birth":     pr["date_of_birth"],
        "sex":               pr["sex"],
        # Defaults for nested structures
        "gender_identity":   None,
        "sex_at_birth":      None,
        "ethnicity_codes":   [],
        "address":           {},
        "phone":             None,
        "email":             None,
        "gp_name":           None,
        "gp_practice":       None,
        "pho":               None,
        "presenting_complaint": None,
        "clinician_name":    None,
        "clinician_role":    None,
        "vitals":            {},
        "conditions":        [],
        "medications":       [],
        "allergies":         [],
        "lab_results":       [],
        "immunizations":     [],
        "social_history":    {},
        "clinical_notes":    [],
    }

    # Patient extended demographics take precedence over EAV defaults.
    # For old records these columns are NULL so EAV fallback still applies.
    for col in ("gender_identity", "sex_at_birth", "phone", "email",
                "gp_name", "gp_practice", "pho"):
        val = pr.get(col)
        if val is not None:
            result[col] = val
    if pr.get("ethnicity_codes"):
        result["ethnicity_codes"] = [c for c in pr["ethnicity_codes"].split("|") if c]
    addr_from_cols = {
        "street":   pr.get("address_street"),
        "suburb":   pr.get("address_suburb"),
        "city":     pr.get("address_city"),
        "postcode": pr.get("address_postcode"),
        "region":   pr.get("address_region"),
    }
    if any(v is not None for v in addr_from_cols.values()):
        result["address"] = addr_from_cols

    # Group repeating EAV rows by (instrument, instance)
    repeating_groups: dict[str, dict[int, dict[str, Any]]] = {
        k: {} for k in _REPEATING
    }

    for row in eav_rows:
        fn: str = row["field_name"]
        raw: str | None = row["value"]
        instance: int = row["instance"] if row["instance"] is not None else 0

        if fn == "ethnicity_codes":
            result["ethnicity_codes"] = [c for c in (raw or "").split("|") if c]
            continue

        if "." in fn:
            prefix, rest = fn.split(".", 1)
        else:
            prefix, rest = fn, fn

        if prefix == "address":
            result["address"][rest] = raw
        elif prefix == "vitals":
            result["vitals"][rest] = _coerce_value(fn, raw)
        elif prefix == "social_history":
            result["social_history"][rest] = _coerce_value(fn, raw)
        elif prefix in _REPEATING and instance > 0:
            # instance=0 means non-repeating; instance>=1 means repeating
            grp = repeating_groups[prefix]
            if instance not in grp:
                grp[instance] = {}
            grp[instance][rest] = _coerce_value(fn, raw)
        elif prefix == fn and instance == 0:
            # Plain top-level field (gender_identity, phone, etc.)
            result[fn] = _coerce_value(fn, raw)

    # Sort and flatten repeating groups into lists
    for key in _REPEATING:
        grp = repeating_groups[key]
        result[key] = [grp[i] for i in sorted(grp)]

    # Return None for completely empty sub-dicts
    if result["vitals"] and all(v is None for v in result["vitals"].values()):
        result["vitals"] = None
    elif not result["vitals"]:
        result["vitals"] = None

    if result["social_history"] and all(v is None for v in result["social_history"].values()):
        result["social_history"] = None
    elif not result["social_history"]:
        result["social_history"] = None

    if not result["address"] or all(v is None for v in result["address"].values()):
        result["address"] = None

    return result


def _upsert_eav(conn: sqlite3.Connection, record_id: str, triples) -> None:
    """Write EAV rows using ON CONFLICT DO UPDATE (never INSERT OR REPLACE)."""
    for field_name, value, instance in triples:
        conn.execute(
            """
            INSERT INTO redcap_data (record_id, field_name, value, instance)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (record_id, field_name, instance)
            DO UPDATE SET value = excluded.value
            """,
            (record_id, field_name, value, instance),
        )


def _audit(conn: sqlite3.Connection, action: str, record_id: str | None = None,
           field_name: str | None = None, old_value: str | None = None,
           new_value: str | None = None, description: str | None = None) -> None:
    conn.execute(
        "INSERT INTO audit_log (action, record_id, field_name, old_value, new_value, description) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (action, record_id, field_name, old_value, new_value, description),
    )


def _lookup_event_id(conn: sqlite3.Connection, event_name: str | None) -> int | None:
    if not event_name:
        return None
    row = conn.execute(
        "SELECT event_id FROM events WHERE unique_event_name=?", (event_name,)
    ).fetchone()
    return row["event_id"] if row else None


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def create_record(record_dict: dict[str, Any]) -> dict[str, Any]:
    now = _now()  # defined first — both the encounter-only and NHI-upsert paths use it

    # Encounter-only path: patient already exists, referenced by patient_id
    explicit_patient_id = record_dict.get("patient_id")
    if explicit_patient_id:
        with _db_conn() as conn:
            if not conn.execute(
                "SELECT 1 FROM patients WHERE patient_id=?", (explicit_patient_id,)
            ).fetchone():
                raise ValueError(f"Patient not found: {explicit_patient_id}")
            patient_id: str = explicit_patient_id
            event_name = record_dict.get("redcap_event_name") or "baseline_arm_1"
            event_id = _lookup_event_id(conn, event_name)
            if event_id is None:
                baseline = conn.execute(
                    "SELECT event_id FROM events WHERE unique_event_name='baseline_arm_1'"
                ).fetchone()
                event_id = baseline["event_id"] if baseline else None
            record_id = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO encounters (record_id, patient_id, event_id, redcap_event_name, "
                "encounter_date, encounter_type, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
                (record_id, patient_id, event_id, event_name,
                 record_dict["encounter_date"],
                 record_dict.get("encounter_type", "ambulatory"),
                 now, now),
            )
            _upsert_eav(conn, record_id, _flatten_record(record_dict))
            _audit(conn, "record_add", record_id=record_id, description="Record created")
            p_row = conn.execute("SELECT * FROM patients WHERE patient_id=?", (patient_id,)).fetchone()
            e_row = conn.execute("SELECT * FROM encounters WHERE record_id=?", (record_id,)).fetchone()
            eav_rows = conn.execute(
                "SELECT field_name, value, instance FROM redcap_data WHERE record_id=?", (record_id,)
            ).fetchall()
        return _assemble_record(p_row, e_row, eav_rows)

    with _db_conn() as conn:
        # Patient deduplication by NHI — NHI is required so always present
        nhi: str = record_dict["nhi_number"]
        row = conn.execute(
            "SELECT patient_id FROM patients WHERE nhi_number=?", (nhi,)
        ).fetchone()
        if row:
            patient_id: str = row["patient_id"]
            conn.execute(
                "UPDATE patients SET family_name=?, given_names=?, date_of_birth=?, "
                "sex=?, updated_at=? WHERE patient_id=?",
                (record_dict["family_name"], record_dict["given_names"],
                 record_dict["date_of_birth"], record_dict["sex"],
                 now, patient_id),
            )
        else:
            patient_id = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO patients (patient_id, nhi_number, family_name, given_names, "
                "date_of_birth, sex, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
                (patient_id, nhi, record_dict["family_name"], record_dict["given_names"],
                 record_dict["date_of_birth"], record_dict["sex"], now, now),
            )

        # Event lookup
        event_name = record_dict.get("redcap_event_name") or "baseline_arm_1"
        event_id = _lookup_event_id(conn, event_name)
        if event_id is None:
            # Default to baseline
            baseline = conn.execute(
                "SELECT event_id FROM events WHERE unique_event_name='baseline_arm_1'"
            ).fetchone()
            event_id = baseline["event_id"] if baseline else None

        record_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO encounters (record_id, patient_id, event_id, redcap_event_name, "
            "encounter_date, encounter_type, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
            (record_id, patient_id, event_id, event_name,
             record_dict["encounter_date"],
             record_dict.get("encounter_type", "ambulatory"),
             now, now),
        )

        # EAV
        _upsert_eav(conn, record_id, _flatten_record(record_dict))

        # Audit
        _audit(conn, "record_add", record_id=record_id, description="Record created")

        # Build the full assembled dict
        patient_row = conn.execute(
            "SELECT * FROM patients WHERE patient_id=?", (patient_id,)
        ).fetchone()
        encounter_row = conn.execute(
            "SELECT * FROM encounters WHERE record_id=?", (record_id,)
        ).fetchone()
        eav_rows = conn.execute(
            "SELECT field_name, value, instance FROM redcap_data WHERE record_id=?",
            (record_id,),
        ).fetchall()

    return _assemble_record(patient_row, encounter_row, eav_rows)


def get_record(record_id: str) -> dict[str, Any] | None:
    with _db_conn() as conn:
        enc = conn.execute(
            "SELECT e.*, p.* FROM encounters e "
            "JOIN patients p ON e.patient_id = p.patient_id "
            "WHERE e.record_id=? AND e.is_deleted=0",
            (record_id,),
        ).fetchone()
        if not enc:
            return None
        eav = conn.execute(
            "SELECT field_name, value, instance FROM redcap_data WHERE record_id=?",
            (record_id,),
        ).fetchall()
        # Build separate Row-like dicts to avoid column collision
        enc_dict = dict(enc)
        # patient_row columns are duplicated; separate them
        patient_cols = {"patient_id", "nhi_number", "family_name", "given_names",
                        "date_of_birth", "sex"}
        encounter_cols_set = {
            "record_id", "event_id", "redcap_event_name",
            "encounter_date", "encounter_type", "fhir_bundle_id",
            "is_deleted", "created_at", "updated_at",
        }
        p_row = conn.execute(
            "SELECT * FROM patients WHERE patient_id=?", (enc_dict["patient_id"],)
        ).fetchone()
        e_row = conn.execute(
            "SELECT * FROM encounters WHERE record_id=?", (record_id,)
        ).fetchone()

    return _assemble_record(p_row, e_row, eav)


def update_record(record_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
    existing = get_record(record_id)
    if existing is None:
        return None

    # Deep merge
    merged = dict(existing)
    for key, val in updates.items():
        if isinstance(val, dict) and isinstance(merged.get(key), dict):
            merged[key] = {**merged[key], **val}
        else:
            merged[key] = val

    now = _now()

    with _db_conn() as conn:
        # Current EAV map for diffing
        old_eav_rows = conn.execute(
            "SELECT field_name, value, instance FROM redcap_data WHERE record_id=?",
            (record_id,),
        ).fetchall()
        old_map: dict[tuple, str | None] = {
            (row["field_name"], row["instance"] if row["instance"] is not None else 0): row["value"]
            for row in old_eav_rows
        }

        # Flatten merged
        new_triples = list(_flatten_record(merged))

        # Audit changed fields
        for fn, new_val, instance in new_triples:
            old_val = old_map.get((fn, instance))
            if old_val != new_val:
                _audit(conn, "record_edit", record_id=record_id,
                       field_name=fn, old_value=old_val, new_value=new_val)

        # Upsert EAV
        _upsert_eav(conn, record_id, new_triples)

        # Update encounter scalars if changed
        conn.execute(
            "UPDATE encounters SET encounter_date=?, encounter_type=?, "
            "redcap_event_name=?, updated_at=? WHERE record_id=?",
            (merged.get("encounter_date", existing["encounter_date"]),
             merged.get("encounter_type", existing.get("encounter_type", "ambulatory")),
             merged.get("redcap_event_name", existing.get("redcap_event_name")),
             now, record_id),
        )
        # Update patient demographics if changed (core + extended columns)
        patient_id = existing["patient_id"]
        addr = merged.get("address") or {}
        if hasattr(addr, "model_dump"):
            addr = addr.model_dump()
        eth = merged.get("ethnicity_codes") or []
        conn.execute(
            "UPDATE patients SET family_name=?, given_names=?, date_of_birth=?, sex=?, "
            "nhi_number=?, gender_identity=?, sex_at_birth=?, ethnicity_codes=?, "
            "address_street=?, address_suburb=?, address_city=?, address_postcode=?, address_region=?, "
            "phone=?, email=?, gp_name=?, gp_practice=?, pho=?, updated_at=? WHERE patient_id=?",
            (
                merged.get("family_name", existing["family_name"]),
                merged.get("given_names", existing["given_names"]),
                merged.get("date_of_birth", existing["date_of_birth"]),
                merged.get("sex", existing["sex"]),
                merged.get("nhi_number", existing.get("nhi_number")),
                merged.get("gender_identity"),
                merged.get("sex_at_birth"),
                "|".join(eth) if eth else None,
                addr.get("street") if addr else None,
                addr.get("suburb") if addr else None,
                addr.get("city") if addr else None,
                addr.get("postcode") if addr else None,
                addr.get("region") if addr else None,
                merged.get("phone"),
                merged.get("email"),
                merged.get("gp_name"),
                merged.get("gp_practice"),
                merged.get("pho"),
                now, patient_id,
            ),
        )

        p_row = conn.execute(
            "SELECT * FROM patients WHERE patient_id=?", (patient_id,)
        ).fetchone()
        e_row = conn.execute(
            "SELECT * FROM encounters WHERE record_id=?", (record_id,)
        ).fetchone()
        eav = conn.execute(
            "SELECT field_name, value, instance FROM redcap_data WHERE record_id=?",
            (record_id,),
        ).fetchall()

    return _assemble_record(p_row, e_row, eav)


def delete_record(record_id: str) -> bool:
    now = _now()
    with _db_conn() as conn:
        cursor = conn.execute(
            "UPDATE encounters SET is_deleted=1, updated_at=? WHERE record_id=?",
            (now, record_id),
        )
        if cursor.rowcount > 0:
            _audit(conn, "record_delete", record_id=record_id,
                   description="Record soft-deleted")
            return True
    return False


def list_records(
    nhi: str | None = None,
    family_name: str | None = None,
    encounter_date: str | None = None,
    patient_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    conditions: list[str] = ["e.is_deleted=0"]
    params: list[Any] = []

    if nhi:
        conditions.append("p.nhi_number=?")
        params.append(nhi)
    if family_name:
        conditions.append("LOWER(p.family_name) LIKE ?")
        params.append(f"%{family_name.lower()}%")
    if encounter_date:
        conditions.append("e.encounter_date=?")
        params.append(encounter_date)
    if patient_id:
        conditions.append("e.patient_id=?")
        params.append(patient_id)

    where = " AND ".join(conditions)

    with _db_conn() as conn:
        enc_rows = conn.execute(
            f"SELECT e.record_id FROM encounters e "
            f"JOIN patients p ON e.patient_id=p.patient_id "
            f"WHERE {where} "
            f"ORDER BY e.encounter_date DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()

        if not enc_rows:
            return []

        record_ids = [r["record_id"] for r in enc_rows]
        placeholders = ",".join("?" * len(record_ids))

        # Bulk fetch — include extended patient demographic columns
        all_encs = conn.execute(
            f"SELECT e.*, p.patient_id as p_id, p.nhi_number, p.family_name, "
            f"p.given_names, p.date_of_birth, p.sex, "
            f"p.gender_identity as p_gender_identity, p.sex_at_birth as p_sex_at_birth, "
            f"p.ethnicity_codes as p_ethnicity_codes, "
            f"p.address_street as p_address_street, p.address_suburb as p_address_suburb, "
            f"p.address_city as p_address_city, p.address_postcode as p_address_postcode, "
            f"p.address_region as p_address_region, "
            f"p.phone as p_phone, p.email as p_email, "
            f"p.gp_name as p_gp_name, p.gp_practice as p_gp_practice, p.pho as p_pho, "
            f"p.created_at as p_created_at, p.updated_at as p_updated_at "
            f"FROM encounters e "
            f"JOIN patients p ON e.patient_id=p.patient_id "
            f"WHERE e.record_id IN ({placeholders})",
            record_ids,
        ).fetchall()

        all_eav = conn.execute(
            f"SELECT record_id, field_name, value, instance "
            f"FROM redcap_data WHERE record_id IN ({placeholders})",
            record_ids,
        ).fetchall()

    # Group EAV by record_id
    eav_map: dict[str, list] = {rid: [] for rid in record_ids}
    for row in all_eav:
        eav_map[row["record_id"]].append(row)

    # Build individual p_row / e_row from combined row
    results: list[dict[str, Any]] = []
    enc_lookup: dict[str, sqlite3.Row] = {r["record_id"]: r for r in all_encs}

    for rid in record_ids:
        row = enc_lookup.get(rid)
        if not row:
            continue

        class _FakeRow(dict):
            def __getitem__(self, k):
                return super().__getitem__(k)
            def __contains__(self, k):
                return super().__contains__(k)
            def get(self, k, default=None):
                return super().get(k, default)

        d = dict(row)
        p_row_d = {
            "patient_id":      d["patient_id"],
            "nhi_number":      d["nhi_number"],
            "family_name":     d["family_name"],
            "given_names":     d["given_names"],
            "date_of_birth":   d["date_of_birth"],
            "sex":             d["sex"],
            "gender_identity": d.get("p_gender_identity"),
            "sex_at_birth":    d.get("p_sex_at_birth"),
            "ethnicity_codes": d.get("p_ethnicity_codes"),
            "address_street":  d.get("p_address_street"),
            "address_suburb":  d.get("p_address_suburb"),
            "address_city":    d.get("p_address_city"),
            "address_postcode":d.get("p_address_postcode"),
            "address_region":  d.get("p_address_region"),
            "phone":           d.get("p_phone"),
            "email":           d.get("p_email"),
            "gp_name":         d.get("p_gp_name"),
            "gp_practice":     d.get("p_gp_practice"),
            "pho":             d.get("p_pho"),
            "created_at":      d.get("p_created_at", d.get("created_at")),
            "updated_at":      d.get("p_updated_at", d.get("updated_at")),
        }
        e_row_d = {
            "record_id":         d["record_id"],
            "patient_id":        d["patient_id"],
            "event_id":          d.get("event_id"),
            "redcap_event_name": d.get("redcap_event_name"),
            "encounter_date":    d["encounter_date"],
            "encounter_type":    d["encounter_type"],
            "fhir_bundle_id":    d.get("fhir_bundle_id"),
            "is_deleted":        d.get("is_deleted", 0),
            "created_at":        d.get("created_at"),
            "updated_at":        d.get("updated_at"),
        }

        class DictRow(dict):
            def keys(self):
                return super().keys()

        p_fake = DictRow(p_row_d)
        e_fake = DictRow(e_row_d)

        results.append(_assemble_record(p_fake, e_fake, eav_map.get(rid, [])))

    return results


def get_audit_log(record_id: str) -> list[dict[str, Any]]:
    with _db_conn() as conn:
        rows = conn.execute(
            "SELECT log_id, ts, username, record_id, field_name, old_value, new_value, "
            "action, description FROM audit_log WHERE record_id=? ORDER BY log_id ASC",
            (record_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def list_patients(
    nhi: str | None = None,
    family_name: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    conditions: list[str] = []
    params: list[Any] = []
    if nhi:
        conditions.append("p.nhi_number=?")
        params.append(nhi)
    if family_name:
        conditions.append("LOWER(p.family_name) LIKE ?")
        params.append(f"%{family_name.lower()}%")
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    with _db_conn() as conn:
        rows = conn.execute(
            f"SELECT p.patient_id, p.nhi_number, p.family_name, p.given_names, "
            f"p.date_of_birth, p.sex, "
            f"COUNT(e.record_id) as encounter_count, "
            f"MAX(e.encounter_date) as last_encounter_date "
            f"FROM patients p "
            f"LEFT JOIN encounters e ON e.patient_id=p.patient_id AND e.is_deleted=0 "
            f"{where} "
            f"GROUP BY p.patient_id "
            f"ORDER BY p.family_name "
            f"LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()
    return [dict(r) for r in rows]


def _patient_row_to_dict(row: dict[str, Any]) -> dict[str, Any]:
    """Convert a flat patient DB row (with optional encounter_count) to a clean dict."""
    codes_str = row.get("ethnicity_codes")
    codes = [c for c in (codes_str or "").split("|") if c]
    addr = {
        "street":   row.get("address_street"),
        "suburb":   row.get("address_suburb"),
        "city":     row.get("address_city"),
        "postcode": row.get("address_postcode"),
        "region":   row.get("address_region"),
    }
    return {
        "patient_id":          row["patient_id"],
        "nhi_number":          row["nhi_number"],
        "family_name":         row["family_name"],
        "given_names":         row["given_names"],
        "date_of_birth":       row["date_of_birth"],
        "sex":                 row["sex"],
        "gender_identity":     row.get("gender_identity"),
        "sex_at_birth":        row.get("sex_at_birth"),
        "ethnicity_codes":     codes,
        "address":             addr if any(v is not None for v in addr.values()) else None,
        "phone":               row.get("phone"),
        "email":               row.get("email"),
        "gp_name":             row.get("gp_name"),
        "gp_practice":         row.get("gp_practice"),
        "pho":                 row.get("pho"),
        "encounter_count":     row.get("encounter_count", 0),
        "last_encounter_date": row.get("last_encounter_date"),
        "created_at":          row.get("created_at"),
        "updated_at":          row.get("updated_at"),
    }


def _patient_with_counts_query(conn: sqlite3.Connection, patient_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT p.*, COUNT(e.record_id) as encounter_count, "
        "MAX(e.encounter_date) as last_encounter_date "
        "FROM patients p "
        "LEFT JOIN encounters e ON e.patient_id=p.patient_id AND e.is_deleted=0 "
        "WHERE p.patient_id=? GROUP BY p.patient_id",
        (patient_id,),
    ).fetchone()
    return _patient_row_to_dict(dict(row)) if row else None


def create_patient(patient_dict: dict[str, Any]) -> dict[str, Any]:
    now = _now()
    patient_id = str(uuid.uuid4())
    ethnicity_codes = patient_dict.get("ethnicity_codes") or []
    addr = patient_dict.get("address") or {}
    if hasattr(addr, "model_dump"):
        addr = addr.model_dump()

    with _db_conn() as conn:
        conn.execute(
            """INSERT INTO patients (
                patient_id, nhi_number, family_name, given_names, date_of_birth, sex,
                gender_identity, sex_at_birth, ethnicity_codes,
                address_street, address_suburb, address_city, address_postcode, address_region,
                phone, email, gp_name, gp_practice, pho,
                created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                patient_id,
                patient_dict["nhi_number"],
                patient_dict["family_name"],
                patient_dict["given_names"],
                patient_dict["date_of_birth"],
                patient_dict["sex"],
                patient_dict.get("gender_identity"),
                patient_dict.get("sex_at_birth"),
                "|".join(ethnicity_codes) if ethnicity_codes else None,
                addr.get("street") if addr else None,
                addr.get("suburb") if addr else None,
                addr.get("city") if addr else None,
                addr.get("postcode") if addr else None,
                addr.get("region") if addr else None,
                patient_dict.get("phone"),
                patient_dict.get("email"),
                patient_dict.get("gp_name"),
                patient_dict.get("gp_practice"),
                patient_dict.get("pho"),
                now, now,
            ),
        )
        _audit(conn, "patient_add", record_id=patient_id, description="Patient created")
        result = _patient_with_counts_query(conn, patient_id)
    return result  # type: ignore[return-value]


def get_patient(patient_id: str) -> dict[str, Any] | None:
    with _db_conn() as conn:
        return _patient_with_counts_query(conn, patient_id)


def update_patient(patient_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
    now = _now()
    with _db_conn() as conn:
        if not conn.execute(
            "SELECT 1 FROM patients WHERE patient_id=?", (patient_id,)
        ).fetchone():
            return None

        set_clauses: list[str] = ["updated_at=?"]
        params: list[Any] = [now]

        for col in ("nhi_number", "family_name", "given_names", "date_of_birth", "sex",
                    "gender_identity", "sex_at_birth", "phone", "email",
                    "gp_name", "gp_practice", "pho"):
            if col in updates:
                set_clauses.append(f"{col}=?")
                params.append(updates[col])

        if "ethnicity_codes" in updates:
            codes = updates["ethnicity_codes"] or []
            set_clauses.append("ethnicity_codes=?")
            params.append("|".join(codes) if codes else None)

        if "address" in updates:
            addr = updates["address"] or {}
            if hasattr(addr, "model_dump"):
                addr = addr.model_dump()
            if isinstance(addr, dict):
                for ak in ("street", "suburb", "city", "postcode", "region"):
                    if ak in addr:
                        set_clauses.append(f"address_{ak}=?")
                        params.append(addr[ak])

        params.append(patient_id)
        conn.execute(
            f"UPDATE patients SET {', '.join(set_clauses)} WHERE patient_id=?", params
        )
        _audit(conn, "patient_edit", record_id=patient_id, description="Patient updated")
        result = _patient_with_counts_query(conn, patient_id)
    return result


def delete_patient(patient_id: str) -> bool:
    with _db_conn() as conn:
        if not conn.execute(
            "SELECT 1 FROM patients WHERE patient_id=?", (patient_id,)
        ).fetchone():
            return False
        _audit(conn, "patient_delete", record_id=patient_id, description="Patient deleted")
        conn.execute(
            "DELETE FROM redcap_data WHERE record_id IN "
            "(SELECT record_id FROM encounters WHERE patient_id=?)",
            (patient_id,),
        )
        conn.execute("DELETE FROM encounters WHERE patient_id=?", (patient_id,))
        conn.execute("DELETE FROM patients WHERE patient_id=?", (patient_id,))
    return True


def set_fhir_bundle_id(record_id: str, bundle_id: str) -> None:
    with _db_conn() as conn:
        conn.execute(
            "UPDATE encounters SET fhir_bundle_id=? WHERE record_id=?",
            (bundle_id, record_id),
        )


def count_records() -> int:
    with _db_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM encounters WHERE is_deleted=0"
        ).fetchone()
    return row["n"]


__all__ = [
    "init_db",
    "create_record",
    "get_record",
    "update_record",
    "delete_record",
    "list_records",
    "get_audit_log",
    "list_patients",
    "create_patient",
    "get_patient",
    "update_patient",
    "delete_patient",
    "set_fhir_bundle_id",
    "count_records",
]
