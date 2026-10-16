"""
Pydantic models for the NZ clinical data capture form.
These are the raw clinical records — NOT FHIR yet.
"""
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Shared type aliases
# ---------------------------------------------------------------------------

# NZ sex vocabulary (FHIR AdministrativeGender + NZ extension)
SexCode = Literal["male", "female", "other", "unknown"]

# Condition lifecycle
ConditionStatus = Literal["active", "resolved", "inactive"]

# Medication lifecycle
MedicationStatus = Literal["active", "stopped", "on-hold"]

# Allergy/intolerance severity
AllergySeverity = Literal["mild", "moderate", "severe"]

# Standard lab abnormal flags
AbnormalFlag = Literal["H", "L", "HH", "LL", "N"]

# FHIR encounter class
EncounterType = Literal["ambulatory", "inpatient", "emergency", "telehealth"]


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------


class NZAddress(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    street: str | None = None
    suburb: str | None = None
    city: str | None = None
    postcode: str | None = None
    region: str | None = None


class VitalSigns(BaseModel):
    systolic_bp: float | None = Field(None, description="mmHg")
    diastolic_bp: float | None = Field(None, description="mmHg")
    heart_rate: float | None = Field(None, description="beats/min")
    respiratory_rate: float | None = Field(None, description="breaths/min")
    temperature: float | None = Field(None, description="degrees Celsius")
    spo2: float | None = Field(None, description="percent")
    weight_kg: float | None = Field(None, description="kg")
    height_cm: float | None = Field(None, description="cm")
    bmi: float | None = Field(None, description="kg/m2, calculated if not provided")


class LabResult(BaseModel):
    loinc_code: str
    value: float
    unit: str
    reference_range_low: float | None = None
    reference_range_high: float | None = None
    abnormal_flag: AbnormalFlag | None = None
    collected_date: str | None = None  # ISO date string


class Condition(BaseModel):
    snomed_code: str
    display: str
    onset_date: str | None = None  # ISO date
    status: ConditionStatus = "active"
    notes: str | None = None


class Medication(BaseModel):
    snomed_code: str
    name: str
    dose: str | None = None
    frequency: str | None = None
    route: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    status: MedicationStatus = "active"


class Allergy(BaseModel):
    allergen_code: str  # SNOMED code
    allergen_display: str
    reaction: str | None = None
    severity: AllergySeverity | None = None
    status: str = "active"


class Immunization(BaseModel):
    vaccine_code: str  # SNOMED or CVX
    vaccine_display: str
    date_given: str | None = None
    lot_number: str | None = None
    site: str | None = None


class SocialHistory(BaseModel):
    smoking_status_code: str | None = None
    smoking_status_display: str | None = None
    pack_years: float | None = None
    alcohol_status_code: str | None = None
    alcohol_units_per_week: float | None = None
    occupation: str | None = None
    lives_alone: bool | None = None


class ClinicalNote(BaseModel):
    section: str  # e.g. "presenting complaint", "examination", "plan"
    text: str
    author: str | None = None


# ---------------------------------------------------------------------------
# Top-level patient record (the full form submission)
# ---------------------------------------------------------------------------


class PatientRecord(BaseModel):
    # Internal ID — generated on creation
    record_id: str = Field(default_factory=lambda: str(uuid.uuid4()))

    # NZ NHI — the national patient identifier
    nhi_number: str | None = Field(
        None,
        description="NZ National Health Index number e.g. ZZZ0008",
    )

    # Demographics
    family_name: str
    given_names: str
    date_of_birth: str  # ISO date YYYY-MM-DD
    sex: SexCode
    gender_identity: str | None = None
    sex_at_birth: SexCode | None = None
    ethnicity_codes: list[str] = Field(
        default_factory=list,
        description="NZ ethnicity level-4 codes (5-digit)",
    )

    # Contact
    address: NZAddress | None = None
    phone: str | None = None
    email: str | None = None

    # GP / PHO
    gp_name: str | None = None
    gp_practice: str | None = None
    pho: str | None = None

    # Encounter context
    encounter_date: str  # ISO date YYYY-MM-DD
    encounter_type: EncounterType = "ambulatory"
    presenting_complaint: str | None = None
    clinician_name: str | None = None
    clinician_role: str | None = None

    # Clinical data
    vitals: VitalSigns | None = None
    conditions: list[Condition] = Field(default_factory=list)
    medications: list[Medication] = Field(default_factory=list)
    allergies: list[Allergy] = Field(default_factory=list)
    lab_results: list[LabResult] = Field(default_factory=list)
    immunizations: list[Immunization] = Field(default_factory=list)
    social_history: SocialHistory | None = None
    clinical_notes: list[ClinicalNote] = Field(default_factory=list)

    # Timestamps
    created_at: str | None = None
    updated_at: str | None = None


class PatientRecordUpdate(BaseModel):
    """Partial update — all fields optional."""

    nhi_number: str | None = None
    family_name: str | None = None
    given_names: str | None = None
    date_of_birth: str | None = None
    sex: SexCode | None = None
    gender_identity: str | None = None
    sex_at_birth: SexCode | None = None
    ethnicity_codes: list[str] | None = None
    address: NZAddress | None = None
    phone: str | None = None
    email: str | None = None
    gp_name: str | None = None
    gp_practice: str | None = None
    pho: str | None = None
    encounter_date: str | None = None
    encounter_type: EncounterType | None = None
    presenting_complaint: str | None = None
    clinician_name: str | None = None
    clinician_role: str | None = None
    vitals: VitalSigns | None = None
    conditions: list[Condition] | None = None
    medications: list[Medication] | None = None
    allergies: list[Allergy] | None = None
    lab_results: list[LabResult] | None = None
    immunizations: list[Immunization] | None = None
    social_history: SocialHistory | None = None
    clinical_notes: list[ClinicalNote] | None = None
