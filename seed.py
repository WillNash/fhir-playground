"""
Seed script — creates three realistic NZ demo patients and converts each to FHIR.

Usage:
    python3 seed.py                   # assumes app running on localhost:8000
    python3 seed.py http://host:port  # custom base URL

NHI numbers ZAA0001–ZAA9999 are reserved for NZ testing purposes.
"""
from __future__ import annotations
import json
import sys
import urllib.request
import urllib.error

BASE = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://localhost:8000"


def post(path: str, body: dict) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


# ---------------------------------------------------------------------------
# Demo patients
# ---------------------------------------------------------------------------

PATIENTS = [
    # ------------------------------------------------------------------
    # 1. Aroha Tane — Māori female, T2DM + hypertension, 3-monthly review
    # ------------------------------------------------------------------
    {
        "nhi_number": "ZAA0001",
        "family_name": "Tane",
        "given_names": "Aroha",
        "date_of_birth": "1975-03-15",
        "sex": "female",
        "redcap_event_name": "baseline_arm_1",
        "sex_at_birth": "female",
        "ethnicity_codes": ["21111"],
        "address": {
            "street": "14 Papatoetoe Road",
            "suburb": "Papatoetoe",
            "city": "Auckland",
            "postcode": "2025",
            "region": "Counties Manukau"
        },
        "phone": "021 555 0101",
        "gp_name": "Dr Rangi Parata",
        "gp_practice": "Mangere Health Centre",
        "pho": "Counties Manukau PHO",
        "encounter_date": "2026-10-15",
        "encounter_type": "ambulatory",
        "presenting_complaint": "3-monthly diabetes review. Patient reports good adherence to medications. Some ankle swelling noted over the past 2 weeks.",
        "clinician_name": "Dr Rangi Parata",
        "clinician_role": "GP",
        "vitals": {
            "systolic_bp": 148.0,
            "diastolic_bp": 92.0,
            "heart_rate": 78.0,
            "respiratory_rate": 16.0,
            "temperature": 36.7,
            "spo2": 98.0,
            "weight_kg": 87.0,
            "height_cm": 162.0
        },
        "conditions": [
            {
                "snomed_code": "44054006",
                "display": "Diabetes mellitus type 2",
                "onset_date": "2015-08-01",
                "status": "active"
            },
            {
                "snomed_code": "38341003",
                "display": "Hypertension",
                "onset_date": "2018-03-10",
                "status": "active"
            }
        ],
        "medications": [
            {
                "snomed_code": "386873009",
                "name": "Metformin",
                "dose": "500mg",
                "frequency": "twice daily",
                "route": "oral",
                "start_date": "2015-08-15",
                "status": "active"
            },
            {
                "snomed_code": "372741007",
                "name": "Ramipril",
                "dose": "5mg",
                "frequency": "once daily",
                "route": "oral",
                "start_date": "2018-04-01",
                "status": "active"
            }
        ],
        "allergies": [
            {
                "allergen_code": "372687004",
                "allergen_display": "Penicillin",
                "reaction": "Urticaria and facial swelling",
                "severity": "moderate",
                "status": "active"
            }
        ],
        "lab_results": [
            {"loinc_code": "4548-4",  "value": 7.8,  "unit": "%",           "reference_range_low": 4.0,  "reference_range_high": 6.0,   "abnormal_flag": "H",  "collected_date": "2026-10-14"},
            {"loinc_code": "2339-0",  "value": 9.2,  "unit": "mmol/L",      "reference_range_low": 3.9,  "reference_range_high": 7.8,   "abnormal_flag": "H",  "collected_date": "2026-10-14"},
            {"loinc_code": "2160-0",  "value": 72.0, "unit": "umol/L",      "reference_range_low": 45.0, "reference_range_high": 90.0,  "abnormal_flag": "N",  "collected_date": "2026-10-14"},
            {"loinc_code": "33914-3", "value": 78.0, "unit": "mL/min/1.73m2","reference_range_low": 60.0,"reference_range_high": 999.0, "abnormal_flag": "N",  "collected_date": "2026-10-14"},
            {"loinc_code": "2093-3",  "value": 5.4,  "unit": "mmol/L",      "reference_range_low": 0.0,  "reference_range_high": 5.0,   "abnormal_flag": "H",  "collected_date": "2026-10-14"},
            {"loinc_code": "2085-9",  "value": 1.1,  "unit": "mmol/L",      "reference_range_low": 1.0,  "reference_range_high": 9.9,   "abnormal_flag": "N",  "collected_date": "2026-10-14"},
            {"loinc_code": "13457-7", "value": 3.4,  "unit": "mmol/L",      "reference_range_low": 0.0,  "reference_range_high": 3.4,   "abnormal_flag": "N",  "collected_date": "2026-10-14"},
            {"loinc_code": "2571-8",  "value": 1.9,  "unit": "mmol/L",      "reference_range_low": 0.0,  "reference_range_high": 1.7,   "abnormal_flag": "H",  "collected_date": "2026-10-14"},
            {"loinc_code": "14957-5", "value": 3.8,  "unit": "mg/L",        "reference_range_low": 0.0,  "reference_range_high": 3.0,   "abnormal_flag": "H",  "collected_date": "2026-10-14"}
        ],
        "immunizations": [
            {"vaccine_code": "46233009",  "vaccine_display": "Influenza virus vaccine", "date_given": "2026-04-10"},
            {"vaccine_code": "333621000", "vaccine_display": "Pneumococcal vaccine",    "date_given": "2022-06-01"}
        ],
        "social_history": {
            "smoking_status_code": "8517006",
            "smoking_status_display": "Ex-smoker",
            "pack_years": 10.0,
            "alcohol_status_code": "228276006",
            "alcohol_units_per_week": 5.0,
            "occupation": "School teacher",
            "lives_alone": False
        },
        "clinical_notes": [
            {
                "section": "examination",
                "text": "BP elevated at 148/92. BMI 33.1 — obese. Mild bilateral ankle pitting oedema (1+). Heart sounds dual, no murmur. Chest clear. Abdomen soft, no organomegaly.",
                "author": "Dr Rangi Parata"
            },
            {
                "section": "assessment and plan",
                "text": "T2DM suboptimally controlled — HbA1c 7.8%, target <7.0%. Hypertension not at target. Plan: (1) Increase Metformin to 1000mg BD. (2) Add Amlodipine 5mg daily for BP. (3) Reinforce dietary advice, refer to dietitian. (4) Ankle oedema likely secondary to Amlodipine — monitor. (5) Repeat HbA1c and renal function in 3 months.",
                "author": "Dr Rangi Parata"
            }
        ]
    },

    # ------------------------------------------------------------------
    # 2. Hemi Ngata — Māori male, asthma, annual health check
    # ------------------------------------------------------------------
    {
        "nhi_number": "ZAA0002",
        "family_name": "Ngata",
        "given_names": "Hemi",
        "date_of_birth": "1980-06-22",
        "sex": "male",
        "redcap_event_name": "baseline_arm_1",
        "sex_at_birth": "male",
        "ethnicity_codes": ["21111"],
        "address": {
            "street": "7 Ngongotaha Road",
            "suburb": "Ngongotaha",
            "city": "Rotorua",
            "postcode": "3010",
            "region": "Lakes"
        },
        "phone": "027 555 0202",
        "gp_name": "Dr Sarah Thompson",
        "gp_practice": "Rotorua Lakes Primary Health",
        "pho": "Midlands Health Network",
        "encounter_date": "2026-10-16",
        "encounter_type": "ambulatory",
        "presenting_complaint": "Annual health check. Asthma well controlled on current regime. No recent exacerbations.",
        "clinician_name": "Dr Sarah Thompson",
        "clinician_role": "GP",
        "vitals": {
            "systolic_bp": 124.0,
            "diastolic_bp": 78.0,
            "heart_rate": 68.0,
            "respiratory_rate": 14.0,
            "temperature": 36.5,
            "spo2": 99.0,
            "weight_kg": 88.0,
            "height_cm": 178.0
        },
        "conditions": [
            {
                "snomed_code": "195967001",
                "display": "Asthma",
                "onset_date": "2005-01-01",
                "status": "active"
            }
        ],
        "medications": [
            {
                "snomed_code": "373873005",
                "name": "Salbutamol",
                "dose": "100mcg",
                "frequency": "as required",
                "route": "inhaled",
                "start_date": "2005-06-01",
                "status": "active"
            },
            {
                "snomed_code": "373254001",
                "name": "Fluticasone",
                "dose": "250mcg",
                "frequency": "twice daily",
                "route": "inhaled",
                "start_date": "2010-03-15",
                "status": "active"
            }
        ],
        "allergies": [],
        "lab_results": [
            {"loinc_code": "718-7",  "value": 158.0, "unit": "g/L",    "reference_range_low": 130.0, "reference_range_high": 170.0, "abnormal_flag": "N", "collected_date": "2026-10-15"},
            {"loinc_code": "6690-2", "value": 6.8,   "unit": "10^9/L", "reference_range_low": 4.0,   "reference_range_high": 11.0,  "abnormal_flag": "N", "collected_date": "2026-10-15"},
            {"loinc_code": "777-3",  "value": 245.0, "unit": "10^9/L", "reference_range_low": 150.0, "reference_range_high": 400.0, "abnormal_flag": "N", "collected_date": "2026-10-15"},
            {"loinc_code": "2951-2", "value": 139.0, "unit": "mmol/L", "reference_range_low": 135.0, "reference_range_high": 145.0, "abnormal_flag": "N", "collected_date": "2026-10-15"},
            {"loinc_code": "2823-3", "value": 4.1,   "unit": "mmol/L", "reference_range_low": 3.5,   "reference_range_high": 5.0,   "abnormal_flag": "N", "collected_date": "2026-10-15"},
            {"loinc_code": "2093-3", "value": 4.6,   "unit": "mmol/L", "reference_range_low": 0.0,   "reference_range_high": 5.0,   "abnormal_flag": "N", "collected_date": "2026-10-15"}
        ],
        "immunizations": [
            {"vaccine_code": "46233009", "vaccine_display": "Influenza virus vaccine", "date_given": "2026-04-08"}
        ],
        "social_history": {
            "smoking_status_code": "266919005",
            "smoking_status_display": "Never smoked",
            "alcohol_status_code": "228276006",
            "alcohol_units_per_week": 4.0,
            "occupation": "Electrician",
            "lives_alone": False
        },
        "clinical_notes": [
            {
                "section": "examination",
                "text": "Well-looking male. BMI 27.8 — overweight. BP 124/78 — normal. Chest clear, good air entry bilaterally, no wheeze at rest. Peak flow 520 L/min (predicted 630 — 83%). Heart sounds dual, no added sounds.",
                "author": "Dr Sarah Thompson"
            },
            {
                "section": "assessment and plan",
                "text": "Asthma partially controlled — peak flow 83% predicted. No acute exacerbations in past 12 months. Continue current inhaler regime. Reviewed inhaler technique — adequate. Advised to maintain asthma action plan. Annual influenza vaccination given today. BMI counselling — encourage activity and healthy eating. Routine bloods reviewed — all normal. Return in 12 months or sooner if concerns.",
                "author": "Dr Sarah Thompson"
            }
        ]
    },

    # ------------------------------------------------------------------
    # 3. Lien Nguyen — Vietnamese NZ female, COPD + depression
    # ------------------------------------------------------------------
    {
        "nhi_number": "ZAA0003",
        "family_name": "Nguyen",
        "given_names": "Lien",
        "date_of_birth": "1958-11-03",
        "sex": "female",
        "redcap_event_name": "baseline_arm_1",
        "sex_at_birth": "female",
        "ethnicity_codes": ["41311"],
        "address": {
            "street": "22 Aro Street",
            "suburb": "Aro Valley",
            "city": "Wellington",
            "postcode": "6021",
            "region": "Capital and Coast"
        },
        "phone": "04 555 0303",
        "gp_name": "Dr James Park",
        "gp_practice": "Wellington City Medical",
        "pho": "Compass Health",
        "encounter_date": "2026-10-14",
        "encounter_type": "ambulatory",
        "presenting_complaint": "Increasing shortness of breath over the past 10 days. COPD follow-up. Also requesting repeat of Sertraline.",
        "clinician_name": "Dr James Park",
        "clinician_role": "GP",
        "vitals": {
            "systolic_bp": 138.0,
            "diastolic_bp": 84.0,
            "heart_rate": 92.0,
            "respiratory_rate": 20.0,
            "temperature": 37.2,
            "spo2": 93.0,
            "weight_kg": 58.0,
            "height_cm": 155.0
        },
        "conditions": [
            {
                "snomed_code": "13645005",
                "display": "Chronic obstructive pulmonary disease",
                "onset_date": "2018-05-01",
                "status": "active"
            },
            {
                "snomed_code": "35489007",
                "display": "Depressive disorder",
                "onset_date": "2020-02-14",
                "status": "active"
            }
        ],
        "medications": [
            {
                "snomed_code": "373873005",
                "name": "Salbutamol",
                "dose": "100mcg",
                "frequency": "as required",
                "route": "inhaled",
                "start_date": "2018-05-10",
                "status": "active"
            },
            {
                "snomed_code": "372762008",
                "name": "Sertraline",
                "dose": "50mg",
                "frequency": "once daily",
                "route": "oral",
                "start_date": "2020-03-01",
                "status": "active"
            },
            {
                "snomed_code": "372588000",
                "name": "Prednisolone",
                "dose": "30mg",
                "frequency": "once daily for 5 days",
                "route": "oral",
                "start_date": "2026-10-14",
                "status": "active",
                "end_date": "2026-10-19"
            }
        ],
        "allergies": [
            {
                "allergen_code": "387207008",
                "allergen_display": "Ibuprofen",
                "reaction": "Bronchospasm",
                "severity": "severe",
                "status": "active"
            }
        ],
        "lab_results": [
            {"loinc_code": "718-7",   "value": 109.0, "unit": "g/L",   "reference_range_low": 115.0, "reference_range_high": 160.0, "abnormal_flag": "L", "collected_date": "2026-10-13"},
            {"loinc_code": "1988-5",  "value": 22.0,  "unit": "mg/L",  "reference_range_low": 0.0,   "reference_range_high": 10.0,  "abnormal_flag": "H", "collected_date": "2026-10-13"},
            {"loinc_code": "6690-2",  "value": 11.8,  "unit": "10^9/L","reference_range_low": 4.0,   "reference_range_high": 11.0,  "abnormal_flag": "H", "collected_date": "2026-10-13"},
            {"loinc_code": "2951-2",  "value": 141.0, "unit": "mmol/L","reference_range_low": 135.0, "reference_range_high": 145.0, "abnormal_flag": "N", "collected_date": "2026-10-13"},
            {"loinc_code": "2823-3",  "value": 3.8,   "unit": "mmol/L","reference_range_low": 3.5,   "reference_range_high": 5.0,   "abnormal_flag": "N", "collected_date": "2026-10-13"},
            {"loinc_code": "2160-0",  "value": 68.0,  "unit": "umol/L","reference_range_low": 45.0,  "reference_range_high": 90.0,  "abnormal_flag": "N", "collected_date": "2026-10-13"}
        ],
        "immunizations": [
            {"vaccine_code": "46233009",  "vaccine_display": "Influenza virus vaccine",  "date_given": "2026-04-05"},
            {"vaccine_code": "1119349007","vaccine_display": "COVID-19 vaccine",          "date_given": "2025-10-20"}
        ],
        "social_history": {
            "smoking_status_code": "8517006",
            "smoking_status_display": "Ex-smoker",
            "pack_years": 30.0,
            "alcohol_status_code": "228274009",
            "alcohol_units_per_week": 0.0,
            "occupation": "Retired (former seamstress)",
            "lives_alone": True
        },
        "clinical_notes": [
            {
                "section": "examination",
                "text": "Unwell-looking female, mildly breathless at rest. SpO2 93% on air — low. RR 20. Temp 37.2. Chest: diffuse expiratory wheeze, reduced air entry at left base, dullness to percussion left base. Heart: tachycardic at 92. Abdomen: soft, non-tender.",
                "author": "Dr James Park"
            },
            {
                "section": "assessment and plan",
                "text": "Acute COPD exacerbation with possible left lower lobe consolidation. Plan: (1) Prednisolone 30mg daily x 5 days. (2) Amoxicillin 500mg TDS x 5 days (no penicillin allergy documented — check — patient reports tolerance). (3) Increase Salbutamol to QID until review. (4) Chest X-ray ordered. (5) SpO2 monitoring — if drops below 90% refer to ED. (6) Sertraline renewed x 3 months. (7) Review in 5 days or sooner if worsening. (8) Anaemia noted — Hb 109 — likely anaemia of chronic disease, follow up once acute episode resolved.",
                "author": "Dr James Park"
            }
        ]
    }
]


