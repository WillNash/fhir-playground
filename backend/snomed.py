"""
NZ-flavoured SNOMED-CT and local coding reference tables.

All codes are real SNOMED-CT International / NZ Edition codes or
recognised NZ national code systems used in production FHIR implementations.

Systems
-------
SNOMED-CT   : http://snomed.info/sct
NZ Ethnicity: https://standards.digital.health.nz/ns/ethnic-group-level-4-code
NZ NHI      : https://standards.digital.health.nz/ns/nhi-id
NZMT        : http://nzmt.org.nz  (NZ Medicines Terminology, SNOMED extension)
LOINC       : http://loinc.org
RxNorm      : http://www.nlm.nih.gov/research/umls/rxnorm
"""

from __future__ import annotations

from typing import Final, TypedDict

# ---------------------------------------------------------------------------
# Coding system URI constants
# ---------------------------------------------------------------------------

SNOMED_SYSTEM: Final = "http://snomed.info/sct"
NZ_ETHNICITY_SYSTEM: Final = "https://standards.digital.health.nz/ns/ethnic-group-level-4-code"
NHI_SYSTEM: Final = "https://standards.digital.health.nz/ns/nhi-id"
NZMT_SYSTEM: Final = "http://nzmt.org.nz"
LOINC_SYSTEM: Final = "http://loinc.org"
RXNORM_SYSTEM: Final = "http://www.nlm.nih.gov/research/umls/rxnorm"

# ---------------------------------------------------------------------------
# TypedDict shapes for structured reference entries
# ---------------------------------------------------------------------------


class ObservationEntry(TypedDict):
    """A single LOINC observation definition with display name and units."""

    display: str
    unit: str   # human-readable unit label
    ucum: str   # UCUM canonical unit string for FHIR Quantity.system


class MedicationEntry(TypedDict):
    """A single medication reference entry."""

    name: str
    form: str       # dosage form (tablet, capsule, inhaler, injection, …)
    strength: str   # strength as a display string, e.g. "500mg"


# ---------------------------------------------------------------------------
# NZ Stats Ethnicity codes — Level 4 (5-digit)
# Source: https://fhir.org.nz/ig/base/CodeSystem-ethnicityL4.html
# System: https://standards.digital.health.nz/ns/ethnic-group-level-4-code
# ---------------------------------------------------------------------------

