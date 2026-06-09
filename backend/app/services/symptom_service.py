from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SymptomAssessment
from app.models.enums import RiskLevel


def assess_symptoms(symptoms: list[str], duration: str | None, conditions: list[str] | None) -> dict:
    risk = RiskLevel.low
    specialty = "General Physician"
    recommendation = "Monitor symptoms. Consult a doctor if they worsen."

    symptom_set = {s.lower() for s in symptoms}
    symptom_blob = " ".join(symptoms).lower()
    has_chronic = bool(conditions)

    if "fever" in symptom_blob and "cough" in symptom_blob:
        risk = RiskLevel.medium
        recommendation = "Physician consultation recommended within 24-48 hours."
    if has_chronic and "fever" in symptom_blob:
        risk = RiskLevel.medium
        recommendation = "Given your medical history, please consult a physician within 24-48 hours."
    if "chest pain" in symptom_blob or ("chest" in symptom_blob and "pain" in symptom_blob):
        risk = RiskLevel.emergency
        specialty = "Emergency"
        recommendation = "Seek emergency care immediately."
    if any(w in symptom_blob for w in ("headache", "migraine", "head pain")):
        specialty = "General Physician"
        recommendation = "Rest and hydration may help. Consult a doctor if it persists or worsens."
    if any(w in symptom_blob for w in ("stomach", "abdominal", "nausea", "vomit")):
        specialty = "Gastroenterologist"
        recommendation = "Monitor symptoms. See a gastroenterologist if severe or persistent."
    if any(w in symptom_blob for w in ("skin", "rash", "itch", "allergy")):
        specialty = "Dermatologist"
        recommendation = "Avoid scratching irritated skin. A dermatologist can help if it spreads."

    return {
        "risk_level": risk,
        "recommended_specialty": specialty,
        "recommendation_text": recommendation,
    }


async def save_assessment(
    db: AsyncSession,
    patient_id: UUID,
    symptoms: list[str],
    duration: str | None = None,
    conditions: list[str] | None = None,
    conversation_id: UUID | None = None,
) -> SymptomAssessment:
    result = assess_symptoms(symptoms, duration, conditions)
    assessment = SymptomAssessment(
        patient_id=patient_id,
        conversation_id=conversation_id,
        symptoms_json={"symptoms": symptoms, "conditions": conditions or []},
        duration=duration,
        risk_level=result["risk_level"],
        recommended_specialty=result["recommended_specialty"],
        recommendation_text=result["recommendation_text"],
        completed_at=datetime.now(timezone.utc),
    )
    db.add(assessment)
    await db.flush()
    return assessment
