"""
REDCap-compatible data dictionary for the NZ FHIR Clinical Demo Platform.

Exports:
  EVENTS            — 3 longitudinal study events
  MISSING_DATA_CODES — 17 CDISC standard missing data codes
  DATA_DICTIONARY   — 60+ field descriptors (18 REDCap columns each)
"""

# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

EVENTS = [
    {"event_id": 1, "arm_num": 1, "unique_event_name": "baseline_arm_1",   "event_label": "Baseline",    "event_order": 1},
    {"event_id": 2, "arm_num": 1, "unique_event_name": "followup_1_arm_1", "event_label": "Follow-up 1", "event_order": 2},
    {"event_id": 3, "arm_num": 1, "unique_event_name": "followup_2_arm_1", "event_label": "Follow-up 2", "event_order": 3},
]

# ---------------------------------------------------------------------------
# Missing data codes (CDISC standard)
# ---------------------------------------------------------------------------

MISSING_DATA_CODES = [
    {"code": "NI",   "label": "No information"},
    {"code": "INV",  "label": "Invalid"},
    {"code": "UNK",  "label": "Unknown"},
    {"code": "NASK", "label": "Not asked"},
    {"code": "ASKU", "label": "Asked but unknown"},
    {"code": "NAV",  "label": "Temporarily unavailable"},
    {"code": "MSK",  "label": "Masked"},
    {"code": "NA",   "label": "Not applicable"},
    {"code": "NAVU", "label": "Not available"},
    {"code": "NP",   "label": "Not present"},
    {"code": "QS",   "label": "Sufficient quantity"},
    {"code": "TRC",  "label": "Trace"},
    {"code": "UNC",  "label": "Unencoded"},
    {"code": "DER",  "label": "Derived"},
    {"code": "PINF", "label": "Positive infinity"},
    {"code": "NINF", "label": "Negative infinity"},
    {"code": "OTH",  "label": "Other"},
]

# ---------------------------------------------------------------------------
# Helper: blank entry template (all 18 REDCap columns)
# ---------------------------------------------------------------------------

def _field(
    variable_field_name: str,
    form_name: str,
    field_type: str,
    field_label: str,
    *,
    section_header: str = "",
    choices: str = "",
    field_note: str = "",
    text_validation_type: str = "",
    text_validation_min: str = "",
    text_validation_max: str = "",
    identifier: str = "",
    branching_logic: str = "",
    required_field: str = "",
    custom_alignment: str = "",
    question_number: str = "",
    matrix_group: str = "",
    matrix_ranking: str = "",
    field_annotation: str = "",
) -> dict:
    return {
        "variable_field_name": variable_field_name,
        "form_name": form_name,
        "section_header": section_header,
        "field_type": field_type,
        "field_label": field_label,
        "choices_calculations_slider_labels": choices,
        "field_note": field_note,
        "text_validation_type_or_show_slider_number": text_validation_type,
        "text_validation_min": text_validation_min,
        "text_validation_max": text_validation_max,
        "identifier": identifier,
        "branching_logic": branching_logic,
        "required_field": required_field,
        "custom_alignment": custom_alignment,
        "question_number_surveys_only": question_number,
        "matrix_group_name": matrix_group,
        "matrix_ranking": matrix_ranking,
        "field_annotation": field_annotation,
    }


# ---------------------------------------------------------------------------
# Data dictionary
# ---------------------------------------------------------------------------