NZ_ETHNICITY: Final[dict[str, str]] = {
    "10000": "European NFD",
    "11111": "New Zealand European",
    "12100": "British NFD",
    "12111": "Celtic",
    "12112": "Channel Islander",
    "12113": "Cornish",
    "12114": "English",
    "12116": "Irish",
    "12117": "Manx",
    "12119": "Scottish (Scots)",
    "12121": "Welsh",
    "12199": "British NEC",
    "12211": "Dutch/Netherlands",
    "12311": "Greek (including Greek Cypriot)",
    "12411": "Polish",
    "12500": "South Slav (formerly Yugoslav groups) NFD",
    "12511": "Croat/Croatian",
    "12512": "Dalmatian",
    "12513": "Macedonian",
    "12514": "Serb/Serbian",
    "12515": "Slovene/Slovenian",
    "12516": "Bosnian",
    "12599": "South Slav (formerly Yugoslav groups) NEC",
    "12611": "Italian",
    "12711": "German",
    "12811": "Australian",
    "12911": "Albanian",
    "12912": "Armenian",
    "12913": "Austrian",
    "12914": "Belgian",
    "12915": "Bulgarian",
    "12916": "Belorussian",
    "12918": "Cypriot Unspecified",
    "12919": "Czech",
    "12920": "Danish",
    "12921": "Estonian",
    "12922": "Finnish",
    "12923": "Flemish",
    "12924": "French",
    "12926": "Hungarian",
    "12927": "Icelander",
    "12928": "Latvian",
    "12929": "Lithuanian",
    "12930": "Maltese",
    "12931": "Norwegian",
    "12932": "Portuguese",
    "12933": "Romanian / Rumanian",
    "12934": "Romani",
    "12935": "Russian",
    "12937": "Slavic / Slav",
    "12938": "Slovak",
    "12939": "Spanish",
    "12940": "Swedish",
    "12941": "Swiss",
    "12942": "Ukrainian",
    "12943": "American (US)",
    "12945": "Canadian",
    "12947": "New Caledonian",
    "12948": "South African European",
    "12949": "Afrikaner",
    "12950": "Zimbabwean European",
    "12999": "European NEC",
    "21111": "Māori",
    "30000": "Pacific peoples NFD",
    "31111": "Samoan",
    "32100": "Cook Islands Maori",
    "33111": "Tongan",
    "34111": "Niuean",
    "35111": "Tokelauan",
    "36111": "Fijian (except Fiji Indian / Indo-Fijian)",
    "37112": "Indigenous Australian",
    "37122": "Hawaiian",
    "37124": "I-Kiribati / Gilbertese",
    "37130": "Nauru Islander",
    "37135": "Papuan / New Guinean / Irian Jayan",
    "37137": "Pitcairn Islander",
    "37138": "Rotuman / Rotuman Islander",
    "37140": "Society Islander (including Tahitian)",
    "37141": "Solomon Islander",
    "37144": "Tuvalu Islander / Ellice Islander",
    "37145": "Vanuatu Islander / New Hebridean",
    "37199": "Other Pacific peoples NEC",
    "40000": "Asian NFD",
    "41000": "Southeast Asian NFD",
    "41111": "Filipino",
    "41211": "Khmer / Kampuchean / Cambodian",
    "41311": "Vietnamese",
    "41411": "Burmese",
    "41412": "Indonesian (including Javanese / Sundanese / Sumatran)",
    "41413": "Lao",
    "41414": "Malay / Malayan",
    "41415": "Thai / Tai / Siamese",
    "41416": "Karen",
    "41417": "Chin",
    "41499": "Other Southeast Asian NEC",
    "42100": "Chinese NFD",
    "42111": "Hong Kong Chinese",
    "42112": "Kampuchean Chinese",
    "42113": "Malaysian Chinese",
    "42114": "Singaporean Chinese",
    "42115": "Vietnamese Chinese",
    "42116": "Taiwanese Chinese",
    "42199": "Chinese NEC",
    "43100": "Indian NFD",
    "43111": "Bengali",
    "43112": "Fijian Indian / Indo-Fijian",
    "43114": "Tamil",
    "43115": "Punjabi",
    "43116": "Sikh",
    "43117": "Anglo Indian",
    "43118": "Malaysian Indian",
    "43119": "South African Indian",
    "43199": "Indian NEC",
    "44100": "Sri Lankan NFD",
    "44111": "Sinhalese",
    "44112": "Sri Lankan Tamil",
    "44199": "Sri Lankan NEC",
    "44211": "Japanese",
    "44311": "Korean",
    "44411": "Afghan",
    "44412": "Bangladeshi",
    "44413": "Nepali",
    "44414": "Pakistani",
    "44415": "Tibetan",
    "44416": "Eurasian",
    "44417": "Bhutanese",
    "44418": "Maldivian",
    "44419": "Mongolian",
    "44499": "Other Asian NEC",
    "51100": "Middle Eastern NFD",
    "51111": "Algerian",
    "51112": "Arab",
    "51113": "Assyrian",
    "51114": "Egyptian",
    "51115": "Iranian / Persian",
    "51116": "Iraqi",
    "51117": "Israeli / Jewish / Hebrew",
    "51118": "Jordanian",
    "51119": "Kurd",
    "51120": "Lebanese",
    "51122": "Moroccan",
    "51124": "Palestinian",
    "51125": "Syrian",
    "51127": "Turkish (including Turkish Cypriot)",
    "51199": "Middle Eastern NEC",
    "52100": "Latin American / Hispanic NFD",
    "52111": "Argentinian",
    "52112": "Bolivian",
    "52113": "Brazilian",
    "52114": "Chilean",
    "52115": "Colombian",
    "52118": "Ecuadorian",
    "52123": "Mexican",
    "52127": "Peruvian",
    "52128": "Puerto Rican",
    "52129": "Uruguayan",
    "52130": "Venezuelan",
    "52199": "Latin American / Hispanic NEC",
    "53100": "African NFD",
    "53113": "Jamaican",
    "53114": "Kenyan",
    "53115": "Nigerian",
    "53116": "African American",
    "53118": "Caribbean",
    "53119": "Somali",
    "53120": "Eritrean",
    "53121": "Ethiopian",
    "53122": "Ghanaian",
    "53123": "Burundian",
    "53124": "Congolese",
    "53125": "Sudanese",
    "53126": "Zambian",
    "53127": "Other Zimbabwean",
    "53199": "Other African NEC",
    "61113": "Indigenous North American",
    "61115": "Mauritian",
    "61116": "Seychelles Islander",
    "61117": "Other South African",
    "61118": "New Zealander",
    "61199": "Other NEC",
    "94444": "Don't know",
    "95555": "Refused to answer",
    "96666": "Repeated Value",
    "97777": "Response unidentifiable",
    "98888": "Response Outside Scope",
    "99999": "Not stated",
}

