"""
AI integration layer (stub).

Future endpoints will call approved LLM services to suggest finding
classifications based on borescope images and selected AMM references.
All outputs must be validated against approved maintenance data.
"""

from constants import AI_ADVISORY_WARNING


def is_ai_enabled():
    """Return True when AI features are configured and available."""
    return False


def get_advisory_warning():
    return AI_ADVISORY_WARNING


def search_amm_context(base_dir, query, engine_type="", ata="", inspected_area=""):
    """
    Return the most relevant AMM text snippets for manual review or future AI use.

    Does not make automatic airworthiness decisions.
    """
    from amm_storage import search_amm_snippets

    snippets = search_amm_snippets(
        base_dir,
        query=query or "",
        engine_type=engine_type or "",
        ata=ata or "",
        inspected_area=inspected_area or "",
    )
    return {
        "advisory_warning": AI_ADVISORY_WARNING,
        "query": query,
        "engine_type": engine_type,
        "ata": ata,
        "inspected_area": inspected_area,
        "snippets": snippets,
        "airworthiness_decision": None,
        "message": (
            "AMM excerpts are provided for reference only. "
            "Validate all findings against approved maintenance data."
        ),
    }


def suggest_finding_classification(image_path=None, finding_context=None, amm_reference=None):
    """
    Placeholder for future AI-assisted finding analysis.

    finding_context: dict with area, defect_category, comment, etc.
    amm_reference: dict with AMM document metadata linked to the finding.

    Returns a structured suggestion payload for the UI layer.
    """
    return {
        "available": False,
        "advisory_warning": AI_ADVISORY_WARNING,
        "suggested_classification": None,
        "suggested_comment": None,
        "amm_citations": [],
        "confidence": None,
        "airworthiness_decision": None,
        "message": "AI suggestions are not yet enabled. Validate all findings manually.",
    }


def build_ai_context_payload(report_data, photo_meta, amm_document=None):
    """
    Normalized payload for future AI API calls — keeps integration points stable.
    """
    return {
        "report": {
            "report_number": report_data.get("report_number"),
            "aircraft_type": report_data.get("aircraft"),
            "engine_type": report_data.get("engine_type"),
            "registration": report_data.get("registration"),
            "engine_sn": report_data.get("engine_sn"),
        },
        "finding": {
            "area": photo_meta.get("area"),
            "defect_category": photo_meta.get("defect_category"),
            "comment": photo_meta.get("comment"),
            "classification": photo_meta.get("classification"),
            "maintenance_data_reference": photo_meta.get("maintenance_data_reference"),
        },
        "amm_reference": amm_document,
        "advisory_warning": AI_ADVISORY_WARNING,
    }
