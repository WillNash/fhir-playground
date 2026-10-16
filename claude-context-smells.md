# Code Smell Analysis — Python Backend

> Analysed: 2026-10-16
> Files: `backend/main.py`, `backend/hapi_client.py`, `backend/fhir_store.py`, `backend/db.py`, `backend/models.py`, `backend/converter.py`, `backend/snomed.py`

---

## File: `backend/db.py`

### DB-1 — Connection lifecycle inconsistency (Inconsistency / Inappropriate intimacy) — **HIGH**

**Lines 28–33 vs 62–63 and every CRUD function.**

`_get_conn()` returns a raw, unclosed `sqlite3.Connection`. Every caller wraps it in a `with` block, relying on the implicit `Connection.__exit__` behaviour (which *commits* on success but does **not** close the connection). `fhir_store.py` (a sibling module) solves the identical problem differently: it uses a proper `@contextmanager` called `_index_conn()` that explicitly calls `conn.close()` in its `finally` block. The `db.py` approach leaks connections on every call, whereas `fhir_store.py` closes them. The inconsistency means maintenance developers will copy whichever pattern they encounter first, making the divergence self-propagating.

### DB-2 — `create_record` mutates its caller's dict (Long function / side-effect) — **HIGH**

**Lines 104–140.**

`create_record` is documented as mutating `record_dict` in place ("record_dict is mutated in place"). `main.py` calls it with `record.model_dump()` so the immediate caller is safe, but the function's contract is surprising: a function named `create_record` that silently rewrites the dict passed to it is an unexpected side-effect. If any future caller passes a live dict it cares about, timestamps will be injected silently. The mutation also means `fhir_bundle_id = None` is forced onto the dict at line 139, which is unrelated to the purpose of "create".

### DB-3 — `update_record` silently ignores `None` values (Inconsistency / Missing abstraction) — **MEDIUM**

**Lines 152–189.**

The docstring notes that `None` values in `updates` are skipped. However, this is also enforced one level up in `main.py` at line 137 (`{k: v for k, v in updates.model_dump().items() if v is not None}`), meaning the `None`-filter runs twice. There is no way to deliberately set a field back to `None` through the update path. This is a silent data-loss path: a caller who wants to clear `presenting_complaint` cannot do so.

### DB-4 — `_get_conn` not a context manager but used as one (Inconsistency) — **MEDIUM**

**Line 62 (`with _get_conn() as conn`).**

`sqlite3.Connection` supports the context manager protocol as a *transaction* manager only (it does not close). Calling `_get_conn()` in a `with` statement gives the illusion that the resource is properly managed, but the connection remains open. Compare with `_index_conn()` in `fhir_store.py` which is an explicit `@contextmanager` and closes in `finally`. The naming (`_get_conn` vs `_index_conn`) reinforces the false equivalence.

### DB-5 — Magic string default `"ambulatory"` duplicated (Magic values / Duplication) — **LOW**

**Lines 127 and 182.**

The string `"ambulatory"` appears twice as a `.get()` default. The same default is defined in `models.py` (line 160) via the Pydantic field default. Three source locations for one canonical default creates a drift risk.

---

## File: `backend/fhir_store.py`

### FS-1 — `_purge_orphaned_index_entries` loads all IDs into memory (Long function / scalability) — **MEDIUM**

**Lines 379–397.**

The function fetches every row from `fhir_index` at startup and checks each ID's file existence in Python. For a large store this is O(n) memory and O(n) filesystem probes at boot. A more maintainable design would delete on `get_resource` miss (which already exists at line 302–304) rather than doing a full scan at init time.

### FS-2 — `_today_iso` uses local time, not UTC (Inconsistency) — **MEDIUM**

**Lines 94–97.**

`_now_iso()` returns `datetime.now(timezone.utc).isoformat()` (correct UTC). But `_today_iso()` returns `date.today().isoformat()` — which uses the **server's local timezone**, not UTC. On a server in NZ (UTC+12/13) this can produce a date one day ahead of the actual UTC date. `converter.py` avoids this by using `datetime.now(_NZ_TZ).date()`, which is explicit about the timezone. The inconsistency between the two modules means dates stored in the index may differ from dates embedded in FHIR resources.

### FS-3 — `save_resource` is a god function (Long function / God function) — **MEDIUM**

**Lines 224–291.**

