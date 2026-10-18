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
import uuid
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from .models import MISSING_CODES
from .snomed import (
    SNOMED_SYSTEM,
    NZ_ETHNICITY_SYSTEM,
    NHI_SYSTEM,
    LOINC_SYSTEM,
    OBSERVATIONS,
    NZ_ETHNICITY,
)


def _is_missing_code(v: object) -> bool:
    return isinstance(v, str) and v in MISSING_CODES

# ---------------------------------------------------------------------------
# NZ Base IG profile URLs (canonical — https://fhir.org.nz/ig/base/)
# ---------------------------------------------------------------------------
NZ_BASE_PATIENT_PROFILE = "https://fhir.org.nz/ig/base/StructureDefinition/NzPatient"
NZ_BASE_ENCOUNTER_PROFILE = "https://fhir.org.nz/ig/base/StructureDefinition/NzEncounter"

FHIR_VERSION = "4.0.1"

# ---------------------------------------------------------------------------
# Repeated FHIR terminology system URLs — named to avoid silent typos
# ---------------------------------------------------------------------------
_SYS_OBS_CATEGORY = "http://terminology.hl7.org/CodeSystem/observation-category"
_SYS_ACT_CODE = "http://terminology.hl7.org/CodeSystem/v3-ActCode"
_SYS_UCUM = "http://unitsofmeasure.org"
_SYS_OBS_INTERP = "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation"
_SYS_COND_CLINICAL = "http://terminology.hl7.org/CodeSystem/condition-clinical"
_SYS_COND_VER = "http://terminology.hl7.org/CodeSystem/condition-ver-status"
_SYS_ALLERGY_CLINICAL = "http://terminology.hl7.org/CodeSystem/allergyintolerance-clinical"
_SYS_ALLERGY_VER = "http://terminology.hl7.org/CodeSystem/allergyintolerance-verification"
_SYS_ORG_TYPE = "http://terminology.hl7.org/CodeSystem/organization-type"
_SYS_ADMIN_GENDER = "http://hl7.org/fhir/administrative-gender"

_NZ_TZ = ZoneInfo("Pacific/Auckland")

# Maps allergen SNOMED codes to their FHIR AllergyIntolerance.category value.
# Unknown codes fall back to "medication" at the call site.
_ALLERGEN_CATEGORY_MAP: dict[str, str] = {
    "372687004": "medication",  # Penicillin
    "373224006": "medication",  # Cephalosporins
    "387207008": "medication",  # Ibuprofen
    "372664007": "medication",  # Paracetamol
    "227493005": "food",        # Cashew nuts
    "226910009": "food",        # Peanuts
    "102263004": "food",        # Eggs
    "735029006": "food",        # Shellfish
    "227021000": "food",        # Wheat
    "227165004": "food",        # Cow milk
    "111088007": "environment", # Latex
    "412071004": "environment", # Pollen
    "84489001":  "environment", # Mould
    "260152009": "environment", # Cat dander
    "260157003": "environment", # Dust mite
}

# Valid FHIR abnormal-flag codes for lab interpretations.
_ABNORMAL_FLAG_MAP: dict[str, tuple[str, str]] = {
    "H":  ("H",  "High"),
    "L":  ("L",  "Low"),
    "HH": ("HH", "Critical High"),
    "LL": ("LL", "Critical Low"),
}

# Valid severity values for AllergyIntolerance.reaction.severity (FHIR R4).
_VALID_ALLERGY_SEVERITIES = frozenset({"mild", "moderate", "severe"})

# Valid clinical status codes per resource type.
_CONDITION_STATUSES: frozenset[str] = frozenset({"active", "resolved", "inactive"})
_MEDICATION_STATUSES: frozenset[str] = frozenset({"active", "stopped", "on-hold"})


def _coerce_status(raw: str | None, valid: frozenset[str], default: str = "active") -> str:
    """Return ``raw`` if it is a recognised status code, otherwise ``default``."""
    return raw if raw in valid else default


