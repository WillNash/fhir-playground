# Context Explorer — REDCap Simulator Gap Analysis

> Task: Move system closer to a REDCap simulator by removing the forced clinical-encounter coupling and introducing instrument-level data submission at events, with instrument-level completion tracking.
> Analysed: 2026-10-17

---

## Files Examined

- `/workspace/active_repo/backend/db.py` (1178 lines)
- `/workspace/active_repo/backend/models.py` (349 lines)
- `/workspace/active_repo/backend/main.py` (515 lines)
- `/workspace/active_repo/backend/data_dictionary.py` (262 lines)
- `/workspace/active_repo/backend/converter.py` (first 80 lines for context)
- `/workspace/active_repo/frontend/index.html` (2994 lines)
- `/workspace/active_repo/claude-context-smells.md`

---

## 1. Database Schema (backend/db.py)

### Tables

**patients** — one row per unique patient, keyed by `patient_id` (UUID). Core demographics: `nhi_number` (NZ NHI, UNIQUE NOT NULL), `family_name`, `given_names`, `date_of_birth`, `sex`, plus extended columns: `gender_identity`, `sex_at_birth`, `ethnicity_codes` (pipe-separated), address columns, `phone`, `email`, `gp_name`, `gp_practice`, `pho`.

**arms** — single row seeded: arm_num=1, name="Arm 1".

**events** — three rows seeded from `data_dictionary.EVENTS`:
- event_id=1 `baseline_arm_1` "Baseline" order=1
- event_id=2 `followup_1_arm_1` "Follow-up 1" order=2
- event_id=3 `followup_2_arm_1` "Follow-up 2" order=3

**encounters** — the critical table. One row per "record". Columns:
- `record_id` TEXT PRIMARY KEY (UUID)
- `patient_id` FK → patients
- `event_id` FK → events (nullable)
- `redcap_event_name` TEXT (string label, denormalised alongside event_id)
- `encounter_date` TEXT NOT NULL
- `encounter_type` TEXT NOT NULL DEFAULT 'ambulatory'
- `fhir_bundle_id` TEXT
- `is_deleted` INTEGER DEFAULT 0
- `created_at`, `updated_at`

**redcap_data** — EAV store. Columns: `id`, `record_id` FK → encounters, `field_name`, `value`, `instance` (0 for scalars, 1-based for repeating). UNIQUE on (record_id, field_name, instance).

**audit_log** — append-only field-level change log.

**redcap_metadata** — data dictionary fields mirroring `data_dictionary.py` at seed time. 18 REDCap-standard columns.

### EAV Structure Details

Scalar non-repeating fields are stored with `instance=0`. Repeating instruments (`conditions`, `medications`, `allergies`, `lab_results`, `immunizations`, `clinical_notes`) use `instance` ≥ 1. Field names use dot notation: `vitals.systolic_bp`, `conditions.snomed_code`, etc.

The `_REPEATING` tuple in db.py at line 62 defines the six repeating instruments:
```python
_REPEATING = ("conditions", "medications", "allergies",
              "lab_results", "immunizations", "clinical_notes")
```

---

## 2. Models (backend/models.py)

`PatientRecord` is the top-level submission model. It merges:
- Patient demographics (NHI, name, DOB, sex, ethnicity, address, contact, GP)
- **Encounter context** (encounter_date REQUIRED, encounter_type, redcap_event_name, presenting_complaint, clinician_name, clinician_role)
- Clinical instruments as sub-objects: `vitals` (VitalSigns), `conditions` (list[Condition]), `medications` (list[Medication]), `allergies` (list[Allergy]), `lab_results` (list[LabResult]), `immunizations` (list[Immunization]), `social_history` (SocialHistory), `clinical_notes` (list[ClinicalNote])

**`encounter_date` is the only required field beyond demographics.** This is the architectural coupling: you cannot submit instrument data without an encounter date.

There is no model for instrument-level completion status. There is no concept of a standalone instrument submission that references an event without implying a clinical visit.

---

## 3. API Routes (backend/main.py)

### Clinical Records (encounter-centric)
- `POST /api/records` — creates a PatientRecord (demographics + encounter + all instruments in one payload)
- `GET /api/records` — list/search by nhi, family_name, encounter_date, patient_id
- `GET /api/records/{id}` — single record
- `PUT /api/records/{id}` — update (PatientRecordUpdate, all fields optional)
- `DELETE /api/records/{id}` — soft-delete

### Patients (demographics-only, added later)
- `POST /api/patients` — create patient (no encounter)
- `GET /api/patients` — list patients with encounter_count aggregate
- `GET /api/patients/{id}` — single patient
- `PUT /api/patients/{id}` — update demographics
- `DELETE /api/patients/{id}` — hard-delete