`save_resource` does four conceptually distinct things: validates the resource, writes the file, derives index metadata (three different code paths depending on resource type), and writes to SQLite. The embedded `match` block (lines 248–268) has branches of materially different complexity. Splitting into `_write_resource_file`, `_derive_index_fields`, and `_upsert_index` would improve testability.

### FS-4 — Open-coded SQL string building risks injection if misused (Missing abstraction) — **LOW**

**Lines 325–357 in `search_resources`.**

The WHERE clause is assembled by string concatenation (`f"WHERE {' AND '.join(conditions)}"`). Only the *values* go through parameterisation; column names are safe because they come from literals within the function. However the pattern is one copy-paste away from a real SQL injection. An explicit query-builder helper (even a small one) would make the intent clearer and remove the risk if the function is ever extended with external input for column names.

### FS-5 — `_index_conn` re-creates the directory on every call (Duplication) — **LOW**

**Lines 74–86 vs 237.**

`_index_conn` calls `INDEX_DB.parent.mkdir(parents=True, exist_ok=True)` on every single database connection open, and `save_resource` at line 237 additionally calls `FHIR_DIR.mkdir(parents=True, exist_ok=True)`. Both directories are guaranteed to exist after `init_fhir_store()` runs; the repeated `mkdir` calls are unnecessary overhead on every read/write.

---

## File: `backend/hapi_client.py`

### HC-1 — New HTTP client instantiated on every call (Inconsistency / Performance) — **MEDIUM**

**Lines 36–47 (`_fhir_client`) and all callers.**

Every public function (`post_bundle`, `get_resource`, `search`, `patient_everything`, `capability_statement`, `proxy_get`) creates and destroys its own `httpx.AsyncClient`. The module docstring in `_fhir_client` acknowledges this is less efficient than a shared client ("A long-lived shared client would be more efficient") but defers to convenience. In practice:
- TLS handshakes are repeated for every request.
- `is_available()` is polled from `main.py` on every `/api/hapi-status` request, meaning a new TCP+TLS connection is created on each status poll.
- The comment says "would require explicit startup/shutdown hooks", but FastAPI's `lifespan` (already in use in `main.py`) is exactly the right place for this.

### HC-2 — `proxy_get` deviates silently from error-handling convention (Inconsistency) — **LOW**

**Lines 115–123 vs every other function.**

All other public functions call `response.raise_for_status()`. `proxy_get` deliberately does not, forwarding the raw response to the caller. This is correct for a proxy, but the deviation is only explained in a comment. A caller adding a new public function might miss the pattern and forget `raise_for_status`.

---

## File: `backend/main.py`

### M-1 — `ref_loinc` duplicates `ref_observations` (Duplication / Dead code) — **HIGH**

**Lines 297–299 vs 263–265.**

`/api/ref/loinc/observations` and `/api/ref/snomed/observations` are two separate routes that return **exactly the same object** (`OBSERVATIONS`). The LOINC route is almost certainly a mistake or leftover from a rename — LOINC codes are already in `OBSERVATIONS`, and there is no separate LOINC dict. One of these routes is redundant; any frontend code consuming one will silently get the same data from the other, but the double exposure creates confusion about which is "correct".

### M-2 — CORS wildcard `allow_origins=["*"]` is a magic/insecure value (Magic values) — **LOW**

**Lines 91–96.**

Wildcard CORS is acceptable during development but should not silently persist. There is no environment-based override — the same permissive setting applies to production. The allowed origins should come from a config/environment variable.

### M-3 — `_post_bundle_to_hapi` parses patient ID with fragile string splitting (Magic values / Missing abstraction) — **LOW**

**Line 199.**

`loc.split("/")[1].split("/_history")[0]` extracts a FHIR resource ID from a `location` header. This pattern is duplicated conceptually in `converter.py` (`get_patient_id_from_bundle`) and `fhir_store.py` (`_patient_ref_from_resource`). A shared `parse_fhir_reference(ref: str)` utility would centralise this parsing and remove the brittle split logic.

### M-4 — Route handlers are thin but `convert_to_fhir` is fat (Long function) — **LOW**

**Lines 155–182.**

Most route handlers are one-liners that delegate to domain functions. `convert_to_fhir` is the exception: it orchestrates persistence, HAPI posting, and response assembly. The HAPI call is already extracted into `_post_bundle_to_hapi`. The individual-resource loop (lines 167–170) and the response construction are still inline. This is a minor maintainability smell — the function is not excessively long but it mixes concerns.

---

## File: `backend/converter.py`

### CV-1 — `build_patient` is a long god function (Long function / God function) — **HIGH**