# Encounter-class mapping from record field to v3-ActCode.
_ENCOUNTER_CLASS_MAP: dict[str, dict[str, str]] = {
    "ambulatory": {"system": _SYS_ACT_CODE, "code": "AMB",  "display": "ambulatory"},
    "inpatient":  {"system": _SYS_ACT_CODE, "code": "IMP",  "display": "inpatient"},
    "emergency":  {"system": _SYS_ACT_CODE, "code": "EMER", "display": "emergency"},
    "telehealth": {"system": _SYS_ACT_CODE, "code": "VR",   "display": "virtual"},
}

# LOINC code -> (systolic field, diastolic field) for the BP panel.
_VITAL_FIELD_TO_LOINC: dict[str, str] = {
    "systolic_bp":     "8480-6",
    "diastolic_bp":    "8462-4",
    "heart_rate":      "8867-4",
    "respiratory_rate": "9279-1",
    "temperature":     "8310-5",
    "weight_kg":       "29463-7",
    "height_cm":       "8302-2",
    "bmi":             "39156-5",
}


# ---------------------------------------------------------------------------
# Small private helpers
# ---------------------------------------------------------------------------

def _now_nz() -> str:
    """Return the current NZ time as ISO 8601 with NZ UTC offset (+13:00 NZDT / +12:00 NZST)."""
    return datetime.now(_NZ_TZ).isoformat(timespec="seconds")


def _today_nz() -> str:
    """Return the current NZ date as an ISO 8601 date string (YYYY-MM-DD)."""
    return datetime.now(_NZ_TZ).date().isoformat()


_NAMESPACE = uuid.UUID("12e4b2c0-9dad-4a71-8000-7edcab000001")  # fixed app namespace for det IDs

def _det_uuid(*parts: str) -> str:
    """Deterministic UUID5 so the same logical resource always gets the same ID."""
    return str(uuid.uuid5(_NAMESPACE, "/".join(parts)))


def _ref(resource_type: str, resource_id: str) -> dict[str, str]:
    return {"reference": f"{resource_type}/{resource_id}"}


def _obs_category(code: str, display: str) -> list[dict[str, Any]]:
    """Return a FHIR Observation.category element for the given category code."""
    return [{"coding": [{"system": _SYS_OBS_CATEGORY, "code": code, "display": display}]}]


def _resource_ref(resource: dict[str, Any]) -> dict[str, str]:
    """Return a minimal {resourceType, id} dict for Composition section entries."""
    return {"resourceType": resource["resourceType"], "id": resource["id"]}


# ---------------------------------------------------------------------------
# Patient sub-builders (private — only called by build_patient)
# ---------------------------------------------------------------------------

def _nhi_identifiers(record: dict[str, Any]) -> list[dict[str, Any]]:
    if not record.get("nhi_number"):
        return []
    return [{"use": "official", "system": NHI_SYSTEM, "value": record["nhi_number"].upper()}]


def _ethnicity_extensions(record: dict[str, Any]) -> list[dict[str, Any]]:
    exts: list[dict[str, Any]] = []
    for code in record.get("ethnicity_codes", []):
        display = NZ_ETHNICITY.get(code, code)
        exts.append({
            "url": "http://hl7.org.nz/fhir/StructureDefinition/nz-ethnicity",
            "valueCodeableConcept": {
                "coding": [{"system": NZ_ETHNICITY_SYSTEM, "code": code, "display": display}],
                "text": display,
            },
        })
    return exts


def _patient_address(record: dict[str, Any]) -> list[dict[str, Any]]:
    addr_raw = record.get("address") or {}
    if not (isinstance(addr_raw, dict) and any(addr_raw.values())):
        return []
    a: dict[str, Any] = {"use": "home", "type": "physical"}
    if addr_raw.get("street"):
        a["line"] = [addr_raw["street"]]
    if addr_raw.get("suburb"):
        a["district"] = addr_raw["suburb"]
    if addr_raw.get("city"):
        a["city"] = addr_raw["city"]
    if addr_raw.get("postcode"):
        a["postalCode"] = addr_raw["postcode"]
    a["country"] = "NZ"
    return [a]


