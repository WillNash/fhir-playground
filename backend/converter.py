"""
Clinical record -> FHIR R4 resource conversion.

Produces a FHIR Transaction Bundle containing:
  - Patient
  - Encounter
  - Observation (vitals + labs)
  - Condition  (problem list)
  - MedicationStatement (current meds)
  - AllergyIntolerance
  - Immunization
  - Procedure (none yet — placeholder)
  - Composition (clinical note)

All resources reference the NZ Base IG profiles where they exist:
  https://fhir.org.nz/ig/base/

FHIR version: R4  (https://hl7.org/fhir/R4/)
"""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from .snomed import (
    SNOMED_SYSTEM,
    NZ_ETHNICITY_SYSTEM,
    NHI_SYSTEM,
    LOINC_SYSTEM,
    OBSERVATIONS,
    NZ_ETHNICITY,
)

# NZ Base IG profile URLs (canonical — https://fhir.org.nz/ig/base/)
NZ_BASE_PATIENT_PROFILE = "https://fhir.org.nz/ig/base/StructureDefinition/NzPatient"
NZ_BASE_ENCOUNTER_PROFILE = "https://fhir.org.nz/ig/base/StructureDefinition/NzEncounter"

FHIR_VERSION = "4.0.1"

_NZ_TZ = ZoneInfo("Pacific/Auckland")


def _now_nz() -> str:
    """Return current NZ time as ISO 8601 with NZ UTC offset (+13:00 NZDT or +12:00 NZST)."""
    return datetime.now(_NZ_TZ).isoformat(timespec="seconds")


def _uuid() -> str:
    return str(uuid.uuid4())


def _ref(resource_type: str, resource_id: str) -> Dict[str, str]:
    return {"reference": f"{resource_type}/{resource_id}"}


# ---------------------------------------------------------------------------
# Individual resource builders
# ---------------------------------------------------------------------------

def build_patient(record: Dict[str, Any]) -> Dict[str, Any]:
    patient_id = _uuid()

    identifiers = []
    if record.get("nhi_number"):
        identifiers.append({
            "use": "official",
            "system": NHI_SYSTEM,
            "value": record["nhi_number"].upper(),
        })

    # NZ ethnicity extensions (NZ Base IG)
    extensions = []
    for code in record.get("ethnicity_codes", []):
        display = NZ_ETHNICITY.get(code, code)
        extensions.append({
            "url": "http://hl7.org.nz/fhir/StructureDefinition/nz-ethnicity",
            "valueCodeableConcept": {
                "coding": [{
                    "system": NZ_ETHNICITY_SYSTEM,
                    "code": code,
                    "display": display,
                }],
                "text": display,
            },
        })

    given = [n.strip() for n in record.get("given_names", "").split() if n.strip()]

    address = []
    addr_raw = record.get("address") or {}
    if isinstance(addr_raw, dict) and any(addr_raw.values()):
        lines = []
        if addr_raw.get("street"):
            lines.append(addr_raw["street"])
        a = {"use": "home", "type": "physical"}
        if lines:
            a["line"] = lines
        if addr_raw.get("suburb"):
            a["district"] = addr_raw["suburb"]
        if addr_raw.get("city"):
            a["city"] = addr_raw["city"]
        if addr_raw.get("postcode"):
            a["postalCode"] = addr_raw["postcode"]
        a["country"] = "NZ"
        address.append(a)

    telecom = []
    if record.get("phone"):
        telecom.append({"system": "phone", "value": record["phone"], "use": "mobile"})
    if record.get("email"):
        telecom.append({"system": "email", "value": record["email"]})

    patient: Dict[str, Any] = {
        "resourceType": "Patient",
        "id": patient_id,
        "meta": {
            "profile": [NZ_BASE_PATIENT_PROFILE],
            "lastUpdated": _now_nz(),
        },
        "identifier": identifiers,
        "name": [{
            "use": "official",
            "family": record.get("family_name", ""),
            "given": given,
        }],
        "birthDate": record.get("date_of_birth", ""),
        "gender": record.get("sex", "unknown"),
    }

    if extensions:
        patient["extension"] = extensions
    if address:
        patient["address"] = address
    if telecom:
        patient["telecom"] = telecom
    if record.get("gender_identity"):
        patient.setdefault("extension", []).append({
            "url": "http://hl7.org.nz/fhir/StructureDefinition/gender-original-text",
            "valueString": record["gender_identity"],
        })

    # NZ Base IG sex-at-birth extension (confirmed URL from NzPatient ci-build)
    sab = record.get("sex_at_birth")
    if sab:
        patient.setdefault("extension", []).append({
            "url": "http://hl7.org.nz/fhir/StructureDefinition/sex-at-birth",
            "valueCodeableConcept": {
                "coding": [{
                    "system": "http://hl7.org/fhir/administrative-gender",
                    "code": sab,
                    "display": sab.capitalize(),
                }]
            },
        })

    return patient