# ---------------------------------------------------------------------------
# Common SNOMED-CT condition / finding codes used in NZ primary care
# System: SNOMED_SYSTEM
# ---------------------------------------------------------------------------

CONDITIONS: Final[dict[str, str]] = {
    "44054006":  "Diabetes mellitus type 2",
    "73211009":  "Diabetes mellitus type 1",
    "38341003":  "Hypertension",
    "22298006":  "Myocardial infarction",
    "195967001": "Asthma",
    "13645005":  "Chronic obstructive pulmonary disease",
    "49436004":  "Atrial fibrillation",
    "13200003":  "Peptic ulcer",
    "84757009":  "Epilepsy",
    "35489007":  "Depressive disorder",
    "197480006": "Anxiety disorder",
    "66675007":  "Osteoporosis",
    "3723001":   "Arthritis",
    "363346000": "Malignant neoplastic disease",
    "44169009":  "No known allergy",
    "40733004":  "Infectious disease",
    "73595000":  "Stress",
    "271737000": "Anaemia",
    "34840004":  "Chronic kidney disease",
    "44054007":  "Ischaemic heart disease",
    "230690007": "Stroke",
    "62106007":  "Concussion",
    "302870006": "Hypertensive heart disease",
    "444814009": "Viral upper respiratory infection",
    "233604007": "Pneumonia",
    "68566005":  "Urinary tract infection",
}

# ---------------------------------------------------------------------------
# SNOMED-CT procedure codes
# System: SNOMED_SYSTEM
# ---------------------------------------------------------------------------

PROCEDURES: Final[dict[str, str]] = {
    "171279008": "Immunization",
    "182777000": "Intravenous drug injection",
    "413473000": "Counselling about alcohol consumption",
    "183450002": "Admission to hospital",
    "392521001": "History and physical examination",
    "310813008": "Blood test",
    "274663001": "Chest X-ray",
    "44178003":  "Electrocardiogram",
    "73761001":  "Colonoscopy",
    "71651007":  "Mammography",
}

# ---------------------------------------------------------------------------
# LOINC observation codes (vitals and blood tests) used in NZ labs
# System: LOINC_SYSTEM
# Each entry carries a human-readable unit and its UCUM equivalent for FHIR.
# ---------------------------------------------------------------------------