def _patient_telecom(record: dict[str, Any]) -> list[dict[str, Any]]:
    telecom: list[dict[str, Any]] = []
    if record.get("phone"):
        telecom.append({"system": "phone", "value": record["phone"], "use": "mobile"})
    if record.get("email"):
        telecom.append({"system": "email", "value": record["email"]})
    return telecom


def _patient_extra_extensions(record: dict[str, Any]) -> list[dict[str, Any]]:
    """Gender identity and sex-at-birth NZ Base IG extensions."""
    exts: list[dict[str, Any]] = []
    if record.get("gender_identity"):
        exts.append({
            "url": "http://hl7.org.nz/fhir/StructureDefinition/gender-original-text",
            "valueString": record["gender_identity"],
        })
    if sab := record.get("sex_at_birth"):
        exts.append({
            "url": "http://hl7.org.nz/fhir/StructureDefinition/sex-at-birth",
            "valueCodeableConcept": {
                "coding": [{"system": _SYS_ADMIN_GENDER, "code": sab, "display": sab.capitalize()}]
            },
        })
    return exts


# ---------------------------------------------------------------------------
# Individual resource builders
# ---------------------------------------------------------------------------

def build_patient(record: dict[str, Any]) -> dict[str, Any]:  # Any: external JSON
    patient_id = _det_uuid("Patient", record["patient_id"])
    extensions = _ethnicity_extensions(record) + _patient_extra_extensions(record)

    patient: dict[str, Any] = {
        "resourceType": "Patient",
        "id": patient_id,
        "meta": {
            "profile": [NZ_BASE_PATIENT_PROFILE],
            "lastUpdated": _now_nz(),
        },
        "identifier": _nhi_identifiers(record),
        "name": [{
            "use": "official",
            "family": record.get("family_name", ""),
            "given": [n.strip() for n in record.get("given_names", "").split() if n.strip()],
        }],
        "birthDate": record.get("date_of_birth", ""),
        "gender": record.get("sex", "unknown"),
    }

    if extensions:
        patient["extension"] = extensions
    address = _patient_address(record)
    if address:
        patient["address"] = address
    telecom = _patient_telecom(record)
    if telecom:
        patient["telecom"] = telecom

    return patient


def build_organization_ref(record: dict[str, Any]) -> dict[str, Any] | None:  # Any: external JSON
    """Return a contained Organization resource if a GP practice is recorded."""
    if not record.get("gp_practice"):
        return None
    return {
        "resourceType": "Organization",
        "id": _det_uuid("Organization", record.get("gp_practice", "")),
        "name": record["gp_practice"],
        "type": [{
            "coding": [{
                "system": _SYS_ORG_TYPE,
                "code": "prov",
                "display": "Healthcare Provider",
            }]
        }],
    }


