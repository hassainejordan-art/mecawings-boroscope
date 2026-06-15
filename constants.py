CUSTOM_OPTION = "__custom__"

AIRCRAFT_TYPES = [
    "B737-300",
    "B737-400",
    "B737-500",
    "B737-600",
    "B737-700",
    "B737-800",
    "B737-900",
    "B737 MAX 7",
    "B737 MAX 8",
    "B737 MAX 9",
    "A318",
    "A319",
    "A320",
    "A321",
    "A319neo",
    "A320neo",
    "A321neo",
    "A330-200",
    "A330-300",
    "A330neo",
    "A340",
    "A350-900",
    "A350-1000",
    "B757",
    "B767",
    "B777-200",
    "B777-300",
    "B777X",
    "B787-8",
    "B787-9",
    "B787-10",
]

ENGINE_TYPE_GROUPS = {
    "CFM56": [
        "CFM56-3",
        "CFM56-5A",
        "CFM56-5B",
        "CFM56-5C",
        "CFM56-7B",
    ],
    "LEAP": [
        "LEAP-1A",
        "LEAP-1B",
        "LEAP-1C",
    ],
    "Pratt & Whitney": [
        "PW1100G",
        "PW1500G",
        "PW1900G",
        "PW4000",
    ],
    "Rolls Royce": [
        "Trent 700",
        "Trent 800",
        "Trent 900",
        "Trent 1000",
        "Trent XWB",
    ],
    "General Electric": [
        "GE90",
        "GEnx",
    ],
    "IAE": [
        "V2500",
    ],
}

ENGINE_TYPES = [engine for group in ENGINE_TYPE_GROUPS.values() for engine in group]

ENGINE_POSITIONS = [
    "LH",
    "RH",
    "ENG 1",
    "ENG 2",
    "ENG 3",
    "ENG 4",
]

INSPECTION_AREAS = [
    "Fan Blades",
    "Fan Case",
    "Booster",
    "LPC",
    "HPC",
    "Combustion Chamber",
    "Fuel Nozzles",
    "HPT Stage 1",
    "HPT Stage 2",
    "HPT NGV",
    "LPT Stage 1",
    "LPT Stage 2",
    "LPT Stage 3",
    "LPT Stage 4",
    "LPT Stage 5",
    "Exhaust Case",
    "Inner Combustion Liner",
    "Outer Combustion Liner",
    "Transition Duct",
    "Turbine Shroud",
]

# Backward compatibility
ENGINE_AREAS = INSPECTION_AREAS

DEFECT_CATEGORIES = [
    "Cracking",
    "Corrosion",
    "Erosion",
    "Dents / Deformation",
    "Coating Loss",
    "Foreign Object Damage",
    "Missing Material",
    "Discoloration",
    "Other",
]

CLASSIFICATION_LEVELS = ["Acceptable", "Monitor", "Reject"]
SEVERITY_LEVELS = CLASSIFICATION_LEVELS

REPORT_TITLE = "Aircraft Engine Borescope Inspection Report"
REPORT_SUBTITLE = "Mecawings Visual Inspection Findings"

CERTIFICATION_TEXT = (
    "I certify that this borescope inspection has been performed in accordance "
    "with applicable maintenance data and company procedures."
)
