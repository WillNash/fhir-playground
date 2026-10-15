"""
Pydantic models for the NZ clinical data capture form.
These are the raw clinical records — NOT FHIR yet.
"""
from __future__ import annotations
from typing import Optional, List
from pydantic import BaseModel, Field
import uuid


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------

class NZAddress(BaseModel):
    street: Optional[str] = None
    suburb: Optional[str] = None
    city: Optional[str] = None
    postcode: Optional[str] = None
    region: Optional[str] = None


class VitalSigns(BaseModel):
    systolic_bp: Optional[float] = Field(None, description="mmHg")
    diastolic_bp: Optional[float] = Field(None, description="mmHg")
    heart_rate: Optional[float] = Field(None, description="beats/min")
    respiratory_rate: Optional[float] = Field(None, description="breaths/min")
    temperature: Optional[float] = Field(None, description="degrees Celsius")
    spo2: Optional[float] = Field(None, description="percent")
    weight_kg: Optional[float] = Field(None, description="kg")
    height_cm: Optional[float] = Field(None, description="cm")
    bmi: Optional[float] = Field(None, description="kg/m2, calculated if not provided")


class LabResult(BaseModel):
    loinc_code: str
    value: float
    unit: str
    reference_range_low: Optional[float] = None
    reference_range_high: Optional[float] = None
    abnormal_flag: Optional[str] = None   # "H", "L", "HH", "LL", "N"
    collected_date: Optional[str] = None  # ISO date string


class Condition(BaseModel):
    snomed_code: str
    display: str
    onset_date: Optional[str] = None     # ISO date
    status: str = "active"               # active | resolved | inactive
    notes: Optional[str] = None


class Medication(BaseModel):
    snomed_code: str
    name: str
    dose: Optional[str] = None
    frequency: Optional[str] = None
    route: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    status: str = "active"              # active | stopped | on-hold


class Allergy(BaseModel):
    allergen_code: str                  # SNOMED code
    allergen_display: str
    reaction: Optional[str] = None
    severity: Optional[str] = None     # mild | moderate | severe
    status: str = "active"


class Immunization(BaseModel):
    vaccine_code: str                   # SNOMED or CVX
    vaccine_display: str
    date_given: Optional[str] = None
    lot_number: Optional[str] = None
    site: Optional[str] = None


class SocialHistory(BaseModel):
    smoking_status_code: Optional[str] = None
    smoking_status_display: Optional[str] = None
    pack_years: Optional[float] = None
    alcohol_status_code: Optional[str] = None
    alcohol_units_per_week: Optional[float] = None
    occupation: Optional[str] = None
    lives_alone: Optional[bool] = None


class ClinicalNote(BaseModel):
    section: str         # e.g. "presenting complaint", "examination", "plan"
    text: str
    author: Optional[str] = None


# ---------------------------------------------------------------------------
# Top-level patient record (the full form submission)
# ---------------------------------------------------------------------------

class PatientRecord(BaseModel):
    # Internal ID — generated on creation
    record_id: str = Field(default_factory=lambda: str(uuid.uuid4()))

    # NZ NHI — the national patient identifier
    nhi_number: Optional[str] = Field(None, description="NZ National Health Index number e.g. ZZZ0008")

    # Demographics
    family_name: str
    given_names: str
    date_of_birth: str                  # ISO date YYYY-MM-DD
    sex: str                            # male | female | other | unknown
    gender_identity: Optional[str] = None
    sex_at_birth: Optional[str] = None  # male | female | other | unknown
    ethnicity_codes: List[str] = Field(default_factory=list)  # NZ ethnicity level-4 codes (5-digit)

    # Contact
    address: Optional[NZAddress] = None
    phone: Optional[str] = None
    email: Optional[str] = None

    # GP / PHO
    gp_name: Optional[str] = None
    gp_practice: Optional[str] = None
    pho: Optional[str] = None

    # Encounter context
    encounter_date: str                 # ISO date YYYY-MM-DD
    encounter_type: str = "ambulatory"  # ambulatory | inpatient | emergency | telehealth
    presenting_complaint: Optional[str] = None
    clinician_name: Optional[str] = None
    clinician_role: Optional[str] = None

    # Clinical data
    vitals: Optional[VitalSigns] = None
    conditions: List[Condition] = Field(default_factory=list)
    medications: List[Medication] = Field(default_factory=list)
    allergies: List[Allergy] = Field(default_factory=list)
    lab_results: List[LabResult] = Field(default_factory=list)
    immunizations: List[Immunization] = Field(default_factory=list)
    social_history: Optional[SocialHistory] = None
    clinical_notes: List[ClinicalNote] = Field(default_factory=list)

    # Timestamps
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class PatientRecordUpdate(BaseModel):
    """Partial update — all fields optional."""
    nhi_number: Optional[str] = None
    family_name: Optional[str] = None
    given_names: Optional[str] = None
    date_of_birth: Optional[str] = None
    sex: Optional[str] = None
    gender_identity: Optional[str] = None
    sex_at_birth: Optional[str] = None  # male | female | other | unknown
    ethnicity_codes: Optional[List[str]] = None
    address: Optional[NZAddress] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    gp_name: Optional[str] = None
    gp_practice: Optional[str] = None
    pho: Optional[str] = None
    encounter_date: Optional[str] = None
    encounter_type: Optional[str] = None
    presenting_complaint: Optional[str] = None
    clinician_name: Optional[str] = None
    clinician_role: Optional[str] = None
    vitals: Optional[VitalSigns] = None
    conditions: Optional[List[Condition]] = None
    medications: Optional[List[Medication]] = None
    allergies: Optional[List[Allergy]] = None
    lab_results: Optional[List[LabResult]] = None
    immunizations: Optional[List[Immunization]] = None
    social_history: Optional[SocialHistory] = None
    clinical_notes: Optional[List[ClinicalNote]] = None
