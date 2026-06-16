from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_current_user, get_db, get_patient_profile
from app.models import Patient, User
from app.schemas.common import ResponseEnvelope
from app.services.urgent_consult_service import (
    create_urgent_request,
    get_request_for_patient,
    retry_urgent_broadcast,
)

router = APIRouter(prefix="/urgent-consult", tags=["urgent-consult"])


class CreateUrgentConsultRequest(BaseModel):
    symptoms: list[str]
    specialty: str
    risk_level: str = "high"
    patient_message: str = ""
    conversation_id: UUID | None = None


@router.post("/requests")
async def create_request(
    data: CreateUrgentConsultRequest,
    patient: Patient = Depends(get_patient_profile),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    payload = await create_urgent_request(
        db,
        patient,
        data.conversation_id,
        symptoms=data.symptoms,
        specialty=data.specialty,
        risk_level=data.risk_level,
        patient_message=data.patient_message or "",
    )
    await db.commit()
    return ResponseEnvelope(data=payload)


@router.get("/requests/{request_id}")
async def get_request(
    request_id: UUID,
    patient: Patient = Depends(get_patient_profile),
    db: AsyncSession = Depends(get_db),
):
    payload = await get_request_for_patient(db, patient.id, request_id)
    return ResponseEnvelope(data=payload)


@router.post("/requests/{request_id}/retry")
async def retry_request_broadcast(
    request_id: UUID,
    patient: Patient = Depends(get_patient_profile),
    db: AsyncSession = Depends(get_db),
):
    payload = await retry_urgent_broadcast(db, patient.id, request_id)
    await db.commit()
    return ResponseEnvelope(data=payload)
