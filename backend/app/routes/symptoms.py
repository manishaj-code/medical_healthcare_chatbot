from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_patient_profile
from app.database import get_db
from app.models import Patient, SymptomAssessment
from app.schemas.common import ResponseEnvelope
from app.services.symptom_service import save_assessment

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
