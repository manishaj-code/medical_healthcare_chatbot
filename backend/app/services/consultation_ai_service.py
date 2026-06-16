"""AI clinical suggestions for consultations (assistance only — never auto-prescribe)."""
from __future__ import annotations

import json
import logging
import uuid
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Consultation, ConsultationAiAudit, Patient
from app.multi_agent.llm import AgentLLM, parse_llm_json
from app.services.pre_visit_intake_service import build_structured_intake
from app.services.lab_catalog_service import (
    list_active_lab_catalog,
    match_investigations_to_catalog,
)

logger = logging.getLogger(__name__)
llm = AgentLLM()

DISCLAIMER = "AI suggestions are for assistance only. Doctor must review before use."


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
) -> dict:
    intake = await build_structured_intake(db, patient, consultation.appointment_id)
    batch_id = uuid.uuid4()

    payload = {
        "differential_considerations": [],
        "suggested_investigations": [],
        "suggested_follow_up_days": None,
        "clinical_notes_draft": None,
        "suggested_medications": [],
        "allergy_warnings": [],
        "matched_catalog_tests": [],
        "disclaimer": DISCLAIMER,
        "batch_id": str(batch_id),
    }

    if not llm.available:
        payload["clinical_notes_draft"] = _offline_draft(intake, consultation)
        catalog = await list_active_lab_catalog(db)
        payload["matched_catalog_tests"] = match_investigations_to_catalog(
            _offline_investigations(intake),
            catalog,
        )
        await _audit(db, consultation.id, batch_id, payload, None)
        return payload

    prompt = f"""You are a clinical documentation assistant. Provide SUGGESTIONS ONLY for a licensed doctor.
Never prescribe definitively. Return JSON only:

{{
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

    payload["differential_considerations"] = parsed.get("differential_considerations") or []
    payload["suggested_investigations"] = parsed.get("suggested_investigations") or []
    payload["suggested_follow_up_days"] = parsed.get("suggested_follow_up_days")
    payload["clinical_notes_draft"] = parsed.get("clinical_notes_draft")
    payload["suggested_medications"] = parsed.get("suggested_medications") or []
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
    await _audit(db, consultation.id, batch_id, payload, consultation.doctor_id)
    await db.flush()
    return payload


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


def _offline_draft(intake: dict, consultation: Consultation) -> str:
    cc = consultation.chief_complaint or intake.get("chief_complaint") or "Not documented"
    symptoms = ", ".join(intake.get("symptoms") or []) or "—"
    history = ", ".join(intake.get("medical_history") or []) or "—"
    return (
        f"Chief complaint: {cc}\n"
        f"Symptoms: {symptoms}\n"
        f"Duration: {intake.get('duration') or '—'}\n"
        f"Medical history: {history}\n"
        f"(Offline draft — configure LLM API key for richer suggestions.)"
    )


async def _audit(
    db: AsyncSession,
    consultation_id: UUID,
    batch_id: uuid.UUID,
    payload: dict,
    doctor_id: UUID | None,
) -> None:
    db.add(
        ConsultationAiAudit(
            consultation_id=consultation_id,
            suggestion_batch_id=batch_id,
            suggestion_type="clinical_suggestions",
            ai_payload=payload,
            doctor_id=doctor_id,
        )
    )
