"""AI clinical suggestions for consultations (assistance only — never auto-prescribe)."""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Consultation, ConsultationAiAudit, Patient
from app.multi_agent.llm import AgentLLM, parse_llm_json
from app.services.consultation_transcript_service import get_full_transcript_text, save_transcript_insights
from app.services.lab_catalog_service import (
    list_active_lab_catalog,
    match_investigations_to_catalog,
)
from app.services.pre_visit_intake_service import build_structured_intake

logger = logging.getLogger(__name__)
llm = AgentLLM()

DISCLAIMER = "AI suggestions are for assistance only. Doctor must review before use."


def _as_str_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        cleaned = value.strip()
        return [cleaned] if cleaned else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _as_med_list(value: object) -> list[dict]:
    if value is None:
        return []
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def _as_follow_up_days(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        days = int(float(value))
        return days if days > 0 else None
    except (TypeError, ValueError):
        return None


def _as_optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _check_allergy_warnings(suggested_meds: list[dict], allergies: list[str]) -> list[str]:
    warnings: list[str] = []
    if not allergies:
        return warnings
    allergy_lower = [a.lower() for a in allergies]
    for med in suggested_meds:
        name = (med.get("medicine_name") or med.get("name") or "").lower()
        for allergen in allergy_lower:
            if allergen and allergen in name:
                warnings.append(f"Suggested '{med.get('medicine_name')}' may conflict with allergy: {allergen}")
    return warnings


async def generate_clinical_suggestions(
    db: AsyncSession,
    consultation: Consultation,
    patient: Patient,
    doctor_name: str,
    *,
    transcript_text: str | None = None,
    suggestion_type: str = "clinical_suggestions",
) -> dict:
    intake = await build_structured_intake(db, patient, consultation.appointment_id)
    if transcript_text is None:
        transcript_text = await get_full_transcript_text(db, consultation.id)
    batch_id = uuid.uuid4()

    payload = {
        "differential_considerations": [],
        "suggested_investigations": [],
        "suggested_follow_up_days": None,
        "clinical_notes_draft": None,
        "suggested_medications": [],
        "allergy_warnings": [],
        "matched_catalog_tests": [],
        "patient_concerns": [],
        "transcript_summary": None,
        "chief_complaint_suggestion": None,
        "disclaimer": DISCLAIMER,
        "batch_id": str(batch_id),
    }

    if not llm.available:
        payload["clinical_notes_draft"] = _offline_draft(intake, consultation, transcript_text)
        catalog = await list_active_lab_catalog(db)
        payload["matched_catalog_tests"] = match_investigations_to_catalog(
            _offline_investigations(intake),
            catalog,
        )
        await _audit(db, consultation.id, batch_id, payload, None, suggestion_type)
        return payload

    transcript_block = ""
    if transcript_text and transcript_text.strip():
        transcript_block = f"""
Video consultation transcript (doctor-patient discussion):
{transcript_text[:12000]}
"""

    prompt = f"""You are a clinical documentation assistant. Provide SUGGESTIONS ONLY for a licensed doctor.
Never prescribe definitively. Use the call transcript when available to extract patient concerns and clinical content.
Return JSON only:

{{
  "patient_concerns": ["patient-stated concerns from transcript or intake"],
  "transcript_summary": "2-4 sentence summary of the video discussion or null",
  "chief_complaint_suggestion": "primary complaint in patient words or null",
  "differential_considerations": ["string"],
  "suggested_investigations": ["CBC", "..."],
  "suggested_follow_up_days": 3,
  "clinical_notes_draft": "draft SOAP-style note for doctor to edit",
  "suggested_medications": [
    {{"medicine_name": "...", "strength": "...", "frequency": "...", "duration": "...", "rationale": "..."}}
  ]
}}

Patient intake:
{json.dumps(intake, default=str)[:4000]}
{transcript_block}
Current consultation draft:
chief_complaint: {consultation.chief_complaint or intake.get('chief_complaint')}
clinical_findings: {consultation.clinical_findings}
diagnosis: {consultation.diagnosis}
treatment_plan: {consultation.treatment_plan}

Allergies: {intake.get('allergies')}
Current meds: {intake.get('current_medications')}

Doctor: {doctor_name}
"""

    raw = await llm.complete(prompt, temperature=0.25, json_mode=True)
    parsed = parse_llm_json(raw or "") or {}

    payload["patient_concerns"] = _as_str_list(parsed.get("patient_concerns"))
    payload["transcript_summary"] = _as_optional_str(parsed.get("transcript_summary"))
    payload["chief_complaint_suggestion"] = _as_optional_str(parsed.get("chief_complaint_suggestion"))
    payload["differential_considerations"] = _as_str_list(parsed.get("differential_considerations"))
    payload["suggested_investigations"] = _as_str_list(parsed.get("suggested_investigations"))
    payload["suggested_follow_up_days"] = _as_follow_up_days(parsed.get("suggested_follow_up_days"))
    payload["clinical_notes_draft"] = _as_optional_str(parsed.get("clinical_notes_draft"))
    payload["suggested_medications"] = _as_med_list(parsed.get("suggested_medications"))

    if not any(
        [
            payload["clinical_notes_draft"],
            payload["differential_considerations"],
            payload["suggested_medications"],
            payload["patient_concerns"],
            payload["transcript_summary"],
        ]
    ):
        payload["clinical_notes_draft"] = _offline_draft(intake, consultation, transcript_text)
        payload["patient_concerns"] = _as_str_list(intake.get("symptoms"))
    catalog = await list_active_lab_catalog(db)
    payload["matched_catalog_tests"] = match_investigations_to_catalog(
        payload["suggested_investigations"],
        catalog,
    )
    payload["allergy_warnings"] = _check_allergy_warnings(
        payload["suggested_medications"],
        intake.get("allergies") or [],
    )

    consultation.ai_suggestion_batch_id = batch_id
    await _audit(db, consultation.id, batch_id, payload, consultation.doctor_id, suggestion_type)
    segment_count = 0
    if transcript_text and transcript_text.strip():
        from sqlalchemy import func, select
        from app.models.consultation_transcript import (
            ConsultationTranscriptSegment,
            ConsultationTranscriptSession,
        )

        session_result = await db.execute(
            select(ConsultationTranscriptSession.id)
            .where(ConsultationTranscriptSession.consultation_id == consultation.id)
            .order_by(ConsultationTranscriptSession.started_at.desc())
            .limit(1)
        )
        session_id = session_result.scalar_one_or_none()
        if session_id:
            count_result = await db.execute(
                select(func.count())
                .select_from(ConsultationTranscriptSegment)
                .where(ConsultationTranscriptSegment.session_id == session_id)
            )
            segment_count = int(count_result.scalar_one() or 0)

    await save_transcript_insights(
        db,
        consultation.id,
        {
            "batch_id": str(batch_id),
            "analyzed_at": datetime.now(timezone.utc).isoformat(),
            "segment_count": segment_count,
            "patient_concerns": payload["patient_concerns"],
            "transcript_summary": payload["transcript_summary"],
            "chief_complaint_suggestion": payload["chief_complaint_suggestion"],
            "differential_considerations": payload["differential_considerations"],
            "suggested_investigations": payload["suggested_investigations"],
            "matched_catalog_tests": payload.get("matched_catalog_tests"),
            "suggested_follow_up_days": payload["suggested_follow_up_days"],
            "clinical_notes_draft": payload["clinical_notes_draft"],
            "suggested_medications": payload["suggested_medications"],
            "allergy_warnings": payload["allergy_warnings"],
            "disclaimer": payload["disclaimer"],
        },
    )
    await db.flush()
    return payload


async def generate_suggestions_from_transcript(
    db: AsyncSession,
    consultation: Consultation,
    patient: Patient,
    doctor_name: str,
) -> dict:
    transcript_text = await get_full_transcript_text(db, consultation.id)
    if not transcript_text.strip():
        raise ValueError("No transcript available for this consultation.")
    return await generate_clinical_suggestions(
        db,
        consultation,
        patient,
        doctor_name,
        transcript_text=transcript_text,
        suggestion_type="transcript_analysis",
    )


def _offline_investigations(intake: dict) -> list[str]:
    """Basic symptom-based investigations when LLM is unavailable."""
    symptoms = [s.lower() for s in (intake.get("symptoms") or [])]
    history = [h.lower() for h in (intake.get("medical_history") or [])]
    suggestions: list[str] = []
    if any("fever" in s for s in symptoms):
        suggestions.append("CBC")
    if any("diabetes" in h for h in history) or "diabetes" in " ".join(history):
        suggestions.append("HbA1c")
    if any(k in " ".join(symptoms) for k in ("jaundice", "liver", "abdomen")):
        suggestions.append("LFT")
    return suggestions


def _offline_draft(intake: dict, consultation: Consultation, transcript_text: str | None = None) -> str:
    cc = consultation.chief_complaint or intake.get("chief_complaint") or "Not documented"
    symptoms = ", ".join(intake.get("symptoms") or []) or "—"
    history = ", ".join(intake.get("medical_history") or []) or "—"
    lines = [
        f"Chief complaint: {cc}",
        f"Symptoms: {symptoms}",
        f"Duration: {intake.get('duration') or '—'}",
        f"Medical history: {history}",
    ]
    if transcript_text and transcript_text.strip():
        lines.append("")
        lines.append("Call transcript excerpt:")
        lines.append(transcript_text[:2000])
    lines.append("(Offline draft — configure LLM API key for richer suggestions.)")
    return "\n".join(lines)


async def _audit(
    db: AsyncSession,
    consultation_id: UUID,
    batch_id: uuid.UUID,
    payload: dict,
    doctor_id: UUID | None,
    suggestion_type: str = "clinical_suggestions",
) -> None:
    db.add(
        ConsultationAiAudit(
            consultation_id=consultation_id,
            suggestion_batch_id=batch_id,
            suggestion_type=suggestion_type,
            ai_payload=payload,
            doctor_id=doctor_id,
        )
    )
