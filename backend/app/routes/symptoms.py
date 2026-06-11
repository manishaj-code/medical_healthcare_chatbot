from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_patient_profile
from app.database import get_db
from app.models import Patient, SymptomAssessment
from app.schemas.common import ResponseEnvelope
from app.services.symptom_service import assessment_payload_from_row, save_assessment

router = APIRouter(prefix="/symptoms", tags=["symptoms"])


class AssessRequest(BaseModel):
    symptoms: list[str]
    duration: str | None = None
    conditions: list[str] | None = None


@router.post("/assess")
async def assess(
    data: AssessRequest,
    patient: Patient = Depends(get_patient_profile),
    db: AsyncSession = Depends(get_db),
):
    assessment = await save_assessment(
        db, patient.id, data.symptoms, data.duration, data.conditions
    )
    return ResponseEnvelope(
        data={
            "id": str(assessment.id),
            "risk": assessment.risk_level.value if assessment.risk_level else None,
            "speciality": assessment.recommended_specialty,
            "recommendation": assessment.recommendation_text,
        }
    )


@router.get("/latest-assessment")
async def latest_assessment(patient: Patient = Depends(get_patient_profile), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(SymptomAssessment)
        .where(SymptomAssessment.patient_id == patient.id)
        .order_by(SymptomAssessment.completed_at.desc().nullslast())
        .limit(1)
    )
    assessment = result.scalar_one_or_none()
    if not assessment:
        from app.services.triage_chat_service import persist_triage_for_patient

        assessment = await persist_triage_for_patient(db, patient.id)
    if not assessment:
        return ResponseEnvelope(data=None)
    payload = assessment_payload_from_row(assessment)
    return ResponseEnvelope(
        data={
            "id": payload["id"],
            "risk_level": payload["risk_level"],
            "recommended_specialty": payload["recommended_specialty"],
            "recommendation_text": payload["recommendation_text"],
            "symptoms": payload["symptoms"],
            "duration": payload["duration"],
            "completed_at": payload["completed_at"],
        }
    )


@router.get("/assessments")
async def list_assessments(patient: Patient = Depends(get_patient_profile), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(SymptomAssessment)
        .where(SymptomAssessment.patient_id == patient.id)
        .order_by(SymptomAssessment.completed_at.desc().nullslast())
    )
    return ResponseEnvelope(
        data=[
            {
                "id": str(a.id),
                "risk": a.risk_level.value if a.risk_level else None,
                "specialty": a.recommended_specialty,
                "recommendation": a.recommendation_text,
                "symptoms": (a.symptoms_json or {}).get("symptoms", []),
                "completed_at": a.completed_at.isoformat() if a.completed_at else None,
            }
            for a in result.scalars().all()
        ]
    )
