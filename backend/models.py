"""
Pydantic models for the NZ clinical data capture form.
These are the raw clinical records — NOT FHIR yet.
"""
import re
import uuid
from typing import Annotated, Literal, get_args

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator, model_validator

# ---------------------------------------------------------------------------
# Missing data codes (CDISC standard)
# ---------------------------------------------------------------------------

MissingCode = Literal[
    'NI', 'INV', 'UNK', 'NASK', 'ASKU',
    'NAV', 'MSK', 'NA', 'NAVU', 'NP',
    'QS', 'TRC', 'UNC', 'DER', 'PINF', 'NINF', 'OTH',
]
MISSING_CODES: frozenset[str] = frozenset(get_args(MissingCode))


def _validate_numeric_or_missing(v: object) -> float | str | None:
    if v is None:
        return None
    if isinstance(v, bool):
        raise ValueError(f"Expected a number or missing code, got {v!r}")
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str) and v in MISSING_CODES:
        return v
    raise ValueError(f"Expected a number or missing code, got {v!r}")


NumericOrMissing = Annotated[float | str | None, BeforeValidator(_validate_numeric_or_missing)]

# NZ NHI — both legacy (3 alpha + 4 digits) and new (3 alpha + 2 digits + 2 alpha) formats.
# Letters exclude I and O (confusion with 1 and 0). Test NHIs start with Z.
_NHI_RE = re.compile(r"^[A-HJ-NP-Z]{3}([0-9]{4}|[0-9]{2}[A-HJ-NP-Z]{2})$")

# ISO date pattern — YYYY-MM-DD, basic calendar range check.
_ISO_DATE_RE = re.compile(r"^\d{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])$")


def _validate_iso_date(v: object) -> str | None:
    if v is None:
        return None
    if not isinstance(v, str) or not _ISO_DATE_RE.match(v):
        raise ValueError(f"Expected ISO date YYYY-MM-DD, got {v!r}")
    return v


def _validate_nhi(v: str) -> str:
    v = v.strip().upper()
    if not _NHI_RE.match(v):
        raise ValueError(
            "NHI must be 3 letters (A–Z excl. I/O) + 4 digits (legacy, e.g. ZAA0001) "
            "or 3 letters + 2 digits + 2 letters (new format, e.g. ZZZ00AB)"
        )
    return v


ISODate = Annotated[str, BeforeValidator(_validate_iso_date)]

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

# Allergy/intolerance clinical status (mirrors FHIR allergyintolerance-clinical)
AllergyClinicalStatus = Literal["active", "inactive", "resolved"]

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
    systolic_bp: NumericOrMissing = Field(None, description="mmHg")
    diastolic_bp: NumericOrMissing = Field(None, description="mmHg")
    heart_rate: NumericOrMissing = Field(None, description="beats/min")
    respiratory_rate: NumericOrMissing = Field(None, description="breaths/min")
    temperature: NumericOrMissing = Field(None, description="degrees Celsius")
    spo2: NumericOrMissing = Field(None, description="percent")
    weight_kg: NumericOrMissing = Field(None, description="kg")
    height_cm: NumericOrMissing = Field(None, description="cm")
    bmi: NumericOrMissing = Field(None, description="kg/m2, calculated if not provided")


class LabResult(BaseModel):
    loinc_code: str
    value: Annotated[float | str, BeforeValidator(_validate_numeric_or_missing)]
    unit: str
    reference_range_low: NumericOrMissing = None
    reference_range_high: NumericOrMissing = None
    abnormal_flag: AbnormalFlag | None = None
    collected_date: ISODate | None = None


class Condition(BaseModel):
    snomed_code: str
    display: str
    onset_date: ISODate | None = None
    status: ConditionStatus = "active"
    notes: str | None = None


class Medication(BaseModel):
    snomed_code: str
    name: str
    dose: str | None = None
    frequency: str | None = None
    route: str | None = None
    start_date: ISODate | None = None
    end_date: ISODate | None = None
    status: MedicationStatus = "active"


class Allergy(BaseModel):
    allergen_code: str  # SNOMED code
    allergen_display: str
    reaction: str | None = None
    severity: AllergySeverity | None = None
    status: AllergyClinicalStatus = "active"


class Immunization(BaseModel):
    vaccine_code: str  # SNOMED or CVX
    vaccine_display: str
    date_given: ISODate | None = None
    lot_number: str | None = None
    site: str | None = None


class SocialHistory(BaseModel):
    smoking_status_code: str | None = None
    smoking_status_display: str | None = None
    pack_years: NumericOrMissing = None
    alcohol_status_code: str | None = None
    alcohol_units_per_week: NumericOrMissing = None
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

    # Link to an existing patient — if supplied, demographics fields become optional
    patient_id: str | None = None

    # NZ NHI — required when creating a new patient; optional when patient_id is supplied
    nhi_number: str | None = None

    @field_validator("nhi_number")
    @classmethod
    def validate_nhi(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return _validate_nhi(v)

    @model_validator(mode="after")
    def check_demographics_or_patient_id(self) -> "PatientRecord":
        if self.patient_id is None:
            missing = [f for f in ("nhi_number", "family_name", "given_names", "date_of_birth", "sex")
                       if getattr(self, f, None) is None]
            if missing:
                raise ValueError(
                    f"Fields required when patient_id is not provided: {', '.join(missing)}"
                )
        return self

    # Demographics
    family_name: str | None = None
    given_names: str | None = None
    date_of_birth: ISODate | None = None
    sex: SexCode | None = None
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

    # Encounter context (optional — omit for pure instrument submissions)
    encounter_date: ISODate | None = None
    encounter_type: EncounterType | None = None
    redcap_event_name: str | None = None
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

    @field_validator("nhi_number")
    @classmethod
    def validate_nhi(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return _validate_nhi(v)
    family_name: str | None = None
    given_names: str | None = None
    date_of_birth: ISODate | None = None
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
    encounter_date: ISODate | None = None
    encounter_type: EncounterType | None = None
    redcap_event_name: str | None = None
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


# ---------------------------------------------------------------------------
# Patient-only models (demographics without encounter data)
# ---------------------------------------------------------------------------

class PatientCreate(BaseModel):
    """Create a patient record with demographics only — no encounter."""

    nhi_number: str = Field(..., description="NZ NHI number")
    family_name: str
    given_names: str
    date_of_birth: ISODate
    sex: SexCode
    gender_identity: str | None = None
    sex_at_birth: SexCode | None = None
    ethnicity_codes: list[str] = Field(default_factory=list)
    address: NZAddress | None = None
    phone: str | None = None
    email: str | None = None
    gp_name: str | None = None
    gp_practice: str | None = None
    pho: str | None = None

    @field_validator("nhi_number")
    @classmethod
    def validate_nhi(cls, v: str) -> str:
        return _validate_nhi(v)


class InstrumentSubmission(BaseModel):
    """Body for POST /api/patients/{id}/events/{event}/instruments/{instrument}."""
    fields: dict[str, str | None] = Field(default_factory=dict)
    completion_status: Literal["0", "1", "2"] | None = None
    instance: int = Field(default=0, ge=0)


class PatientUpdate(BaseModel):
    """Partial update of patient demographics — all fields optional."""

    nhi_number: str | None = None
    family_name: str | None = None
    given_names: str | None = None
    date_of_birth: ISODate | None = None
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

    @field_validator("nhi_number")
    @classmethod
    def validate_nhi(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return _validate_nhi(v)