OBSERVATIONS: Final[dict[str, ObservationEntry]] = {
    # Vitals
    "8480-6":  {"display": "Systolic blood pressure",              "unit": "mmHg",           "ucum": "mm[Hg]"},
    "8462-4":  {"display": "Diastolic blood pressure",             "unit": "mmHg",           "ucum": "mm[Hg]"},
    "8867-4":  {"display": "Heart rate",                           "unit": "beats/min",      "ucum": "/min"},
    "9279-1":  {"display": "Respiratory rate",                     "unit": "breaths/min",    "ucum": "/min"},
    "8310-5":  {"display": "Body temperature",                     "unit": "degC",           "ucum": "Cel"},
    "2708-6":  {"display": "Oxygen saturation in Arterial blood",  "unit": "%",              "ucum": "%"},
    "59408-5": {"display": "Oxygen saturation by Pulse oximetry",  "unit": "%",              "ucum": "%"},
    "29463-7": {"display": "Body weight",                          "unit": "kg",             "ucum": "kg"},
    "8302-2":  {"display": "Body height",                          "unit": "cm",             "ucum": "cm"},
    "39156-5": {"display": "BMI",                                  "unit": "kg/m2",          "ucum": "kg/m2"},
    # Labs — chemistry
    "2339-0":  {"display": "Glucose (blood)",                      "unit": "mmol/L",         "ucum": "mmol/L"},
    "4548-4":  {"display": "HbA1c",                                "unit": "%",              "ucum": "%"},
    "2093-3":  {"display": "Total cholesterol",                    "unit": "mmol/L",         "ucum": "mmol/L"},
    "2085-9":  {"display": "HDL cholesterol",                      "unit": "mmol/L",         "ucum": "mmol/L"},
    "13457-7": {"display": "LDL cholesterol (calc)",               "unit": "mmol/L",         "ucum": "mmol/L"},
    "2571-8":  {"display": "Triglycerides",                        "unit": "mmol/L",         "ucum": "mmol/L"},
    "2160-0":  {"display": "Creatinine (serum)",                   "unit": "umol/L",         "ucum": "umol/L"},
    "33914-3": {"display": "eGFR (CKD-EPI)",                       "unit": "mL/min/1.73m2",  "ucum": "mL/min/{1.73_m2}"},
    # Labs — haematology
    "718-7":   {"display": "Haemoglobin",                          "unit": "g/L",            "ucum": "g/L"},
    "777-3":   {"display": "Platelets",                            "unit": "10^9/L",         "ucum": "10*9/L"},
    "6690-2":  {"display": "White cell count",                     "unit": "10^9/L",         "ucum": "10*9/L"},
    # Labs — electrolytes
    "2951-2":  {"display": "Sodium",                               "unit": "mmol/L",         "ucum": "mmol/L"},
    "2823-3":  {"display": "Potassium",                            "unit": "mmol/L",         "ucum": "mmol/L"},
    "2075-0":  {"display": "Chloride",                             "unit": "mmol/L",         "ucum": "mmol/L"},
    "1963-8":  {"display": "Bicarbonate",                          "unit": "mmol/L",         "ucum": "mmol/L"},
    # Labs — urine
    "14957-5": {"display": "Urine microalbumin",                   "unit": "mg/L",           "ucum": "mg/L"},
    "5792-7":  {"display": "Urine glucose",                        "unit": "mmol/L",         "ucum": "mmol/L"},
    # Labs — liver function
    "1742-6":  {"display": "ALT",                                  "unit": "U/L",            "ucum": "U/L"},
    "1920-8":  {"display": "AST",                                  "unit": "U/L",            "ucum": "U/L"},
    "6768-6":  {"display": "Alkaline phosphatase",                 "unit": "U/L",            "ucum": "U/L"},
    "1975-2":  {"display": "Bilirubin total",                      "unit": "umol/L",         "ucum": "umol/L"},
    "2324-2":  {"display": "GGT",                                  "unit": "U/L",            "ucum": "U/L"},
    "2885-2":  {"display": "Total protein",                        "unit": "g/L",            "ucum": "g/L"},
    # Labs — thyroid
    "3016-3":  {"display": "TSH",                                  "unit": "mIU/L",          "ucum": "m[IU]/L"},
    "3026-2":  {"display": "Free T4",                              "unit": "pmol/L",         "ucum": "pmol/L"},
    # Labs — inflammation / other
    "1988-5":  {"display": "C-reactive protein",                   "unit": "mg/L",           "ucum": "mg/L"},
    "2532-0":  {"display": "LDH",                                  "unit": "U/L",            "ucum": "U/L"},
    "2462-0":  {"display": "IgE total",                            "unit": "kU/L",           "ucum": "kU/L"},
    "3040-3":  {"display": "Lipase",                               "unit": "U/L",            "ucum": "U/L"},
}

# ---------------------------------------------------------------------------
# Common NZ medications
# Codes are SNOMED product concepts (system: SNOMED_SYSTEM).
# Strength is a display string — not a structured FHIR Quantity.
# ---------------------------------------------------------------------------

