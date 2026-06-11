"""AI-assisted visual symptom observation from patient-uploaded photos."""
from __future__ import annotations

import asyncio
import json
import logging
import re
from app.database import get_settings
from app.services.report_service import IMAGE_EXTENSIONS, normalize_extension, validate_report_file

logger = logging.getLogger(__name__)
settings = get_settings()

SYMPTOM_IMAGE_MAX_BYTES = 8 * 1024 * 1024
SYMPTOM_IMAGE_ACCEPT = IMAGE_EXTENSIONS

DISCLAIMER = (
    "This is an AI visual observation only — not a medical diagnosis. "
    "Please consult a licensed clinician for proper evaluation."
)


def validate_symptom_image(filename: str, mime_type: str | None, data: bytes) -> tuple[str, str]:
    if len(data) > SYMPTOM_IMAGE_MAX_BYTES:
        raise ValueError("Image is too large. Maximum size is 8 MB.")
    ext, mime = validate_report_file(filename, mime_type, data)
    if ext not in IMAGE_EXTENSIONS:
        raise ValueError("Please upload a photo (PNG, JPG, WebP, GIF, BMP, or TIFF).")
    return ext, mime


def _parse_json(raw: str) -> dict:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            return json.loads(match.group(0))
    return {}


async def analyze_symptom_image(
    data: bytes,
    filename: str,
    mime_type: str | None = None,
    *,
    patient_note: str | None = None,
) -> dict:
    """Use vision LLM to describe visible signs and suggest triage follow-up."""
    ext, resolved_mime = validate_symptom_image(filename, mime_type, data)
    note_line = f"\nPatient note: {patient_note}" if patient_note else ""

    prompt = (
        "You are a medical triage assistant reviewing a patient-submitted symptom photo. "
        "Describe only what is visually observable. Do NOT diagnose or prescribe. "
        f"{note_line}\n\n"
        "Return ONLY JSON:\n"
        "{\n"
        '  "observations": ["short bullet observations"],\n'
        '  "possible_symptoms": ["symptom labels e.g. rash, swelling, redness"],\n'
        '  "risk_level": "low|medium|high|emergency",\n'
        '  "recommendation": "2-3 sentences of safe next steps and when to seek urgent care",\n'
        '  "follow_up_question": "one clarifying question if needed, or null"\n'
        "}"
    )

    if settings.gemini_api_key:
        result = await _analyze_with_gemini(data, resolved_mime, prompt)
        if result:
            return _normalize_result(result)

    return _offline_fallback(ext)


async def _analyze_with_gemini(data: bytes, mime_type: str, prompt: str) -> dict | None:
    import google.generativeai as genai

    def _run() -> dict:
        genai.configure(api_key=settings.gemini_api_key)
        model = genai.GenerativeModel(settings.gemini_model)
        response = model.generate_content(
            [prompt, {"mime_type": mime_type, "data": data}],
            generation_config={"response_mime_type": "application/json"},
        )
        return _parse_json(response.text or "{}")

    try:
        return await asyncio.to_thread(_run)
    except Exception as exc:
        logger.warning("Gemini symptom image analysis failed: %s", exc)
        return None


def _normalize_result(raw: dict) -> dict:
    observations = raw.get("observations") or []
    if isinstance(observations, str):
        observations = [observations]
    symptoms = raw.get("possible_symptoms") or []
    if isinstance(symptoms, str):
        symptoms = [symptoms]
    risk = str(raw.get("risk_level", "low")).lower()
    if risk not in {"low", "medium", "high", "emergency"}:
        risk = "low"
    return {
        "observations": [str(o) for o in observations[:6]],
        "possible_symptoms": [str(s) for s in symptoms[:8]] or ["unspecified symptoms"],
        "risk_level": risk,
        "recommendation": raw.get("recommendation") or "Please monitor symptoms and consult a clinician if they worsen.",
        "follow_up_question": raw.get("follow_up_question"),
        "disclaimer": DISCLAIMER,
    }


def _offline_fallback(ext: str) -> dict:
    return {
        "observations": [
            f"Received a {ext.lstrip('.').upper()} symptom image.",
            "Configure GEMINI_API_KEY for AI visual analysis.",
        ],
        "possible_symptoms": ["unspecified symptoms"],
        "risk_level": "low",
        "recommendation": (
            "Please describe your symptoms in text so I can help assess them, "
            "or configure GEMINI_API_KEY for photo analysis."
        ),
        "follow_up_question": "How long have you been experiencing this?",
        "disclaimer": DISCLAIMER,
    }


def format_symptom_image_reply(analysis: dict) -> str:
    lines = ["**Visual symptom observation**\n"]
    for obs in analysis.get("observations") or []:
        lines.append(f"• {obs}")
    symptoms = analysis.get("possible_symptoms") or []
    if symptoms and symptoms != ["unspecified symptoms"]:
        lines.append(f"\n**Possible related symptoms:** {', '.join(symptoms[:5])}")
    lines.append(f"\n{analysis.get('recommendation', '')}")
    if analysis.get("follow_up_question"):
        lines.append(f"\n_{analysis['follow_up_question']}_")
    lines.append(f"\n\n_{analysis.get('disclaimer', DISCLAIMER)}_")
    return "\n".join(lines)