**Lines 126–219 (93 lines).**

`build_patient` assembles identifiers, ethnicity extensions, name parsing, address mapping, telecom, gender-identity extensions, and sex-at-birth extensions all in one function. Each of those is a discrete FHIR concept with its own rules and edge cases. The function is not wrong but it is difficult to test, extend (e.g. adding a new extension), or reuse in isolation. Comparable builders (`build_encounter`, `build_allergy`, etc.) are 30–40 lines, making `build_patient` a clear outlier.

### CV-2 — Status validation logic duplicated across `build_condition` and `build_medication_statement` (Duplication) — **MEDIUM**

**Lines 437–439 and 479–481.**

Both functions define a local `_valid_statuses` set and apply the same fallback-to-`"active"` pattern:
```python
_valid_statuses = {"active", "resolved", "inactive"}
raw_status = cond.get("status", "active")
clin_status = raw_status if raw_status in _valid_statuses else "active"
```
The pattern is duplicated, not shared. Because the valid sets differ (`"resolved"/"inactive"` for conditions vs `"stopped"/"on-hold"` for medications), an abstraction like `_validated_status(raw, valid_set, default="active")` would communicate the intent while reducing duplication. As written, the pattern can silently differ between the two if one copy is edited and the other is not.

### CV-3 — `build_vitals` skips `spo2` in the LOINC loop but also handles it specially — double processing risk (Inconsistency / Duplication) — **MEDIUM**

**Lines 319–344 vs 346–374.**

`spo2` is handled in a dedicated block (lines 319–344) with dual LOINC coding. Then, at line 347, only `{"systolic_bp", "diastolic_bp"}` are added to `skip_for_bp`. `spo2` is *not* in `_VITAL_FIELD_TO_LOINC` (line 78–87), so it happens to be skipped — but this relies on an implicit non-membership rather than an explicit exclusion. If someone adds `"spo2"` to `_VITAL_FIELD_TO_LOINC` for completeness, `spo2` will silently be emitted twice in the FHIR bundle. A comment or explicit guard would prevent this.

### CV-4 — Repeated inline FHIR skeleton construction (Duplication) — **MEDIUM**

**`build_social_history_observations` lines 599–633, and vitals loop lines 353–374.**

Both blocks produce nearly identical `Observation` dicts with the same set of keys (`resourceType`, `id`, `status`, `category`, `code`, `subject`, `encounter`, `effectiveDateTime`, `valueQuantity`). A small `_make_observation(patient_id, encounter_id, date, category, code, value_quantity)` factory would eliminate 30–40 lines of duplication and make structural conformance easier to verify.

### CV-5 — `build_allergy` hardcodes `"category": ["medication"]` for all allergies (Magic values / Missing abstraction) — **MEDIUM**

**Line 538.**

Every allergy is categorised as `"medication"` regardless of what the allergen actually is (food, environmental, drug). `snomed.py`'s `ALLERGENS` dict contains pollen, latex, eggs, milk, and dust mites — none of which are medications. A caller recording a nut allergy will receive a FHIR resource that incorrectly declares `category: medication`. This is a functional bug masquerading as a magic value.

### CV-6 — `clinical_record_to_fhir_bundle` is a moderately long orchestrator (Long function) — **LOW**

**Lines 685–782 (97 lines).**

The main entry point is a sequential orchestrator. Its length is partly justified by the number of resource types, but the inner `_entry` and `_add` closures (lines 693–726) could be module-level helpers to ease testing. The function is readable as-is, but any new resource type adds another 3–4-line block without prompting any structural refactor.

### CV-7 — Primitive obsession: `record: dict[str, Any]` throughout (Primitive obsession) — **LOW**

**Every `build_*` function signature.**

All builder functions accept `dict[str, Any]` to represent the clinical record or sub-records (conditions, meds, etc.). The Pydantic models in `models.py` exist precisely for this data, but the converter operates on raw dicts (because `db.py` stores JSON and returns plain dicts). Passing `PatientRecord` directly to the converter — or at least a TypedDict — would catch missing fields at type-check time instead of at runtime via silent `.get()` fallbacks.

---

## File: `backend/models.py`

### MO-1 — `Allergy.status` is an untyped bare string (Primitive obsession) — **MEDIUM**

**Line 94.**