### FHIR Conversion
- `POST /api/records/{id}/convert` — converts record to FHIR Bundle
- `POST /api/patients/{id}/convert` — converts patient demographics to FHIR Patient

### Reference Data
- `GET /api/ref/events` — returns the 3 seeded events
- `GET /api/ref/missing-codes` — 17 CDISC codes
- `GET /api/data-dictionary` — all field definitions
- `GET /api/data-dictionary.csv`
- `GET /api/ref/snomed/conditions|medications|allergens|smoking|alcohol`
- `GET /api/ref/ethnicity|regions|loinc/observations|snomed/observations` (latter two return same object — known bug M-1)
- `GET /api/stats`

**Missing REDCap-like endpoints:**
- No endpoint for instrument-level submission (e.g. `POST /api/records/{id}/instruments/{instrument_name}`)
- No endpoint to read/write instrument completion status
- No endpoint to fetch all data for a patient at a specific event
- No endpoint that accepts data keyed by (patient, event, instrument) without implying a clinical encounter

---

## 4. Data Dictionary (backend/data_dictionary.py)

Defines `EVENTS` (3 events) and `DATA_DICTIONARY` (~60 field entries).

### Instruments (form_name values in DATA_DICTIONARY)
- `demographics` — record_id, nhi_number, family_name, given_names, date_of_birth, sex, gender_identity, sex_at_birth, ethnicity_codes, phone, email
- `address` — address.street, address.suburb, address.city, address.postcode, address.region
- `gp` — gp_name, gp_practice, pho
- `encounter` — encounter_date, encounter_type, redcap_event_name, presenting_complaint, clinician_name, clinician_role
- `vitals` — 9 vital sign fields (systolic_bp through bmi, including a calc field)
- `conditions` — 5 fields (repeating)
- `medications` — 8 fields (repeating)
- `allergies` — 5 fields (repeating)
- `lab_results` — 7 fields (repeating)
- `immunizations` — 5 fields (repeating)
- `social_history` — 6 fields (smoking, pack_years, alcohol, units/week, occupation, lives_alone)
- `clinical_notes` — 3 fields (repeating)

**There is no `instrument_completion_status` concept anywhere in the data dictionary.** Real REDCap stores completion status per instrument per event as an integer (0=Incomplete, 1=Unverified, 2=Complete) in a field named `{instrument_name}_complete`.

### Key gap
The `encounter` form_name groups encounter-specific fields (date, type, complaint, clinician). In real REDCap, instruments do not have an inherent "encounter" concept — they are forms filled out within an event. The `encounter` instrument here blurs the line between "event" (when data was collected) and "clinical encounter" (a specific FHIR Encounter resource).

---

## 5. Frontend (frontend/index.html)

### Pages / Navigation
- **Dashboard** (`page-home`) — stats, quick start guide
- **Patient Records** (`page-records`) — patient view (list patients) or encounter view (list records)
- **Quick Entry** (`page-form`) — single full-form that submits everything at once via `POST /api/records`
- **FHIR Store** (`page-fhir`) — browse local store and HAPI server
- **Data Dict** (`page-dict`) — displays `redcap_metadata` fields

### Data Entry Flow

**Quick Entry form** (page-form / `#encounter-form`): One monolithic form with collapsible sections:
1. Patient Demographics (NHI, name, DOB, sex, ethnicity, contact, address) — required open by default
2. GP / PHO Details — collapsible, closed by default
3. Encounter Details — required open (encounter_date, type, event selector, clinician, complaint)
4. Vital Signs — collapsible, closed
5. Conditions / Problem List — collapsible, chip-based add/remove
6. Medications — collapsible
7. Allergies — collapsible
8. Laboratory Results — collapsible
9. Immunizations — collapsible
10. Social History — collapsible
11. Clinical Notes — collapsible

Single submit button calls `submitRecord()` which posts the entire monolithic JSON to `POST /api/records`.

**Add Encounter modal** (opened from patient view via "Add Encounter" button): Separate modal `buildEncounterFormHTML()` that includes event selector, encounter date/type, vitals, conditions, and social history — also posts to `POST /api/records` with `patient_id` instead of demographics.

### Event Selector
The `<select id="redcap_event">` dropdown is populated from `/api/ref/events` and sends `redcap_event_name` as part of the payload. However, it is visually embedded within the "Encounter Details" section — making it feel like a property of the clinical encounter rather than a study timepoint.

### No instrument-level completion tracking in UI
There are no completion badges, status indicators, or per-instrument save buttons. The entire record is saved in one shot.

### Patient Timeline (in Records view)
`togglePatientTimeline()` fetches `GET /api/records?nhi=...` and renders encounters as rows with Event, Date, Type, Actions. This is the closest thing to a REDCap event grid, but it shows encounters (rows in the encounters table), not instrument completion at each event.

---

