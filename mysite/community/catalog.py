from __future__ import annotations

CATEGORY_GENERAL = "GENERAL"
CATEGORY_MIND = "MIND"
CATEGORY_SKIN = "SKIN"
CATEGORY_SENIOR = "SENIOR"
CATEGORY_RESP = "RESP"
CATEGORY_CARDIO = "CARDIO"
CATEGORY_NEURO = "NEURO"
CATEGORY_DIGESTIVE = "DIGESTIVE"
CATEGORY_ENDOCRINE = "ENDOCRINE"
CATEGORY_RENAL = "RENAL"
CATEGORY_MUSCULO = "MUSCULO"
CATEGORY_INFECTIOUS = "INFECTIOUS"
CATEGORY_ENT = "ENT"
CATEGORY_EYE = "EYE"
CATEGORY_DENTAL = "DENTAL"
CATEGORY_REPRODUCTIVE = "REPRODUCTIVE"
CATEGORY_CHILD_DEV = "CHILD_DEV"
CATEGORY_CANCER = "CANCER"
CATEGORY_IMMUNE = "IMMUNE"

ROOM_CODE_GENERAL = "group-general-care"
ROOM_CODE_MIND = "group-mind-support"
ROOM_CODE_SKIN = "group-skin-infection"
ROOM_CODE_SENIOR = "group-senior-support"
ROOM_CODE_RESP = "group-respiratory-care"
ROOM_CODE_CARDIO = "group-cardiac-care"
ROOM_CODE_NEURO = "group-neuro-care"
ROOM_CODE_DIGESTIVE = "group-digestive-care"
ROOM_CODE_ENDOCRINE = "group-endocrine-care"
ROOM_CODE_RENAL = "group-renal-care"
ROOM_CODE_MUSCULO = "group-musculo-care"
ROOM_CODE_INFECTIOUS = "group-infectious-care"
ROOM_CODE_ENT = "group-ent-care"
ROOM_CODE_EYE = "group-eye-care"
ROOM_CODE_DENTAL = "group-dental-care"
ROOM_CODE_REPRODUCTIVE = "group-reproductive-care"
ROOM_CODE_CHILD_DEV = "group-child-development-care"
ROOM_CODE_CANCER = "group-oncology-care"
ROOM_CODE_IMMUNE = "group-immune-care"

