NZ FHIR Clinical Demo Platform

A local test platform for exploring FHIR R4 and SNOMED-CT through clinical use.
Modelled on NZ health data standards, GP workflow, and the NZ FHIR Base IG.

QUICK START

  bash run.sh

Then open http://localhost:8000 in a browser.

Requirements: Python 3.10+. No other system dependencies.

WHAT IT DOES

1. Clinical data entry (REDCap-style form)
   - NHI (National Health Index) patient identifier
   - NZ Stats Level-2 ethnicity coding
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

4. FHIR store (data/fhir_store/*.json + data/fhir_index.db)
   Bundles and resources persisted as JSON files with an SQLite search index.
   Searchable by resource type, patient, NHI, date range.

5. FHIR viewer
   Raw JSON display with syntax highlighting. application/fhir+json content type.
   Copy-to-clipboard. Accessible from the FHIR Store tab.

FHIR STANDARDS COMPLIANCE

  - FHIR version: R4 (4.0.1)  https://hl7.org/fhir/R4/
  - Patient profile: NZ Base IG  http://hl7.org.nz/fhir/StructureDefinition/NzPatient
  - Encounter profile: NZ Base IG  http://hl7.org.nz/fhir/StructureDefinition/NzEncounter
  - NHI identifier system: https://standards.digital.health.nz/ns/nhi-id
  - NZ ethnicity: https://standards.digital.health.nz/ns/ethnic-group-level-2-code
  - SNOMED-CT: http://snomed.info/sct
  - LOINC: http://loinc.org
  - UCUM units: http://unitsofmeasure.org
  - HL7 terminology: http://terminology.hl7.org/
  - Bundle type: transaction (PUT per resource)

API ENDPOINTS

  Clinical records:
    POST   /api/records                Create encounter
    GET    /api/records                List/search (nhi, family_name, encounter_date)
    GET    /api/records/{id}           Get single record
    PUT    /api/records/{id}           Update record
    DELETE /api/records/{id}           Delete record
    POST   /api/records/{id}/convert   Convert to FHIR Bundle

  FHIR store:
    GET    /api/fhir/all               List all FHIR resources (index)
    GET    /api/fhir                   Search (resource_type, patient_id, nhi_number, date_from, date_to, subject_name)
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

FILE STRUCTURE

  backend/
    main.py        FastAPI application, all routes
    models.py      Pydantic models for clinical data
    db.py          SQLite persistence for raw clinical records
    fhir_store.py  FHIR JSON file persistence + SQLite index
    converter.py   Clinical record -> FHIR R4 Bundle conversion
    snomed.py      SNOMED-CT, LOINC, NZ ethnicity reference tables

  frontend/
    index.html     Single-page app (no build step required)

  data/
    clinical.db    SQLite: raw clinical records
    fhir_index.db  SQLite: FHIR resource search index
    fhir_store/    Directory of FHIR JSON files (one per Bundle/resource)

  requirements.txt
  run.sh

CODING SYSTEMS INCLUDED

  SNOMED-CT conditions: 26 codes covering NZ primary care
  SNOMED-CT medications: 30 codes (NZ formulary / NZMT)
  SNOMED-CT allergens:  15 codes
  SNOMED-CT smoking:     6 status codes
  LOINC observations:   38 codes (vitals + full biochemistry + haematology)
  NZ ethnicity:         26 Level-2 codes (Stats NZ)
  NZ regions:           20 Te Whatu Ora regions
  Vaccines:              9 common NZ immunisation schedule vaccines

FOR DEMO / LEARNING PURPOSES ONLY
No patient data should be entered. Use synthetic data only.