## 6. The Core Architectural Gap

### What REDCap does
REDCap organises data as: **patient (record) → event → instrument → fields**.

At each event, each instrument has an independent completion status (0/1/2). Data can be submitted to one instrument at one event without touching any other instrument or implying a clinical visit occurred. The `{instrument_name}_complete` field is stored alongside the instrument's EAV data.

Events are study timepoints (Baseline, Follow-up 1), not clinical encounters. A patient can have data in the "demographics" instrument at Baseline without ever having an "encounter" instrument filled in.

### What this system does
This system treats every data submission as a **clinical encounter first**. Every call to `POST /api/records` creates a row in the `encounters` table with a mandatory `encounter_date` and `encounter_type`. All instruments (vitals, conditions, medications, etc.) are stored as EAV rows that FK to that encounter row.

- There is no way to store instrument data at an event without an encounter row
- There is no instrument completion status column/table
- The UI presents all instruments as sections of a single encounter form
- Events are a secondary label on the encounter, not the primary organising axis

### Specific changes needed to close the gap

**Database:**
1. Either decouple `redcap_data.record_id` from `encounters.record_id` so that EAV rows can reference a (patient, event) pair directly — OR — make the `encounters` table optional/implicit for non-clinical events (rename to `event_data` or similar)
2. Add an `instrument_status` table: columns (patient_id, event_id, instrument_name, status INT 0/1/2, updated_at). This is the REDCap `{instrument}_complete` equivalent.
3. The `encounter_date` and `encounter_type` fields belong only in the `encounter` instrument/form, not as mandatory columns on every data submission row.

**Models (models.py):**
4. `encounter_date` must stop being a required field on `PatientRecord`. It should be optional — only required when the `encounter` instrument is being filled in.
5. A new `InstrumentSubmission` model should accept (patient_id, event_name, instrument_name, field_values dict) without any encounter fields.
6. A new `InstrumentStatus` model should represent completion state.

**API (main.py):**
7. New route: `POST /api/patients/{patient_id}/events/{event_name}/instruments/{instrument_name}` — submit data for one instrument at one event, no encounter required.
8. New route: `GET /api/patients/{patient_id}/events/{event_name}` — return all instrument data and completion statuses for a patient at an event (REDCap event grid view).
9. New route: `GET/PUT /api/patients/{patient_id}/events/{event_name}/instruments/{instrument_name}/status` — read/write completion status.
10. The existing `POST /api/records` endpoint can stay for backwards compatibility and FHIR conversion workflows.

**Data Dictionary (data_dictionary.py):**
11. Add `{instrument_name}_complete` fields to the data dictionary for each non-repeating instrument (demographics, address, gp, encounter, vitals, social_history). Repeating instruments use a per-instance completion concept.

**Frontend (frontend/index.html):**
12. Add an "Event Grid" view to the patient detail — rows = events, columns = instruments, cells = completion badges (red/amber/green). Clicking a cell opens that instrument's form for that event.
13. Each instrument section needs its own "Save" button and completion status selector (Incomplete/Unverified/Complete).
14. The event selector should move out of the "Encounter Details" section and become the primary axis for the entire data entry screen.
15. The "Quick Entry" form concept (one monolithic form) conflicts with the REDCap model. It can remain as a convenience shortcut but should not be the only data entry path.

---

## 7. Side-Effects and Risks for the Main Agent

- **The `encounters` table is the FK parent for `redcap_data`.** Any decoupling requires either migrating the FK or creating a new parent concept (e.g. `event_records` table keyed by patient_id + event_id). Existing data in `data/clinical.db` uses `record_id` UUIDs from `encounters` as the EAV parent.
- **FHIR conversion (`converter.py`) assumes a full encounter record.** `clinical_record_to_fhir_bundle` calls `build_encounter()` and expects `encounter_date` and `encounter_type`. If data can be submitted without an encounter, the converter must handle the case where these fields are absent.
- **`list_records()` in db.py JOINs encounters to patients** — any new non-encounter-backed storage won't appear in this list.
- **The `audit_log` references `record_id`** — this maps to encounter UUIDs. If a new (patient, event, instrument) storage path is introduced, audit rows need to reference those instead.
- **`encounter_type` default `'ambulatory'` is hardcoded in three places** (db.py line 159, line 604, line 644) — noted as code smell DB-5. Removing encounter_type as mandatory will clean this up naturally.
- **The `redcap_metadata` table currently has no `instrument_complete` fields seeded** — they would need to be added to `DATA_DICTIONARY` in data_dictionary.py and re-seeded (or migrated).
- **Existing frontend `openAddEncounterModal()`** sends `patient_id` + encounter fields — this path already avoids demographics but still requires `encounter_date`. Extending this modal to support instrument-only submission with event context would be the lowest-risk first step.