ROOM_CATALOG: tuple[dict, ...] = (
    {
        "category": CATEGORY_GENERAL,
        "room_code": ROOM_CODE_GENERAL,
        "name": "General Care Group",
        "description": "Shared chat for serious cases that need broad support.",
        "keywords": (),
    },
    {
        "category": CATEGORY_MIND,
        "room_code": ROOM_CODE_MIND,
        "name": "Mind Support Group",
        "description": "Shared chat for mood, behavior, cognitive, and neurodevelopment conditions.",
        "keywords": (
            "anxiety",
            "depression",
            "bipolar",
            "schizo",
            "schizophrenia",
            "personality disorder",
            "eating disorder",
            "autism",
            "adhd",
            "neurodevelopment",
            "panic",
            "ocd",
            "ptsd",
            "insomnia",
            "mood disorder",
            "down syndrome",
            "intellectual disability",
            "learning disability",
            "cognitive",
            "behavior",
            "stress disorder",
        ),
    },
    {
        "category": CATEGORY_SKIN,
        "room_code": ROOM_CODE_SKIN,
        "name": "Skin Infection Group",
        "description": "Shared chat for skin and dermatology-related conditions.",
        "keywords": (
            "skin",
            "rash",
            "fungal",
            "eczema",
            "psoriasis",
            "dermatitis",
            "hives",
            "itch",
            "acne",
            "cellulitis",
            "boil",
            "lesion",
        ),
    },
    {
        "category": CATEGORY_RESP,
        "room_code": ROOM_CODE_RESP,
        "name": "Respiratory Care Group",
        "description": "Shared chat for breathing and lung-related conditions.",
        "keywords": (
            "asthma",
            "copd",
            "bronch",
            "cough",
            "breath",
            "lung",
            "respiratory",
            "pneumonia",
            "wheez",
            "sinobronch",
        ),
    },
    {
        "category": CATEGORY_CARDIO,
        "room_code": ROOM_CODE_CARDIO,
        "name": "Cardiac Care Group",
        "description": "Shared chat for heart and circulation-related conditions.",
        "keywords": (
            "cardio",
            "heart",
            "hypertension",
            "blood pressure",
            "angina",
            "arrhythmia",
            "palpitation",
            "stroke risk",
            "cholesterol",
        ),
    },
    {
        "category": CATEGORY_NEURO,
        "room_code": ROOM_CODE_NEURO,
        "name": "Neuro Care Group",
        "description": "Shared chat for nervous-system and neuro disorders.",
        "keywords": (
            "neuro",
            "seizure",
            "epilep",
            "migraine",
            "neuropathy",
            "tremor",
            "parkinson",
            "alzheimer",
            "dementia",
            "multiple sclerosis",
            "ms ",
        ),
    },
    {
        "category": CATEGORY_DIGESTIVE,
        "room_code": ROOM_CODE_DIGESTIVE,
        "name": "Digestive Care Group",
        "description": "Shared chat for stomach, intestine, and liver-related conditions.",
        "keywords": (
            "gerd",
            "gastric",
            "ulcer",
            "stomach",
            "digest",
            "colitis",
            "crohn",
            "constipation",
            "diarrhea",
            "liver",
            "hepatitis",
            "ibs",
        ),
    },
    {
        "category": CATEGORY_ENDOCRINE,
        "room_code": ROOM_CODE_ENDOCRINE,
        "name": "Endocrine Care Group",
        "description": "Shared chat for hormone and metabolism-related conditions.",
        "keywords": (
            "diabetes",
            "thyroid",
            "hormone",
            "endocrine",
            "insulin",
            "pcos",
            "metabolic",
            "adrenal",
            "pituitary",
        ),
    },
    {
        "category": CATEGORY_RENAL,
        "room_code": ROOM_CODE_RENAL,
        "name": "Renal Care Group",
        "description": "Shared chat for kidney and urinary-related conditions.",
        "keywords": (
            "kidney",
            "renal",
            "nephro",
            "urinary",
            "uti",
            "dialysis",
            "creatinine",
            "proteinuria",
            "stones",
        ),
    },
    {
        "category": CATEGORY_MUSCULO,
        "room_code": ROOM_CODE_MUSCULO,
        "name": "Musculoskeletal Care Group",
        "description": "Shared chat for bones, joints, muscles, and pain conditions.",
        "keywords": (
            "arthritis",
            "joint",
            "muscle",
            "bone",
            "back pain",
            "spine",
            "ligament",
            "tendon",
            "osteoporosis",
            "fibromyalgia",
        ),
    },
    {
        "category": CATEGORY_INFECTIOUS,
        "room_code": ROOM_CODE_INFECTIOUS,
        "name": "Infectious Care Group",
        "description": "Shared chat for infectious and fever-related conditions.",
        "keywords": (
            "infection",
            "fever",
            "viral",
            "bacterial",
            "dengue",
            "malaria",
            "typhoid",
            "tuberculosis",
            "covid",
            "flu",
        ),
    },
    {
        "category": CATEGORY_ENT,
        "room_code": ROOM_CODE_ENT,
        "name": "ENT Care Group",
        "description": "Shared chat for ear, nose, and throat-related conditions.",
        "keywords": (
            "ear",
            "nose",
            "throat",
            "tonsil",
            "sinus",
            "rhinitis",
            "hearing",
            "tinnitus",
            "pharyng",
            "laryng",
        ),
    },
    {
        "category": CATEGORY_EYE,
        "room_code": ROOM_CODE_EYE,
        "name": "Eye Care Group",
        "description": "Shared chat for vision and eye-related conditions.",
        "keywords": (
            "eye",
            "vision",
            "retina",
            "glaucoma",
            "cataract",
            "conjunctivitis",
            "dry eye",
            "optic",
        ),
    },
    {
        "category": CATEGORY_DENTAL,
        "room_code": ROOM_CODE_DENTAL,
        "name": "Dental Care Group",
        "description": "Shared chat for oral and dental-related conditions.",
        "keywords": (
            "dental",
            "tooth",
            "gum",
            "oral",
            "cavity",
            "gingivitis",
            "periodontal",
            "jaw pain",
        ),
    },
    {
        "category": CATEGORY_REPRODUCTIVE,
        "room_code": ROOM_CODE_REPRODUCTIVE,
        "name": "Reproductive Health Group",
        "description": "Shared chat for reproductive and gynecology/urology-related conditions.",
        "keywords": (
            "pregnan",
            "fertility",
            "menstrual",
            "ovary",
            "uterus",
            "prostate",
            "erectile",
            "endometriosis",
            "gyneco",
            "urology",
        ),
    },
    {
        "category": CATEGORY_CHILD_DEV,
        "room_code": ROOM_CODE_CHILD_DEV,
        "name": "Child Development Group",
        "description": "Shared chat for growth and developmental conditions in younger age groups.",
        "keywords": (
            "developmental delay",
            "speech delay",
            "growth delay",
            "child development",
            "pediatric development",
            "autism child",
            "adhd child",
        ),
    },
    {
        "category": CATEGORY_CANCER,
        "room_code": ROOM_CODE_CANCER,
        "name": "Oncology Care Group",
        "description": "Shared chat for cancer and oncology-related conditions.",
        "keywords": (
            "cancer",
            "tumor",
            "carcinoma",
            "oncology",
            "metastasis",
            "chemotherapy",
            "radiation",
            "leukemia",
            "lymphoma",
        ),
    },
    {
        "category": CATEGORY_IMMUNE,
        "room_code": ROOM_CODE_IMMUNE,
        "name": "Immune Care Group",
        "description": "Shared chat for autoimmune and immune-system-related conditions.",
        "keywords": (
            "autoimmune",
            "lupus",
            "immune",
            "immunology",
            "rheumatoid",
            "psoriatic",
            "vasculitis",
            "celiac",
            "hashimoto",
        ),
    },
    {
        "category": CATEGORY_SENIOR,
        "room_code": ROOM_CODE_SENIOR,
        "name": "Senior Support Group",
        "description": "Shared chat for age-related conditions and long-term care support.",
        "keywords": (
            "old age",
            "geriatric",
            "senior",
            "frailty",
            "age-related",
            "caregiver",
        ),
    },
)