Every other status field uses a `Literal` type alias (`ConditionStatus`, `MedicationStatus`). `Allergy.status` is `str = "active"` with no validation. A value of `"Active"` or `"inactive"` would pass Pydantic validation and be silently written to the FHIR resource with an invalid clinical status code. The type should be `Literal["active", "inactive", "resolved"]`.

### MO-2 — Date fields are bare `str` with no format validation (Primitive obsession) — **MEDIUM**

**Lines 73, 139, 159, and others.**

`date_of_birth: str`, `encounter_date: str`, `onset_date: str | None`, `collected_date: str | None`, etc., are documented as "ISO date YYYY-MM-DD" in comments but have no Pydantic validator. A value like `"01/01/1980"` or `"today"` would pass model validation and be embedded verbatim in the FHIR resource, failing FHIR date validation downstream. Using `datetime.date` or a `constr(pattern=r'^\d{4}-\d{2}-\d{2}$')` field would catch this early.

### MO-3 — `PatientRecord` and `PatientRecordUpdate` are near-complete field mirrors (Duplication) — **LOW**

**Lines 126–210.**

`PatientRecordUpdate` repeats every field of `PatientRecord` with `| None` appended. Python typing utilities (`Optional` field override) or Pydantic's planned partial-model support are not yet stable, but the current approach means every new field added to `PatientRecord` must also be added to `PatientRecordUpdate`, with a silent bug if one is missed. A comment or lint check should enforce the link.

---

## File: `backend/snomed.py`

### SN-1 — `PROCEDURES` is defined but never imported anywhere (Dead code) — **MEDIUM**

**Lines 287–298.**

The `PROCEDURES` dict is defined but `grep`-level inspection of all other files shows no import of `PROCEDURES`. It is not exported from `main.py`'s reference data routes and is not used in `converter.py`. Either a `/api/ref/snomed/procedures` route is missing (a functionality gap) or the dict is dead code that creates a false impression of feature completeness.

### SN-2 — `ALLERGENS` code `372687099` is a likely typo (Magic values / Bug) — **HIGH**

**Line 416.**

`ALLERGENS` contains the code `"372687099"` for "Cephalosporins". Compare with `"372687004"` for "Penicillin" (line 401 in `ALLERGENS`, line 363 in `MEDICATIONS`). SNOMED codes do not end in `099`; the valid SNOMED code for cephalosporins is `372687004`'s neighbour `"372687004"` or a related concept, but `372687099` does not exist in SNOMED-CT International. This is a plausible transcription error (last three digits `004` → `099`) that will generate an invalid FHIR code in any allergy resource built from this allergen.

### SN-3 — `ALCOHOL_STATUS` code `219006` is likely wrong system (Magic values / Bug) — **MEDIUM**

**Line 468.**

The code `"219006"` is listed without a system note. SNOMED-CT concept `219006` is "Cadmium poisoning" — obviously wrong for alcohol status. The likely intended SNOMED code is `"219006"` in a different coding system, or `"219006"` is a known NZ local code. If it is genuinely meant to be SNOMED, this will produce a semantically incorrect FHIR Observation. The comment in the file says "most codes are SNOMED-CT", which makes this ambiguity particularly risky.

---

## File: `backend/hapi_client.py` — additional

### HC-3 — `RXNORM_SYSTEM` constant defined in `snomed.py` but never used (Dead code) — **LOW**

**`snomed.py` line 30.**

`RXNORM_SYSTEM` is declared as a `Final` constant but no file in the codebase imports or uses it. It is not used in `converter.py` (which uses only `SNOMED_SYSTEM` and `LOINC_SYSTEM`).

---

## Ranked Summary