def build_encounter(record: dict[str, Any], patient_id: str) -> dict[str, Any]:  # Any: external JSON
    encounter_id = _det_uuid("Encounter", record["record_id"])

    enc_class = _ENCOUNTER_CLASS_MAP.get(
        record.get("encounter_type", "ambulatory"),
        _ENCOUNTER_CLASS_MAP["ambulatory"],
    )
    enc_date = record.get("encounter_date", _today_nz())

    encounter: dict[str, Any] = {
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
        encounter["reasonCode"] = [{"text": record["presenting_complaint"]}]

    if record.get("clinician_name"):
        encounter["participant"] = [{
            "type": [{"text": record.get("clinician_role", "GP")}],
            "individual": {"display": record["clinician_name"]},
        }]

    return encounter


def build_vitals(
    vitals_raw: dict[str, Any],  # Any: external JSON
    patient_id: str,
    encounter_id: str | None,
    encounter_date: str,
    record_id: str = "",
) -> list[dict[str, Any]]:
    """Build FHIR Observation resources for each vital sign recorded."""
    observations: list[dict[str, Any]] = []
    category = _obs_category("vital-signs", "Vital Signs")

    # Blood pressure panel — built from both components together (FHIR R4 BP profile).
    sbp = vitals_raw.get("systolic_bp")
    dbp = vitals_raw.get("diastolic_bp")
    if sbp is not None and dbp is not None and not _is_missing_code(sbp) and not _is_missing_code(dbp):
        bp_obs: dict[str, Any] = {
            "resourceType": "Observation",
            "id": _det_uuid("Observation", record_id, "bp"),
            "meta": {"profile": ["http://hl7.org/fhir/StructureDefinition/bp"]},
            "status": "final",
            "category": category,
            "code": {
                "coding": [{"system": LOINC_SYSTEM, "code": "85354-9",
                             "display": "Blood pressure panel with all children optional"}],
                "text": "Blood pressure",
            },
            "subject": _ref("Patient", patient_id),
            "effectiveDateTime": encounter_date,
            "component": [
                {
                    "code": {"coding": [{"system": LOINC_SYSTEM, "code": "8480-6",
                                         "display": "Systolic blood pressure"}]},
                    "valueQuantity": {"value": sbp, "unit": "mmHg",
                                      "system": _SYS_UCUM, "code": "mm[Hg]"},
                },
                {
                    "code": {"coding": [{"system": LOINC_SYSTEM, "code": "8462-4",
                                         "display": "Diastolic blood pressure"}]},
                    "valueQuantity": {"value": dbp, "unit": "mmHg",
                                      "system": _SYS_UCUM, "code": "mm[Hg]"},
                },
            ],
        }
        if encounter_id is not None:
            bp_obs["encounter"] = _ref("Encounter", encounter_id)
        observations.append(bp_obs)

    # SpO2 — dual-coded per FHIR R4 Vital Signs profile (primary 2708-6, supplementary 59408-5).
    spo2_val = vitals_raw.get("spo2")
    if spo2_val is not None and not _is_missing_code(spo2_val):
        spo2_obs: dict[str, Any] = {
            "resourceType": "Observation",
            "id": _det_uuid("Observation", record_id, "spo2"),
            "status": "final",
            "category": category,
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
            "effectiveDateTime": encounter_date,
            "valueQuantity": {
                "value": spo2_val,
                "unit": "%",
                "system": _SYS_UCUM,
                "code": "%",
            },
        }
        if encounter_id is not None:
            spo2_obs["encounter"] = _ref("Encounter", encounter_id)
        observations.append(spo2_obs)

    # Remaining individual vitals (BP components skipped — already handled above).
    skip_for_bp = {"systolic_bp", "diastolic_bp"}
    for field, loinc in _VITAL_FIELD_TO_LOINC.items():
        if field in skip_for_bp:
            continue
        value = vitals_raw.get(field)
        if value is None or _is_missing_code(value):
            continue
        obs_meta = OBSERVATIONS.get(loinc, {})
        vital_obs: dict[str, Any] = {
            "resourceType": "Observation",
            "id": _det_uuid("Observation", record_id, loinc),
            "status": "final",
            "category": category,
            "code": {
                "coding": [{"system": LOINC_SYSTEM, "code": loinc,
                             "display": obs_meta.get("display", field)}],
                "text": obs_meta.get("display", field),
            },
            "subject": _ref("Patient", patient_id),
            "effectiveDateTime": encounter_date,
            "valueQuantity": {
                "value": value,
                "unit": obs_meta.get("unit", ""),
                "system": _SYS_UCUM,
                "code": obs_meta.get("ucum", ""),
            },
        }
        if encounter_id is not None:
            vital_obs["encounter"] = _ref("Encounter", encounter_id)
        observations.append(vital_obs)

    return observations


def build_lab_observation(
    lab: dict[str, Any],  # Any: external JSON
    patient_id: str,
    encounter_id: str | None,
    record_id: str = "",
    idx: int = 0,
) -> dict[str, Any]:
    loinc_code: str = lab.get("loinc_code", "")
    obs_meta = OBSERVATIONS.get(loinc_code, {})
    unit = lab.get("unit", obs_meta.get("unit", ""))
    ucum = obs_meta.get("ucum", unit)

    lab_value = lab.get("value")
    value_is_missing = _is_missing_code(lab_value)

    obs: dict[str, Any] = {
        "resourceType": "Observation",
        "id": _det_uuid("Observation", record_id, "lab", loinc_code, str(idx)),
        "status": "final",
        "category": _obs_category("laboratory", "Laboratory"),
        "code": {
            "coding": [{"system": LOINC_SYSTEM, "code": loinc_code,
                         "display": obs_meta.get("display", loinc_code)}],
            "text": obs_meta.get("display", loinc_code),
        },
        "subject": _ref("Patient", patient_id),
        "effectiveDateTime": lab.get("collected_date", _today_nz()),
    }
    if encounter_id is not None:
        obs["encounter"] = _ref("Encounter", encounter_id)

    if value_is_missing:
        obs["dataAbsentReason"] = {
            "coding": [{
                "system": "http://terminology.hl7.org/CodeSystem/data-absent-reason",
                "code": "unknown",
                "display": "Unknown",
            }]
        }
    else:
        obs["valueQuantity"] = {
            "value": lab_value,
            "unit": unit,
            "system": _SYS_UCUM,
            "code": ucum,
        }

    low = lab.get("reference_range_low")
    high = lab.get("reference_range_high")
    if not value_is_missing and (low is not None or high is not None):
        rr: dict[str, Any] = {}
        if low is not None and not _is_missing_code(low):
            rr["low"] = {"value": low, "unit": unit, "system": _SYS_UCUM, "code": ucum}
        if high is not None and not _is_missing_code(high):
            rr["high"] = {"value": high, "unit": unit, "system": _SYS_UCUM, "code": ucum}
        if rr:
            obs["referenceRange"] = [rr]

    flag = lab.get("abnormal_flag")
    if flag and flag != "N":
        interp_code, interp_display = _ABNORMAL_FLAG_MAP.get(flag, ("A", "Abnormal"))
        obs["interpretation"] = [{"coding": [{
            "system": _SYS_OBS_INTERP,
            "code": interp_code,
            "display": interp_display,
        }]}]

    return obs


def build_condition(
    cond: dict[str, Any],  # Any: external JSON
    patient_id: str,
    encounter_id: str | None,
    record_id: str = "",
    idx: int = 0,
) -> dict[str, Any]:
    clin_status = _coerce_status(cond.get("status"), _CONDITION_STATUSES)

    fhir_cond: dict[str, Any] = {
        "resourceType": "Condition",
        "id": _det_uuid("Condition", record_id, str(idx)),
        "clinicalStatus": {"coding": [{
            "system": _SYS_COND_CLINICAL,
            "code": clin_status,
            "display": clin_status.capitalize(),
        }]},
        "verificationStatus": {"coding": [{
            "system": _SYS_COND_VER,
            "code": "confirmed",
            "display": "Confirmed",
        }]},
        "code": {
            "coding": [{
                "system": SNOMED_SYSTEM,
                "code": cond.get("snomed_code", ""),
                "display": cond.get("display", ""),
            }],
            "text": cond.get("display", ""),
        },
        "subject": _ref("Patient", patient_id),
    }
    if encounter_id is not None:
        fhir_cond["encounter"] = _ref("Encounter", encounter_id)

    if cond.get("onset_date"):
        fhir_cond["onsetDateTime"] = cond["onset_date"]
    if cond.get("notes"):
        fhir_cond["note"] = [{"text": cond["notes"]}]

    return fhir_cond


def build_medication_statement(
    med: dict[str, Any],  # Any: external JSON
    patient_id: str,
    encounter_id: str | None,
    record_id: str = "",
    idx: int = 0,
) -> dict[str, Any]:
    fhir_status = _coerce_status(med.get("status"), _MEDICATION_STATUSES)

    dosage: list[dict[str, Any]] = []
    if med.get("dose") or med.get("frequency") or med.get("route"):
        d: dict[str, Any] = {}
        if med.get("dose"):
            d["text"] = med["dose"]
        if med.get("frequency"):
            d["timing"] = {"repeat": {"boundsPeriod": {}}, "code": {"text": med["frequency"]}}
        if med.get("route"):
            d["route"] = {"text": med["route"]}
        dosage.append(d)

    stmt: dict[str, Any] = {
        "resourceType": "MedicationStatement",
        "id": _det_uuid("MedicationStatement", record_id, str(idx)),
        "status": fhir_status,
        "medicationCodeableConcept": {
            "coding": [{
                "system": SNOMED_SYSTEM,
                "code": med.get("snomed_code", ""),
                "display": med.get("name", ""),
            }],
            "text": med.get("name", ""),
        },
        "subject": _ref("Patient", patient_id),
    }
    if encounter_id is not None:
        stmt["context"] = _ref("Encounter", encounter_id)

    if med.get("start_date"):
        stmt["effectivePeriod"] = {"start": med["start_date"]}
        if med.get("end_date"):
            stmt["effectivePeriod"]["end"] = med["end_date"]
    if dosage:
        stmt["dosage"] = dosage

    return stmt


def build_allergy(allergy: dict[str, Any], patient_id: str, record_id: str = "", idx: int = 0) -> dict[str, Any]:  # Any: external JSON
    allergen_code: str = allergy.get("allergen_code", "")
    severity = allergy.get("severity")
    fhir_severity: str | None = severity if severity in _VALID_ALLERGY_SEVERITIES else None
    category = _ALLERGEN_CATEGORY_MAP.get(allergen_code, "medication")
    status_code: str = allergy.get("status", "active")

    ai: dict[str, Any] = {
        "resourceType": "AllergyIntolerance",
        "id": _det_uuid("AllergyIntolerance", record_id, str(idx)),
        "clinicalStatus": {"coding": [{
            "system": _SYS_ALLERGY_CLINICAL,
            "code": status_code,
            "display": status_code.capitalize(),
        }]},
        "verificationStatus": {"coding": [{
            "system": _SYS_ALLERGY_VER,
            "code": "confirmed",
            "display": "Confirmed",
        }]},
        "type": "allergy",
        "category": [category],
        "code": {
            "coding": [{
                "system": SNOMED_SYSTEM,
                "code": allergen_code,
                "display": allergy.get("allergen_display", ""),
            }],
            "text": allergy.get("allergen_display", ""),
        },
        "patient": _ref("Patient", patient_id),
    }

    if allergy.get("reaction") or fhir_severity:
        rxn: dict[str, Any] = {}
        if allergy.get("reaction"):
            rxn["manifestation"] = [{"text": allergy["reaction"]}]
        if fhir_severity:
            rxn["severity"] = fhir_severity
        ai["reaction"] = [rxn]

    return ai


def build_immunization(
    imm: dict[str, Any],  # Any: external JSON
    patient_id: str,
    encounter_id: str | None,
    record_id: str = "",
    idx: int = 0,
) -> dict[str, Any]:
    resource: dict[str, Any] = {
        "resourceType": "Immunization",
        "id": _det_uuid("Immunization", record_id, str(idx)),
        "status": "completed",
        "vaccineCode": {
            "coding": [{
                "system": SNOMED_SYSTEM,
                "code": imm.get("vaccine_code", ""),
                "display": imm.get("vaccine_display", ""),
            }],
            "text": imm.get("vaccine_display", ""),
        },
        "patient": _ref("Patient", patient_id),
        "occurrenceDateTime": imm.get("date_given", _today_nz()),
    }
    if encounter_id is not None:
        resource["encounter"] = _ref("Encounter", encounter_id)
    if imm.get("lot_number"):
        resource["lotNumber"] = imm["lot_number"]
    if imm.get("site"):
        resource["site"] = {"text": imm["site"]}
    return resource


def build_social_history_observations(
    social: dict[str, Any],  # Any: external JSON
    patient_id: str,
    encounter_id: str | None,
    encounter_date: str,
    record_id: str = "",
) -> list[dict[str, Any]]:
    obs_list: list[dict[str, Any]] = []
    category = _obs_category("social-history", "Social History")

    if social.get("smoking_status_code"):
        smoking_obs: dict[str, Any] = {
            "resourceType": "Observation",
            "id": _det_uuid("Observation", record_id, "smoking"),
            "status": "final",
            "category": category,
            "code": {"coding": [{"system": LOINC_SYSTEM, "code": "72166-2",
                                  "display": "Tobacco smoking status"}]},
            "subject": _ref("Patient", patient_id),
            "effectiveDateTime": encounter_date,
            "valueCodeableConcept": {"coding": [{
                "system": SNOMED_SYSTEM,
                "code": social["smoking_status_code"],
                "display": social.get("smoking_status_display", ""),
            }]},
        }
        if encounter_id is not None:
            smoking_obs["encounter"] = _ref("Encounter", encounter_id)
        obs_list.append(smoking_obs)

    if social.get("alcohol_units_per_week") is not None and not _is_missing_code(social.get("alcohol_units_per_week")):
        alcohol_obs: dict[str, Any] = {
            "resourceType": "Observation",
            "id": _det_uuid("Observation", record_id, "alcohol"),
            "status": "final",
            "category": category,
            "code": {"coding": [{"system": LOINC_SYSTEM, "code": "74013-4",
                                  "display": "Alcoholic drinks per week"}]},
            "subject": _ref("Patient", patient_id),
            "effectiveDateTime": encounter_date,
            "valueQuantity": {
                "value": social["alcohol_units_per_week"],
                "unit": "units/week",
                "system": _SYS_UCUM,
                "code": "{drinks}/wk",
            },
        }
        if encounter_id is not None:
            alcohol_obs["encounter"] = _ref("Encounter", encounter_id)
        obs_list.append(alcohol_obs)

    return obs_list


def build_composition(
    record: dict[str, Any],  # Any: external JSON
    patient_id: str,
    encounter_id: str | None,
    section_entries: dict[str, list[dict[str, str]]],
    record_id: str = "",
) -> dict[str, Any]:
    notes: list[dict[str, Any]] = record.get("clinical_notes", [])

    sections: list[dict[str, Any]] = []
    for section_name, entries in section_entries.items():
        sections.append({
            "title": section_name,
            "code": {"text": section_name},
            "entry": [{"reference": f"{e['resourceType']}/{e['id']}"} for e in entries],
        })

    for note in notes:
        sections.append({
            "title": note.get("section", "Note").title(),
            "code": {"text": note.get("section", "note")},
            "text": {
                "status": "generated",
                "div": f"<div xmlns=\"http://www.w3.org/1999/xhtml\">{note.get('text', '')}</div>",
            },
        })

    composition: dict[str, Any] = {
        "resourceType": "Composition",
        "id": _det_uuid("Composition", record_id),
        "status": "final",
        "type": {
            "coding": [{"system": LOINC_SYSTEM, "code": "11506-3", "display": "Progress note"}],
            "text": "Clinical encounter note",
        },
        "subject": _ref("Patient", patient_id),
        "date": _now_nz(),
        "author": [{"display": record.get("clinician_name", "Unknown")}],
        "title": f"Encounter note - {record.get('encounter_date', '')}",
        "section": sections,
    }
    if encounter_id is not None:
        composition["encounter"] = _ref("Encounter", encounter_id)
    return composition


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def clinical_record_to_fhir_bundle(record: dict[str, Any]) -> dict[str, Any]:  # Any: external JSON
    """
    Convert a raw clinical PatientRecord dict into a FHIR R4 Transaction Bundle.
    Returns the Bundle dict ready for persistence.
    """
    record_id: str = record["record_id"]
    bundle_id = _det_uuid("Bundle", record_id)
    entries: list[dict[str, Any]] = []

    def _entry(resource: dict[str, Any]) -> dict[str, Any]:
        rid = resource["id"]
        rtype = resource["resourceType"]
        return {
            "fullUrl": f"urn:uuid:{rid}",
            "resource": resource,
            "request": {"method": "PUT", "url": f"{rtype}/{rid}"},
        }

    # Patient
    patient = build_patient(record)
    patient_id: str = patient["id"]
    entries.append(_entry(patient))

    # Encounter — only built when encounter_date is present
    has_encounter = bool(record.get("encounter_date"))
    encounter_id: str | None
    encounter_date: str
    if has_encounter:
        encounter = build_encounter(record, patient_id)
        encounter_id = encounter["id"]
        encounter_date = record.get("encounter_date", _today_nz())
        entries.append(_entry(encounter))
    else:
        encounter_id = None
        encounter_date = _today_nz()

    # Track resources per section for the Composition index.
    section_entries: dict[str, list[dict[str, str]]] = {
        "Vital Signs": [],
        "Laboratory Results": [],
        "Conditions": [],
        "Medications": [],
        "Allergies": [],
        "Immunizations": [],
        "Social History": [],
    }

    def _add(resource: dict[str, Any], section: str) -> None:
        entries.append(_entry(resource))
        section_entries[section].append(_resource_ref(resource))

    # Vitals
    vitals_raw = record.get("vitals") or {}
    if isinstance(vitals_raw, dict):
        for obs in build_vitals(vitals_raw, patient_id, encounter_id, encounter_date, record_id):
            _add(obs, "Vital Signs")

    # Lab results
    for i, lab in enumerate(record.get("lab_results", [])):
        if isinstance(lab, dict):
            _add(build_lab_observation(lab, patient_id, encounter_id, record_id, i), "Laboratory Results")

    # Conditions
    for i, cond in enumerate(record.get("conditions", [])):
        if isinstance(cond, dict):
            _add(build_condition(cond, patient_id, encounter_id, record_id, i), "Conditions")

    # Medications
    for i, med in enumerate(record.get("medications", [])):
        if isinstance(med, dict):
            _add(build_medication_statement(med, patient_id, encounter_id, record_id, i), "Medications")

    # Allergies
    for i, allergy in enumerate(record.get("allergies", [])):
        if isinstance(allergy, dict):
            _add(build_allergy(allergy, patient_id, record_id, i), "Allergies")

    # Immunizations
    for i, imm in enumerate(record.get("immunizations", [])):
        if isinstance(imm, dict):
            _add(build_immunization(imm, patient_id, encounter_id, record_id, i), "Immunizations")

    # Social history
    social = record.get("social_history") or {}
    if isinstance(social, dict) and any(social.values()):
        for obs in build_social_history_observations(social, patient_id, encounter_id, encounter_date, record_id):
            _add(obs, "Social History")

    # Composition (clinical document index)
    entries.append(_entry(build_composition(record, patient_id, encounter_id, section_entries, record_id)))

    return {
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


def get_patient_id_from_bundle(bundle: dict[str, Any]) -> str | None:  # Any: external JSON
    for entry in bundle.get("entry", []):
        resource = entry.get("resource", {})
        if resource.get("resourceType") == "Patient":
            return resource.get("id")
    return None