DATA_DICTIONARY = [
    # ── Demographics ────────────────────────────────────────────────────────
    _field("record_id",        "demographics", "text",    "Record ID",
           section_header="Record Identification",
           field_annotation="@NOMISSING"),
    _field("nhi_number",       "demographics", "text",    "NZ NHI Number",
           field_note="National Health Index number (e.g. ZZZ0008)",
           identifier="y"),
    _field("family_name",      "demographics", "text",    "Family Name",
           required_field="y", field_annotation="@NOMISSING"),
    _field("given_names",      "demographics", "text",    "Given Name(s)",
           required_field="y", field_annotation="@NOMISSING"),
    _field("date_of_birth",    "demographics", "text",    "Date of Birth",
           required_field="y",
           text_validation_type="date_ymd"),
    _field("sex",              "demographics", "radio",   "Sex",
           required_field="y",
           choices="male, Male | female, Female | other, Other / Indeterminate | unknown, Unknown"),
    _field("gender_identity",  "demographics", "text",    "Gender Identity",
           branching_logic="[sex] = 'other'"),
    _field("sex_at_birth",     "demographics", "dropdown","Sex at Birth",
           choices="male, Male | female, Female | other, Other | unknown, Unknown",
           branching_logic="[sex] = 'other'"),
    _field("ethnicity_codes",  "demographics", "text",    "Ethnicity Codes (NZ Stats Level 4, pipe-separated)",
           field_note="e.g. 21111|11111"),

    # Contact
    _field("phone",            "demographics", "text",    "Phone",
           section_header="Contact Details",
           text_validation_type="phone"),
    _field("email",            "demographics", "text",    "Email",
           text_validation_type="email"),

    # ── Address ─────────────────────────────────────────────────────────────
    _field("address.street",   "address",      "text",    "Street Address"),
    _field("address.suburb",   "address",      "text",    "Suburb"),
    _field("address.city",     "address",      "text",    "City"),
    _field("address.postcode", "address",      "text",    "Postcode"),
    _field("address.region",   "address",      "text",    "Region"),

    # ── GP / PHO ────────────────────────────────────────────────────────────
    _field("gp_name",          "gp",           "text",    "GP Name"),
    _field("gp_practice",      "gp",           "text",    "GP Practice Name"),
    _field("pho",              "gp",           "text",    "PHO"),

    # ── Encounter ───────────────────────────────────────────────────────────
    _field("encounter_date",   "encounter",    "text",    "Encounter Date",
           required_field="y",
           text_validation_type="date_ymd"),
    _field("encounter_type",   "encounter",    "dropdown","Encounter Type",
           choices="ambulatory, Ambulatory / Outpatient | inpatient, Inpatient | emergency, Emergency | telehealth, Telehealth"),
    _field("redcap_event_name","encounter",    "text",    "REDCap Event Name",
           field_note="unique_event_name from the events table"),
    _field("presenting_complaint","encounter", "notes",   "Presenting Complaint"),
    _field("clinician_name",   "encounter",    "text",    "Clinician Name"),
    _field("clinician_role",   "encounter",    "text",    "Clinician Role"),

    # ── Vital Signs ─────────────────────────────────────────────────────────
    _field("vitals.systolic_bp",    "vitals",  "text",    "Systolic BP (mmHg)",
           section_header="Vital Signs",
           text_validation_type="number",
           text_validation_min="0", text_validation_max="300"),
    _field("vitals.diastolic_bp",   "vitals",  "text",    "Diastolic BP (mmHg)",
           text_validation_type="number",
           text_validation_min="0", text_validation_max="200"),
    _field("vitals.heart_rate",     "vitals",  "text",    "Heart Rate (bpm)",
           text_validation_type="number",
           text_validation_min="0", text_validation_max="300"),
    _field("vitals.respiratory_rate","vitals", "text",    "Respiratory Rate (/min)",
           text_validation_type="number",
           text_validation_min="0", text_validation_max="60"),
    _field("vitals.temperature",    "vitals",  "text",    "Temperature (°C)",
           text_validation_type="number",
           text_validation_min="30", text_validation_max="45"),
    _field("vitals.spo2",           "vitals",  "text",    "SpO2 (%)",
           text_validation_type="number",
           text_validation_min="0", text_validation_max="100"),
    _field("vitals.weight_kg",      "vitals",  "text",    "Weight (kg)",
           text_validation_type="number",
           text_validation_min="0", text_validation_max="500"),
    _field("vitals.height_cm",      "vitals",  "text",    "Height (cm)",
           text_validation_type="number",
           text_validation_min="0", text_validation_max="250"),
    _field("vitals.bmi",            "vitals",  "calc",    "BMI",
           choices="round(([vitals.weight_kg] / (([vitals.height_cm] / 100) ^ 2)), 1)"),

    # ── Conditions (repeating) ───────────────────────────────────────────────
    _field("conditions.snomed_code","conditions","text",  "SNOMED-CT Code",
           section_header="Conditions / Problem List"),
    _field("conditions.display",    "conditions","text",  "Condition Display Name"),
    _field("conditions.onset_date", "conditions","text",  "Onset Date",
           text_validation_type="date_ymd"),
    _field("conditions.status",     "conditions","dropdown","Status",
           choices="active, Active | resolved, Resolved | inactive, Inactive"),
    _field("conditions.notes",      "conditions","notes", "Notes"),

    # ── Medications (repeating) ──────────────────────────────────────────────
    _field("medications.snomed_code","medications","text","SNOMED-CT / NZMT Code",
           section_header="Medications"),
    _field("medications.name",      "medications","text", "Medication Name"),
    _field("medications.dose",      "medications","text", "Dose"),
    _field("medications.frequency", "medications","text", "Frequency"),
    _field("medications.route",     "medications","text", "Route"),
    _field("medications.start_date","medications","text", "Start Date",
           text_validation_type="date_ymd"),
    _field("medications.end_date",  "medications","text", "End Date",
           text_validation_type="date_ymd"),
    _field("medications.status",    "medications","dropdown","Status",
           choices="active, Active | stopped, Stopped | on-hold, On Hold"),

    # ── Allergies (repeating) ───────────────────────────────────────────────
    _field("allergies.allergen_code",   "allergies","text",  "Allergen SNOMED Code",
           section_header="Allergies & Intolerances"),
    _field("allergies.allergen_display","allergies","text",  "Allergen Display Name"),
    _field("allergies.reaction",        "allergies","text",  "Reaction"),
    _field("allergies.severity",        "allergies","radio", "Severity",
           choices="mild, Mild | moderate, Moderate | severe, Severe"),
    _field("allergies.status",          "allergies","dropdown","Status",
           choices="active, Active | inactive, Inactive | resolved, Resolved"),

    # ── Lab Results (repeating) ──────────────────────────────────────────────
    _field("lab_results.loinc_code",           "lab_results","text",    "LOINC Code",
           section_header="Laboratory Results"),
    _field("lab_results.value",                "lab_results","text",    "Value",
           text_validation_type="number"),
    _field("lab_results.unit",                 "lab_results","text",    "Unit"),
    _field("lab_results.reference_range_low",  "lab_results","text",    "Reference Range Low",
           text_validation_type="number"),
    _field("lab_results.reference_range_high", "lab_results","text",    "Reference Range High",
           text_validation_type="number"),
    _field("lab_results.abnormal_flag",        "lab_results","dropdown","Abnormal Flag",
           choices="H, H (High) | L, L (Low) | HH, HH (Critical High) | LL, LL (Critical Low) | N, N (Normal)"),
    _field("lab_results.collected_date",       "lab_results","text",    "Collected Date",
           text_validation_type="date_ymd"),

    # ── Immunizations (repeating) ────────────────────────────────────────────
    _field("immunizations.vaccine_code",    "immunizations","text", "Vaccine SNOMED/CVX Code",
           section_header="Immunizations"),
    _field("immunizations.vaccine_display", "immunizations","text", "Vaccine Display Name"),
    _field("immunizations.date_given",      "immunizations","text", "Date Given",
           text_validation_type="date_ymd"),
    _field("immunizations.lot_number",      "immunizations","text", "Lot Number"),
    _field("immunizations.site",            "immunizations","text", "Administration Site"),

    # ── Social History ───────────────────────────────────────────────────────
    _field("social_history.smoking_status_code","social_history","dropdown","Smoking Status (SNOMED-CT)",
           section_header="Social History",
           choices="266919005, Never smoked | 8517006, Ex-smoker | 77176002, Current smoker | 428041000124106, Light smoker | 428061000124105, Heavy smoker"),
    _field("social_history.pack_years",         "social_history","text",    "Pack Years",
           text_validation_type="number",
           text_validation_min="0",
           branching_logic="[smoking_status_code] <> '' and [smoking_status_code] <> '266919005'"),
    _field("social_history.alcohol_status_code","social_history","dropdown","Alcohol Status (SNOMED-CT)",
           choices="228274009, Non-drinker | 219006, Current drinker | 228276006, Occasional drinker"),
    _field("social_history.alcohol_units_per_week","social_history","text","Alcohol Units per Week",
           text_validation_type="number",
           text_validation_min="0",
           branching_logic="[alcohol_status_code] <> '' and [alcohol_status_code] <> '228274009'"),
    _field("social_history.occupation",         "social_history","text",    "Occupation"),
    _field("social_history.lives_alone",        "social_history","yesno",   "Lives Alone"),

    # ── Clinical Notes (repeating) ───────────────────────────────────────────
    _field("clinical_notes.section","clinical_notes","text",  "Section",
           section_header="Clinical Notes"),
    _field("clinical_notes.text",   "clinical_notes","notes", "Note Text"),
    _field("clinical_notes.author", "clinical_notes","text",  "Author"),
]