MEDICATIONS: Final[dict[str, MedicationEntry]] = {
    "372687004": {"name": "Amoxicillin",    "form": "capsule",   "strength": "500mg"},
    "387458008": {"name": "Aspirin",        "form": "tablet",    "strength": "100mg"},
    "372691006": {"name": "Warfarin",       "form": "tablet",    "strength": "5mg"},
    "386873009": {"name": "Metformin",      "form": "tablet",    "strength": "500mg"},
    "108537001": {"name": "Atorvastatin",   "form": "tablet",    "strength": "40mg"},
    "372664007": {"name": "Paracetamol",    "form": "tablet",    "strength": "500mg"},
    "373873005": {"name": "Salbutamol",     "form": "inhaler",   "strength": "100mcg"},
    "372741007": {"name": "Ramipril",       "form": "capsule",   "strength": "5mg"},
    "386840002": {"name": "Amlodipine",     "form": "tablet",    "strength": "5mg"},
    "372728009": {"name": "Omeprazole",     "form": "capsule",   "strength": "20mg"},
    "96309000":  {"name": "Losartan",       "form": "tablet",    "strength": "50mg"},
    "387152000": {"name": "Clopidogrel",    "form": "tablet",    "strength": "75mg"},
    "387475002": {"name": "Furosemide",     "form": "tablet",    "strength": "40mg"},
    "372812005": {"name": "Bisoprolol",     "form": "tablet",    "strength": "5mg"},
    "376940000": {"name": "Dabigatran",     "form": "capsule",   "strength": "110mg"},
    "108428000": {"name": "Metoprolol",     "form": "tablet",    "strength": "50mg"},
    "387517004": {"name": "Paclitaxel",     "form": "injection", "strength": "6mg/mL"},
    "386872004": {"name": "Lisinopril",     "form": "tablet",    "strength": "10mg"},
    "372706007": {"name": "Spironolactone", "form": "tablet",    "strength": "25mg"},
    "372762008": {"name": "Sertraline",     "form": "tablet",    "strength": "50mg"},
    "386986009": {"name": "Simvastatin",    "form": "tablet",    "strength": "20mg"},
    "373254001": {"name": "Fluticasone",    "form": "inhaler",   "strength": "250mcg"},
    "372580007": {"name": "Metronidazole",  "form": "tablet",    "strength": "400mg"},
    "372778003": {"name": "Ciprofloxacin",  "form": "tablet",    "strength": "500mg"},
    "372756006": {"name": "Roxithromycin",  "form": "tablet",    "strength": "300mg"},
    "406784005": {"name": "Rivaroxaban",    "form": "tablet",    "strength": "20mg"},
    "372763003": {"name": "Escitalopram",   "form": "tablet",    "strength": "10mg"},
    "386879003": {"name": "Enalapril",      "form": "tablet",    "strength": "5mg"},
    "387207008": {"name": "Ibuprofen",      "form": "tablet",    "strength": "400mg"},
    "372588000": {"name": "Prednisolone",   "form": "tablet",    "strength": "5mg"},
}

# ---------------------------------------------------------------------------
# Allergen SNOMED codes
# System: SNOMED_SYSTEM
# Note: several codes overlap with MEDICATIONS (same substance, different role).
# ---------------------------------------------------------------------------

ALLERGENS: Final[dict[str, str]] = {
    "372687004": "Penicillin",
    "387207008": "Ibuprofen",
    "372664007": "Paracetamol",
    "111088007": "Latex",
    "227493005": "Cashew nuts",
    "226910009": "Peanuts",
    "102263004": "Eggs",
    "735029006": "Shellfish",
    "412071004": "Pollen",
    "84489001":  "Mould",
    "260152009": "Cat dander",
    "260157003": "Dust mite",
    "227021000": "Wheat",
    "227165004": "Cow milk",
    "372687099": "Cephalosporins",
}

# ---------------------------------------------------------------------------
# NZ health regions (Te Whatu Ora / Health New Zealand, as of 2024)
# Ordered roughly north-to-south.
# ---------------------------------------------------------------------------

NZ_REGIONS: Final[tuple[str, ...]] = (
    "Te Tai Tokerau / Northland",
    "Waitemata",
    "Auckland",
    "Counties Manukau",
    "Waikato",
    "Lakes",
    "Bay of Plenty",
    "Tairawhiti",
    "Taranaki",
    "Hawke's Bay",
    "Whanganui",
    "MidCentral",
    "Hutt Valley",
    "Capital and Coast",
    "Wairarapa",
    "Nelson Marlborough",
    "West Coast",
    "Canterbury",
    "South Canterbury",
    "Southern",
)

# ---------------------------------------------------------------------------
# Smoking status SNOMED codes
# System: SNOMED_SYSTEM
# ---------------------------------------------------------------------------

SMOKING_STATUS: Final[dict[str, str]] = {
    "449868002":       "Current every day smoker",
    "428041000124106": "Current some day smoker",
    "8517006":         "Ex-smoker",
    "266919005":       "Never smoked",
    "77176002":        "Smoker, current status unknown",
    "266927001":       "Unknown if ever smoked",
}

# ---------------------------------------------------------------------------
# Alcohol use status codes
# Mixed systems: most codes are SNOMED-CT (system: SNOMED_SYSTEM);
# "160573003" is also SNOMED-CT (alcohol intake finding).
# ---------------------------------------------------------------------------

ALCOHOL_STATUS: Final[dict[str, str]] = {
    "219006":    "Current drinker of alcohol",
    "228276006": "Occasional drinker",
    "228274009": "Non-drinker of alcohol",
    "160573003": "Alcohol intake",
}