| Rank | ID | File | Category | Severity | One-line summary |
|------|----|------|----------|----------|-----------------|
| 1 | SN-2 | `snomed.py:416` | Magic values / Bug | **HIGH** | `ALLERGENS` code `372687099` for Cephalosporins is not a valid SNOMED code and will silently produce invalid FHIR. |
| 2 | DB-1 | `db.py:28–33` | Inconsistency | **HIGH** | `_get_conn` leaks connections; `fhir_store.py` closes them correctly — two patterns for the same problem. |
| 3 | CV-1 | `converter.py:126–219` | God function | **HIGH** | `build_patient` (93 lines) mixes identifier, address, telecom, and extension assembly, making it hard to extend. |
| 4 | M-1 | `main.py:297–299` | Duplication / Dead code | **HIGH** | `/api/ref/loinc/observations` and `/api/ref/snomed/observations` return the same object — one is dead/misleading. |
| 5 | DB-2 | `db.py:104–140` | Side-effect | **HIGH** | `create_record` mutates the caller's dict in-place, which is a surprising and dangerous contract. |
| 6 | SN-3 | `snomed.py:468` | Magic values / Bug | **MEDIUM** | SNOMED code `219006` for alcohol status may be from the wrong system — semantically wrong if emitted as SNOMED-CT. |
| 7 | CV-5 | `converter.py:538` | Missing abstraction | **MEDIUM** | All allergies are hardcoded `category: medication`, producing incorrect FHIR for food/environmental allergens. |
| 8 | HC-1 | `hapi_client.py:36–47` | Performance / Inconsistency | **MEDIUM** | New HTTP client per call — TCP/TLS overhead on every request, acknowledged but not fixed. |
| 9 | CV-2 | `converter.py:437–481` | Duplication | **MEDIUM** | Status validation pattern copy-pasted between `build_condition` and `build_medication_statement`. |
| 10 | MO-1 | `models.py:94` | Primitive obsession | **MEDIUM** | `Allergy.status` is an untyped `str` while all peer status fields are `Literal` — silent validation gap. |
| 11 | MO-2 | `models.py:73,139,159…` | Primitive obsession | **MEDIUM** | ISO date fields are bare `str` with no format validation — invalid dates pass through to FHIR. |
| 12 | SN-1 | `snomed.py:287–298` | Dead code | **MEDIUM** | `PROCEDURES` dict is defined but never imported or exposed via any route. |
| 13 | CV-3 | `converter.py:319–374` | Inconsistency | **MEDIUM** | `spo2` exclusion from the LOINC loop is implicit (non-membership) rather than explicit — future edit risk. |
| 14 | CV-4 | `converter.py:599–633` | Duplication | **MEDIUM** | Observation dict skeletons repeated in vitals and social-history builders; a factory would centralise structure. |
| 15 | FS-2 | `fhir_store.py:94–97` | Inconsistency | **MEDIUM** | `_today_iso` uses local server time; `_now_iso` uses UTC — date fields in the index may be timezone-inconsistent. |
| 16 | FS-1 | `fhir_store.py:379–397` | Scalability | **MEDIUM** | Orphan purge loads all IDs into memory at startup — O(n) filesystem probes. |
| 17 | DB-3 | `db.py:152–164` | Inconsistency | **MEDIUM** | `None`-value filter applied twice (in route handler and in `update_record`), and makes field-clearing impossible. |
| 18 | DB-4 | `db.py:62` | Inconsistency | **MEDIUM** | `_get_conn` used as a context manager implies resource cleanup that does not actually happen. |
| 19 | FS-3 | `fhir_store.py:224–291` | God function | **MEDIUM** | `save_resource` performs file I/O, metadata derivation (three branches), and SQL upsert in one function. |
| 20 | HC-3 | `snomed.py:30` | Dead code | **LOW** | `RXNORM_SYSTEM` constant defined but unused anywhere in the codebase. |
| 21 | DB-5 | `db.py:127,182` | Magic values / Duplication | **LOW** | Default `"ambulatory"` duplicated three times across `db.py` and `models.py`. |
| 22 | CV-6 | `converter.py:685–782` | Long function | **LOW** | Main bundle orchestrator is 97 lines; inner closures should be module-level helpers. |
| 23 | CV-7 | `converter.py` (all builders) | Primitive obsession | **LOW** | Builders accept `dict[str, Any]` where Pydantic models already define the shape. |
| 24 | MO-3 | `models.py:180–210` | Duplication | **LOW** | `PatientRecordUpdate` mirrors all fields of `PatientRecord` with no mechanism to enforce field parity. |
| 25 | FS-4 | `fhir_store.py:325–357` | Missing abstraction | **LOW** | WHERE clause assembled by string concatenation — safe today, but one step from SQL injection. |
| 26 | FS-5 | `fhir_store.py:74` | Duplication | **LOW** | `mkdir` called on every connection open, not just at init time. |
| 27 | M-2 | `main.py:91–96` | Magic values | **LOW** | CORS wildcard `allow_origins=["*"]` is hardcoded with no environment-variable override path. |
| 28 | M-3 | `main.py:199` | Magic values | **LOW** | FHIR reference string parsed with fragile `.split("/")` chaining; pattern also exists in other modules. |
| 29 | HC-2 | `hapi_client.py:115–123` | Inconsistency | **LOW** | `proxy_get` omits `raise_for_status`; deviation from every other function is only in a comment. |