def build_organization_ref(record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Return a contained Organization if GP practice is known."""
    if not record.get("gp_practice"):
        return None
    org_id = _uuid()
    return {
        "resourceType": "Organization",
        "id": org_id,
        "name": record["gp_practice"],
        "type": [{
            "coding": [{
                "system": "http://terminology.hl7.org/CodeSystem/organization-type",
                "code": "prov",
                "display": "Healthcare Provider",
            }]
        }],
    }


def build_encounter(record: Dict[str, Any], patient_id: str) -> Dict[str, Any]:
    encounter_id = _uuid()

    # Map encounter type to FHIR class
    type_map = {
        "ambulatory": {"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "code": "AMB", "display": "ambulatory"},
        "inpatient": {"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "code": "IMP", "display": "inpatient"},
        "emergency": {"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "code": "EMER", "display": "emergency"},
        "telehealth": {"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "code": "VR", "display": "virtual"},
    }
    enc_class = type_map.get(record.get("encounter_type", "ambulatory"),
                              type_map["ambulatory"])

    enc_date = record.get("encounter_date", _now_nz()[:10])

    encounter: Dict[str, Any] = {
        "resourceType": "Encounter",
        "id": encounter_id,
        "meta": {
            "profile": [NZ_BASE_ENCOUNTER_PROFILE],
            "lastUpdated": _now_nz(),
        },
        "status": "finished",
        "class": enc_class,
        "subject": _ref("Patient", patient_id),
        "period": {"start": enc_date, "end": enc_date},
    }

    if record.get("presenting_complaint"):
        encounter["reasonCode"] = [{
            "text": record["presenting_complaint"],
        }]

    if record.get("clinician_name"):
        enc_type_code = record.get("clinician_role", "GP")
        encounter["participant"] = [{
            "type": [{"text": enc_type_code}],
            "individual": {"display": record["clinician_name"]},
        }]

    return encounter


def build_vitals(vitals_raw: Dict[str, Any], patient_id: str, encounter_id: str,
                  encounter_date: str) -> List[Dict[str, Any]]:
    """Build FHIR Observation resources for each vital sign recorded."""
    observations = []

    # Map of field name -> LOINC code (spo2 handled separately below)
    field_map = {
        "systolic_bp": "8480-6",
        "diastolic_bp": "8462-4",
        "heart_rate": "8867-4",
        "respiratory_rate": "9279-1",
        "temperature": "8310-5",
        "weight_kg": "29463-7",
        "height_cm": "8302-2",
        "bmi": "39156-5",
    }

    # Build BP panel separately if both components present
    sbp = vitals_raw.get("systolic_bp")
    dbp = vitals_raw.get("diastolic_bp")
    if sbp and dbp:
        bp_id = _uuid()
        observations.append({
            "resourceType": "Observation",
            "id": bp_id,
            "meta": {"profile": ["http://hl7.org/fhir/StructureDefinition/bp"]},
            "status": "final",
            "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/observation-category",
                                       "code": "vital-signs", "display": "Vital Signs"}]}],
            "code": {"coding": [{"system": LOINC_SYSTEM, "code": "85354-9",
                                  "display": "Blood pressure panel with all children optional"}],
                     "text": "Blood pressure"},
            "subject": _ref("Patient", patient_id),
            "encounter": _ref("Encounter", encounter_id),
            "effectiveDateTime": encounter_date,
            "component": [
                {
                    "code": {"coding": [{"system": LOINC_SYSTEM, "code": "8480-6",
                                         "display": "Systolic blood pressure"}]},
                    "valueQuantity": {"value": sbp, "unit": "mmHg",
                                      "system": "http://unitsofmeasure.org", "code": "mm[Hg]"},
                },
                {
                    "code": {"coding": [{"system": LOINC_SYSTEM, "code": "8462-4",
                                         "display": "Diastolic blood pressure"}]},
                    "valueQuantity": {"value": dbp, "unit": "mmHg",
                                      "system": "http://unitsofmeasure.org", "code": "mm[Hg]"},
                },
            ],
        })

    # SpO2 — dual-coded per FHIR R4 Vital Signs profile (primary 2708-6, supplementary 59408-5)
    spo2_val = vitals_raw.get("spo2")
    if spo2_val is not None:
        spo2_id = _uuid()
        observations.append({
            "resourceType": "Observation",
            "id": spo2_id,
            "status": "final",
            "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/observation-category",
                                       "code": "vital-signs", "display": "Vital Signs"}]}],
            "code": {
                "coding": [
                    {"system": LOINC_SYSTEM, "code": "2708-6",
                     "display": "Oxygen saturation in Arterial blood"},
                    {"system": LOINC_SYSTEM, "code": "59408-5",
                     "display": "Oxygen saturation by Pulse oximetry"},
                ],
                "text": "Oxygen saturation",
            },
            "subject": _ref("Patient", patient_id),
            "encounter": _ref("Encounter", encounter_id),
            "effectiveDateTime": encounter_date,
            "valueQuantity": {
                "value": spo2_val,
                "unit": "%",
                "system": "http://unitsofmeasure.org",
                "code": "%",
            },
        })

    # Remaining individual vitals
    skip_for_bp = {"systolic_bp", "diastolic_bp"}
    for field, loinc in field_map.items():
        if field in skip_for_bp:
            continue
        value = vitals_raw.get(field)
        if value is None:
            continue
        obs_meta = OBSERVATIONS.get(loinc, {})
        obs_id = _uuid()
        obs: Dict[str, Any] = {
            "resourceType": "Observation",
            "id": obs_id,
            "status": "final",
            "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/observation-category",
                                       "code": "vital-signs", "display": "Vital Signs"}]}],
            "code": {"coding": [{"system": LOINC_SYSTEM, "code": loinc,
                                  "display": obs_meta.get("display", field)}],
                     "text": obs_meta.get("display", field)},
            "subject": _ref("Patient", patient_id),
            "encounter": _ref("Encounter", encounter_id),
            "effectiveDateTime": encounter_date,
            "valueQuantity": {
                "value": value,
                "unit": obs_meta.get("unit", ""),
                "system": "http://unitsofmeasure.org",
                "code": obs_meta.get("ucum", ""),
            },
        }
        observations.append(obs)

    return observations


def build_lab_observation(lab: Dict[str, Any], patient_id: str, encounter_id: str) -> Dict[str, Any]:
    obs_meta = OBSERVATIONS.get(lab.get("loinc_code", ""), {})
    obs_id = _uuid()
    obs: Dict[str, Any] = {
        "resourceType": "Observation",
        "id": obs_id,
        "status": "final",
        "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/observation-category",
                                   "code": "laboratory", "display": "Laboratory"}]}],
        "code": {"coding": [{"system": LOINC_SYSTEM, "code": lab["loinc_code"],
                              "display": obs_meta.get("display", lab.get("loinc_code", ""))}],
                 "text": obs_meta.get("display", lab.get("loinc_code", ""))},
        "subject": _ref("Patient", patient_id),
        "encounter": _ref("Encounter", encounter_id),
        "effectiveDateTime": lab.get("collected_date", _now_nz()[:10]),
        "valueQuantity": {
            "value": lab["value"],
            "unit": lab.get("unit", obs_meta.get("unit", "")),
            "system": "http://unitsofmeasure.org",
            "code": obs_meta.get("ucum", lab.get("unit", "")),
        },
    }

    # Reference range
    low = lab.get("reference_range_low")
    high = lab.get("reference_range_high")
    if low is not None or high is not None:
        rr: Dict[str, Any] = {}
        if low is not None:
            rr["low"] = {"value": low, "unit": lab.get("unit", ""),
                         "system": "http://unitsofmeasure.org",
                         "code": obs_meta.get("ucum", "")}
        if high is not None:
            rr["high"] = {"value": high, "unit": lab.get("unit", ""),
                          "system": "http://unitsofmeasure.org",
                          "code": obs_meta.get("ucum", "")}
        obs["referenceRange"] = [rr]

    flag = lab.get("abnormal_flag")
    if flag and flag != "N":
        interp_map = {
            "H": ("H", "High"),
            "L": ("L", "Low"),
            "HH": ("HH", "Critical High"),
            "LL": ("LL", "Critical Low"),
        }
        code, display = interp_map.get(flag, ("A", "Abnormal"))
        obs["interpretation"] = [{"coding": [{
            "system": "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation",
            "code": code, "display": display,
        }]}]

    return obs


def build_condition(cond: Dict[str, Any], patient_id: str, encounter_id: str) -> Dict[str, Any]:
    cond_id = _uuid()

    status_map = {
        "active": "active",
        "resolved": "resolved",
        "inactive": "inactive",
    }
    clin_status = status_map.get(cond.get("status", "active"), "active")

    fhir_cond: Dict[str, Any] = {
        "resourceType": "Condition",
        "id": cond_id,
        "clinicalStatus": {"coding": [{
            "system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
            "code": clin_status,
            "display": clin_status.capitalize(),
        }]},
        "verificationStatus": {"coding": [{
            "system": "http://terminology.hl7.org/CodeSystem/condition-ver-status",
            "code": "confirmed",
            "display": "Confirmed",
        }]},
        "code": {"coding": [{
            "system": SNOMED_SYSTEM,
            "code": cond.get("snomed_code", ""),
            "display": cond.get("display", ""),
        }],
            "text": cond.get("display", ""),
        },
        "subject": _ref("Patient", patient_id),
        "encounter": _ref("Encounter", encounter_id),
    }

    if cond.get("onset_date"):
        fhir_cond["onsetDateTime"] = cond["onset_date"]
    if cond.get("notes"):
        fhir_cond["note"] = [{"text": cond["notes"]}]

    return fhir_cond


def build_medication_statement(med: Dict[str, Any], patient_id: str, encounter_id: str) -> Dict[str, Any]:
    med_id = _uuid()

    status_map = {
        "active": "active",
        "stopped": "stopped",
        "on-hold": "on-hold",
    }
    fhir_status = status_map.get(med.get("status", "active"), "active")

    dosage: List[Dict[str, Any]] = []
    if med.get("dose") or med.get("frequency") or med.get("route"):
        d: Dict[str, Any] = {}
        if med.get("dose"):
            d["text"] = med["dose"]
        if med.get("frequency"):
            d["timing"] = {"repeat": {"boundsPeriod": {}}, "code": {"text": med["frequency"]}}
        if med.get("route"):
            d["route"] = {"text": med["route"]}
        dosage.append(d)

    stmt: Dict[str, Any] = {
        "resourceType": "MedicationStatement",
        "id": med_id,
        "status": fhir_status,
        "medicationCodeableConcept": {"coding": [{
            "system": SNOMED_SYSTEM,
            "code": med.get("snomed_code", ""),
            "display": med.get("name", ""),
        }],
            "text": med.get("name", ""),
        },
        "subject": _ref("Patient", patient_id),
        "context": _ref("Encounter", encounter_id),
    }

    if med.get("start_date"):
        stmt["effectivePeriod"] = {"start": med["start_date"]}
        if med.get("end_date"):
            stmt["effectivePeriod"]["end"] = med["end_date"]
    if dosage:
        stmt["dosage"] = dosage

    return stmt


def build_allergy(allergy: Dict[str, Any], patient_id: str) -> Dict[str, Any]:
    allergy_id = _uuid()

    severity_map = {
        "mild": "mild",
        "moderate": "moderate",
        "severe": "severe",
    }
    fhir_severity = severity_map.get(allergy.get("severity", ""), None)

    ai: Dict[str, Any] = {
        "resourceType": "AllergyIntolerance",
        "id": allergy_id,
        "clinicalStatus": {"coding": [{
            "system": "http://terminology.hl7.org/CodeSystem/allergyintolerance-clinical",
            "code": "active", "display": "Active",
        }]},
        "verificationStatus": {"coding": [{
            "system": "http://terminology.hl7.org/CodeSystem/allergyintolerance-verification",
            "code": "confirmed", "display": "Confirmed",
        }]},
        "type": "allergy",
        "category": ["medication"],
        "code": {"coding": [{
            "system": SNOMED_SYSTEM,
            "code": allergy.get("allergen_code", ""),
            "display": allergy.get("allergen_display", ""),
        }],
            "text": allergy.get("allergen_display", ""),
        },
        "patient": _ref("Patient", patient_id),
    }

    if allergy.get("reaction") or fhir_severity:
        rxn: Dict[str, Any] = {}
        if allergy.get("reaction"):
            rxn["manifestation"] = [{"text": allergy["reaction"]}]
        if fhir_severity:
            rxn["severity"] = fhir_severity
        ai["reaction"] = [rxn]

    return ai


def build_immunization(imm: Dict[str, Any], patient_id: str, encounter_id: str) -> Dict[str, Any]:
    imm_id = _uuid()
    return {
        "resourceType": "Immunization",
        "id": imm_id,
        "status": "completed",
        "vaccineCode": {"coding": [{
            "system": SNOMED_SYSTEM,
            "code": imm.get("vaccine_code", ""),
            "display": imm.get("vaccine_display", ""),
        }],
            "text": imm.get("vaccine_display", ""),
        },
        "patient": _ref("Patient", patient_id),
        "encounter": _ref("Encounter", encounter_id),
        "occurrenceDateTime": imm.get("date_given", _now_nz()[:10]),
        **({"lotNumber": imm["lot_number"]} if imm.get("lot_number") else {}),
        **({"site": {"text": imm["site"]}} if imm.get("site") else {}),
    }


def build_social_history_observations(social: Dict[str, Any], patient_id: str,
                                       encounter_id: str, encounter_date: str) -> List[Dict[str, Any]]:
    obs_list = []

    if social.get("smoking_status_code"):
        obs_id = _uuid()
        obs_list.append({
            "resourceType": "Observation",
            "id": obs_id,
            "status": "final",
            "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/observation-category",
                                       "code": "social-history", "display": "Social History"}]}],
            "code": {"coding": [{"system": LOINC_SYSTEM, "code": "72166-2",
                                  "display": "Tobacco smoking status"}]},
            "subject": _ref("Patient", patient_id),
            "encounter": _ref("Encounter", encounter_id),
            "effectiveDateTime": encounter_date,
            "valueCodeableConcept": {"coding": [{
                "system": SNOMED_SYSTEM,
                "code": social["smoking_status_code"],
                "display": social.get("smoking_status_display", ""),
            }]},
        })

    if social.get("alcohol_units_per_week") is not None:
        obs_id = _uuid()
        obs_list.append({
            "resourceType": "Observation",
            "id": obs_id,
            "status": "final",
            "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/observation-category",
                                       "code": "social-history", "display": "Social History"}]}],
            "code": {"coding": [{"system": LOINC_SYSTEM, "code": "74013-4",
                                  "display": "Alcoholic drinks per week"}]},
            "subject": _ref("Patient", patient_id),
            "encounter": _ref("Encounter", encounter_id),
            "effectiveDateTime": encounter_date,
            "valueQuantity": {
                "value": social["alcohol_units_per_week"],
                "unit": "units/week",
                "system": "http://unitsofmeasure.org",
                "code": "{drinks}/wk",
            },
        })

    return obs_list


def build_composition(record: Dict[str, Any], patient_id: str, encounter_id: str,
                       section_entries: Dict[str, List[Dict[str, str]]]) -> Dict[str, Any]:
    comp_id = _uuid()
    notes = record.get("clinical_notes", [])

    sections = []
    for section_name, entries in section_entries.items():
        sec: Dict[str, Any] = {
            "title": section_name,
            "code": {"text": section_name},
            "entry": [{"reference": f"{e['resourceType']}/{e['id']}"} for e in entries],
        }
        sections.append(sec)

    # Add free-text note sections
    for note in notes:
        sections.append({
            "title": note.get("section", "Note").title(),
            "code": {"text": note.get("section", "note")},
            "text": {
                "status": "generated",
                "div": f"<div xmlns=\"http://www.w3.org/1999/xhtml\">{note.get('text', '')}</div>",
            },
        })

    return {
        "resourceType": "Composition",
        "id": comp_id,
        "status": "final",
        "type": {"coding": [{"system": LOINC_SYSTEM, "code": "11506-3",
                              "display": "Progress note"}],
                 "text": "Clinical encounter note"},
        "subject": _ref("Patient", patient_id),
        "encounter": _ref("Encounter", encounter_id),
        "date": _now_nz(),
        "author": [{"display": record.get("clinician_name", "Unknown")}],
        "title": f"Encounter note - {record.get('encounter_date', '')}",
        "section": sections,
    }


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def clinical_record_to_fhir_bundle(record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert a raw clinical PatientRecord dict into a FHIR R4 Transaction Bundle.
    Returns the Bundle dict ready for persistence.
    """
    bundle_id = _uuid()
    entries: List[Dict[str, Any]] = []

    def _entry(resource: Dict[str, Any]) -> Dict[str, Any]:
        rid = resource["id"]
        rtype = resource["resourceType"]
        return {
            "fullUrl": f"urn:uuid:{rid}",
            "resource": resource,
            "request": {
                "method": "PUT",
                "url": f"{rtype}/{rid}",
            },
        }

    # Patient
    patient = build_patient(record)
    patient_id = patient["id"]
    entries.append(_entry(patient))

    # Encounter
    encounter = build_encounter(record, patient_id)
    encounter_id = encounter["id"]
    encounter_date = record.get("encounter_date", _now_nz()[:10])
    entries.append(_entry(encounter))

    # Track resources per section for Composition
    section_entries: Dict[str, List[Dict[str, str]]] = {
        "Vital Signs": [],
        "Laboratory Results": [],
        "Conditions": [],
        "Medications": [],
        "Allergies": [],
        "Immunizations": [],
        "Social History": [],
    }

    # Vitals
    vitals_raw = record.get("vitals") or {}
    if isinstance(vitals_raw, dict):
        vital_obs = build_vitals(vitals_raw, patient_id, encounter_id, encounter_date)
        for obs in vital_obs:
            entries.append(_entry(obs))
            section_entries["Vital Signs"].append({"resourceType": obs["resourceType"], "id": obs["id"]})

    # Lab results
    for lab in record.get("lab_results", []):
        if isinstance(lab, dict):
            obs = build_lab_observation(lab, patient_id, encounter_id)
            entries.append(_entry(obs))
            section_entries["Laboratory Results"].append({"resourceType": obs["resourceType"], "id": obs["id"]})

    # Conditions
    for cond in record.get("conditions", []):
        if isinstance(cond, dict):
            fhir_cond = build_condition(cond, patient_id, encounter_id)
            entries.append(_entry(fhir_cond))
            section_entries["Conditions"].append({"resourceType": fhir_cond["resourceType"], "id": fhir_cond["id"]})

    # Medications
    for med in record.get("medications", []):
        if isinstance(med, dict):
            stmt = build_medication_statement(med, patient_id, encounter_id)
            entries.append(_entry(stmt))
            section_entries["Medications"].append({"resourceType": stmt["resourceType"], "id": stmt["id"]})

    # Allergies
    for allergy in record.get("allergies", []):
        if isinstance(allergy, dict):
            ai = build_allergy(allergy, patient_id)
            entries.append(_entry(ai))
            section_entries["Allergies"].append({"resourceType": ai["resourceType"], "id": ai["id"]})

    # Immunizations
    for imm in record.get("immunizations", []):
        if isinstance(imm, dict):
            fhir_imm = build_immunization(imm, patient_id, encounter_id)
            entries.append(_entry(fhir_imm))
            section_entries["Immunizations"].append({"resourceType": fhir_imm["resourceType"], "id": fhir_imm["id"]})

    # Social history
    social = record.get("social_history") or {}
    if isinstance(social, dict) and any(social.values()):
        social_obs = build_social_history_observations(social, patient_id, encounter_id, encounter_date)
        for obs in social_obs:
            entries.append(_entry(obs))
            section_entries["Social History"].append({"resourceType": obs["resourceType"], "id": obs["id"]})

    # Composition (clinical document index)
    composition = build_composition(record, patient_id, encounter_id, section_entries)
    entries.append(_entry(composition))

    # Build the Bundle
    bundle: Dict[str, Any] = {
        "resourceType": "Bundle",
        "id": bundle_id,
        "meta": {
            "lastUpdated": _now_nz(),
            "profile": ["http://hl7.org/fhir/StructureDefinition/Bundle"],
        },
        "identifier": {
            "system": "urn:ietf:rfc:3986",
            "value": f"urn:uuid:{bundle_id}",
        },
        "type": "transaction",
        "timestamp": _now_nz(),
        "entry": entries,
    }

    return bundle


def get_patient_id_from_bundle(bundle: Dict[str, Any]) -> Optional[str]:
    for entry in bundle.get("entry", []):
        r = entry.get("resource", {})
        if r.get("resourceType") == "Patient":
            return r.get("id")
    return None