# ---------------------------------------------------------------------------
# Follow-up encounters (longitudinal — same NHI as existing patient)
# ---------------------------------------------------------------------------

FOLLOWUP_ENCOUNTERS = [
    {
        "nhi_number": "ZAA0001",
        "family_name": "Tane",
        "given_names": "Aroha",
        "date_of_birth": "1975-03-15",
        "sex": "female",
        "redcap_event_name": "followup_1_arm_1",
        "encounter_date": "2026-07-15",
        "encounter_type": "ambulatory",
        "presenting_complaint": "3-month diabetes review",
        "clinician_name": "Dr Hemi Parata",
        "clinician_role": "GP",
        "vitals": {
            "systolic_bp": 128,
            "diastolic_bp": 82,
            "heart_rate": 72,
            "weight_kg": 86.2,
            "bmi": 32.1,
        },
        "conditions": [],
        "medications": [],
        "allergies": [],
        "lab_results": [],
        "immunizations": [],
    }
]


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

def _seed_record(p: dict, label: str = "record") -> None:
    name = f"{p['given_names']} {p['family_name']}"
    nhi = p.get("nhi_number", "—")
    event = p.get("redcap_event_name", "baseline_arm_1")

    print(f"  Creating {label}: {name} ({nhi}, {event})…", end=" ", flush=True)
    try:
        rec = post("/api/records", p)
    except urllib.error.URLError as e:
        print(f"\n  ERROR — could not reach {BASE}: {e}")
        print("  Is the app running?  bash run.sh")
        sys.exit(1)
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"\n  ERROR {e.code}: {body}")
        sys.exit(1)

    record_id = rec["record_id"]
    print(f"OK (id={record_id[:8]}…)")

    print(f"  Converting to FHIR…", end=" ", flush=True)
    try:
        result = post(f"/api/records/{record_id}/convert", {})
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"\n  ERROR {e.code}: {body}")
        sys.exit(1)

    bundle_id = result["bundle_id"]
    resource_count = result["resource_count"]
    hapi = result.get("hapi", {})
    hapi_status = hapi.get("status", "—")
    print(f"OK (bundle={bundle_id[:8]}…, {resource_count} resources, HAPI={hapi_status})")
    print()


def main() -> None:
    print(f"Seeding demo data → {BASE}\n")

    for p in PATIENTS:
        _seed_record(p, "record")

    print("Seeding follow-up encounters…\n")
    for p in FOLLOWUP_ENCOUNTERS:
        _seed_record(p, "follow-up")

    print("Done. Open http://localhost:8000 → Records tab to see the patients.")
    print("      Open FHIR Store to browse the generated bundles.")


if __name__ == "__main__":
    main()
