NZ FHIR Clinical Demo Platform

A local test platform for exploring FHIR R4 and SNOMED-CT through clinical use.
Modelled on NZ health data standards, GP workflow, and the NZ FHIR Base IG.

════════════════════════════════════════════════════
QUICK START
════════════════════════════════════════════════════

1. Make sure Python 3.10+ is installed:

     python3 --version

2. Run the startup script from the project directory:

     cd ~/fhir-playground       # or wherever you unpacked it
     bash run.sh

3. Open http://localhost:8000 in a browser.

The script installs Python dependencies automatically on first run.

────────────────────────────────────────────────────
Troubleshooting first-run errors
────────────────────────────────────────────────────

"No such file or directory: .venv/bin/activate"
  python3-venv is not installed. Fix:

    sudo apt install python3-venv        # Debian / Ubuntu / WSL
    # then rerun: bash run.sh

"Could not install Python dependencies"
  pip is not installed. Fix:

    sudo apt install python3-pip         # Debian / Ubuntu / WSL
    # then rerun: bash run.sh

macOS (Homebrew Python):
  No extra steps needed. run.sh uses --user install if venv fails.

  If you hit "externally managed environment":
    brew install python3                 # ensures venv support
    # then rerun: bash run.sh

Python not found at all:
  Ubuntu/Debian:  sudo apt install python3
  macOS:          brew install python

════════════════════════════════════════════════════
WHAT IT DOES
════════════════════════════════════════════════════

1. Clinical data entry (REDCap-style form)
   - NHI (National Health Index) patient identifier — format AAANNNC
   - NZ Stats Level-4 ethnicity coding (186 codes, 5-digit)
   - Sex at Birth (separate from administrative gender — NZ Base IG)
   - NZ address fields (street, suburb, city, postcode, Te Whatu Ora region)
   - GP / PHO linkage
   - Vital signs (BP, HR, RR, temp, SpO2, weight, height, BMI auto-calc)
   - Problem list with SNOMED-CT codes
   - Medications with SNOMED / NZMT codes (dose, frequency, route)
   - Allergies with SNOMED-CT allergen codes and severity
   - Laboratory results with LOINC codes and reference ranges
   - Immunizations with SNOMED-CT vaccine codes
   - Social history (smoking status SNOMED-CT, alcohol units/week)
   - Clinical notes (examination, assessment/plan, other)

2. Persistent raw data store (SQLite — data/clinical.db)
   Full JSON of each encounter stored; searchable by NHI, surname, date.

3. FHIR R4 conversion
   One-click conversion of any clinical record to a FHIR Transaction Bundle
   containing: Patient, Encounter, Observation (vitals + labs), Condition,
   MedicationStatement, AllergyIntolerance, Immunization, Composition.
   Each resource is also individually indexed for browsing.

4. FHIR store (data/fhir_store/*.json + data/fhir_index.db)
   Bundle and all individual resources persisted as JSON files with a
   searchable SQLite index. Filter by resource type, patient, NHI, date range.

5. FHIR viewer
   Raw JSON display with syntax highlighting. application/fhir+json content type.
   Copy-to-clipboard. Accessible from the FHIR Store tab.

════════════════════════════════════════════════════
FHIR STANDARDS COMPLIANCE
════════════════════════════════════════════════════

  FHIR version:      R4 (4.0.1)  https://hl7.org/fhir/R4/
  Patient profile:   https://fhir.org.nz/ig/base/StructureDefinition/NzPatient
  Encounter profile: https://fhir.org.nz/ig/base/StructureDefinition/NzEncounter
  NHI system:        https://standards.digital.health.nz/ns/nhi-id
  NZ ethnicity:      https://standards.digital.health.nz/ns/ethnic-group-level-4-code
  Sex at birth:      http://hl7.org.nz/fhir/StructureDefinition/sex-at-birth
  SNOMED-CT:         http://snomed.info/sct
  LOINC:             http://loinc.org
  UCUM units:        http://unitsofmeasure.org
  HL7 terminology:   http://terminology.hl7.org/
  Bundle type:       transaction (PUT per resource)

Notable compliance details:
  - SpO2 is dual-coded: primary 2708-6 (arterial O2 sat) + supplementary 59408-5
    (pulse oximetry), per FHIR R4 Vital Signs profile
  - BP panel uses LOINC 85354-9 per FHIR R4 bp profile
  - Timestamps include NZ UTC offset (+13:00 NZDT / +12:00 NZST)
  - Ethnicity codes are Level-4 (5-digit, e.g. 21111 = Māori) sourced from the
    official NZ Base IG CodeSystem

════════════════════════════════════════════════════
API ENDPOINTS
════════════════════════════════════════════════════

  Clinical records:
    POST   /api/records                Create encounter
    GET    /api/records                List/search (nhi, family_name, encounter_date)
    GET    /api/records/{id}           Get single record
    PUT    /api/records/{id}           Update record
    DELETE /api/records/{id}           Delete record
    POST   /api/records/{id}/convert   Convert to FHIR Bundle

  FHIR store:
    GET    /api/fhir/all               List all FHIR resources (index)
    GET    /api/fhir                   Search (resource_type, patient_id, nhi_number,
                                              date_from, date_to, subject_name)
    GET    /api/fhir/{id}              Get raw FHIR JSON (Content-Type: application/fhir+json)

  Reference data:
    GET    /api/ref/snomed/conditions
    GET    /api/ref/snomed/medications
    GET    /api/ref/snomed/allergens
    GET    /api/ref/snomed/smoking
    GET    /api/ref/loinc/observations
    GET    /api/ref/ethnicity
    GET    /api/ref/regions
    GET    /api/stats

  Interactive API docs: http://localhost:8000/docs

════════════════════════════════════════════════════
FILE STRUCTURE
════════════════════════════════════════════════════

  backend/
    main.py        FastAPI application, all routes
    models.py      Pydantic models for clinical data
    db.py          SQLite persistence for raw clinical records
    fhir_store.py  FHIR JSON file persistence + SQLite index
    converter.py   Clinical record -> FHIR R4 Bundle conversion
    snomed.py      SNOMED-CT, LOINC, NZ ethnicity reference tables

  frontend/
    index.html     Single-page app (no build step required)

  data/            Created on first run
    clinical.db    SQLite: raw clinical records
    fhir_index.db  SQLite: FHIR resource search index
    fhir_store/    Directory of FHIR JSON files (one per resource)

  requirements.txt
  run.sh

════════════════════════════════════════════════════
CODING SYSTEMS INCLUDED
════════════════════════════════════════════════════

  SNOMED-CT conditions: 26 codes (NZ primary care)
  SNOMED-CT medications: 30 codes (NZ formulary / NZMT)
  SNOMED-CT allergens:  15 codes
  SNOMED-CT smoking:     6 status codes
  LOINC observations:   38 codes (vitals + biochemistry + haematology)
  NZ ethnicity:        186 Level-4 codes (NZ Stats, sourced from NZ Base IG)
  NZ regions:           20 Te Whatu Ora regions
  Vaccines:              9 common NZ immunisation schedule vaccines

════════════════════════════════════════════════════
FOR DEMO / LEARNING PURPOSES ONLY
════════════════════════════════════════════════════