ENABLED_COMMUNITY_CATEGORIES: tuple[str, ...] = tuple(entry["category"] for entry in ROOM_CATALOG)
DEFAULT_COMMUNITY_ROOMS: tuple[tuple[str, str, str, str], ...] = tuple(
    (entry["room_code"], entry["category"], entry["name"], entry["description"]) for entry in ROOM_CATALOG
)

CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    entry["category"]: tuple(entry["keywords"]) for entry in ROOM_CATALOG
}
CATEGORY_TO_ROOM_CODE: dict[str, str] = {
    entry["category"]: entry["room_code"] for entry in ROOM_CATALOG
}

CATEGORY_MATCH_PRIORITY: tuple[str, ...] = (
    CATEGORY_MIND,
    CATEGORY_SKIN,
    CATEGORY_RESP,
    CATEGORY_CARDIO,
    CATEGORY_NEURO,
    CATEGORY_DIGESTIVE,
    CATEGORY_ENDOCRINE,
    CATEGORY_RENAL,
    CATEGORY_MUSCULO,
    CATEGORY_INFECTIOUS,
    CATEGORY_ENT,
    CATEGORY_EYE,
    CATEGORY_DENTAL,
    CATEGORY_REPRODUCTIVE,
    CATEGORY_CHILD_DEV,
    CATEGORY_CANCER,
    CATEGORY_IMMUNE,
    CATEGORY_SENIOR,
)

EMERGENCY_CHAT_PHRASES: tuple[str, ...] = (
    "cannot breathe",
    "can't breathe",
    "severe chest pain",
    "unconscious",
    "heavy bleeding",
    "suicidal",
    "suicide",
)

UNSAFE_ADVICE_PHRASES: tuple[str, ...] = (
    "stop your medicine",
    "ignore doctor",
    "don't go to hospital",
    "dont go to hospital",
    "overdose",
    "take double dose",
    "self medicate",
)

LIKELIHOOD_CONFIDENCE_MAP: dict[str, float] = {
    "very high": 0.92,
    "high": 0.84,
    "moderate": 0.70,
    "medium": 0.70,
    "low": 0.52,
    "very low": 0.40,
}
