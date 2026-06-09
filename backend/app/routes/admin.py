from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, require_admin
from app.models import Appointment, Conversation, SymptomAssessment, User
from app.models.system import AuditLog
from app.schemas.admin import DeleteAccountResponse, ResetDataRequest, ResetDataResponse
from app.schemas.common import ResponseEnvelope
from app.services.admin_service import (
    delete_doctor_account,
    delete_patient_account,
    list_doctors_admin,
    list_patients_admin,
    truncate_all_data,
    truncate_keep_doctors,
)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users")
async def list_users(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    return ResponseEnvelope(
        data=[{"id": str(u.id), "name": u.name, "email": u.email, "role": u.role} for u in result.scalars().all()]
    )


@router.get("/patients")
async def patients(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    return ResponseEnvelope(data=await list_patients_admin(db))


@router.get("/doctors")
async def doctors(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    return ResponseEnvelope(data=await list_doctors_admin(db))


@router.delete("/patients/{patient_id}", response_model=ResponseEnvelope[DeleteAccountResponse])
async def remove_patient(patient_id: UUID, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    result = await delete_patient_account(db, patient_id)
    await db.commit()
    return ResponseEnvelope(data=DeleteAccountResponse(**result))


@router.delete("/doctors/{doctor_id}", response_model=ResponseEnvelope[DeleteAccountResponse])
async def remove_doctor(doctor_id: UUID, db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    result = await delete_doctor_account(db, doctor_id)
    await db.commit()
    return ResponseEnvelope(data=DeleteAccountResponse(**result))


@router.post("/reset-data", response_model=ResponseEnvelope[ResetDataResponse])
async def reset_data(
    data: ResetDataRequest,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    if data.mode == "all_data":
        summary = await truncate_all_data(db)
        message = "All patient and doctor accounts removed. Default doctor catalog re-seeded."
    else:
        summary = await truncate_keep_doctors(db)
        message = "Patient data cleared. Doctor catalog preserved."
    await db.commit()
    return ResponseEnvelope(
        data=ResetDataResponse(
            **summary,
            message=message,
        )
    )


@router.get("/audit-logs")
async def audit_logs(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    result = await db.execute(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(100))
    return ResponseEnvelope(
        data=[
            {"action": a.action, "status": a.status_code, "at": str(a.created_at)}
            for a in result.scalars().all()
        ]
    )


@router.get("/analytics/overview")
async def analytics(db: AsyncSession = Depends(get_db), _=Depends(require_admin)):
    users = await db.execute(select(func.count()).select_from(User))
    patients = await db.execute(select(func.count()).select_from(User).where(User.role == "patient"))
    doctors = await db.execute(select(func.count()).select_from(User).where(User.role == "doctor"))
    appts = await db.execute(select(func.count()).select_from(Appointment))
    chats = await db.execute(select(func.count()).select_from(Conversation))
    triage = await db.execute(select(func.count()).select_from(SymptomAssessment))
    return ResponseEnvelope(
        data={
            "total_users": users.scalar() or 0,
            "total_patients": patients.scalar() or 0,
            "total_doctors": doctors.scalar() or 0,
            "total_appointments": appts.scalar() or 0,
            "total_conversations": chats.scalar() or 0,
            "total_assessments": triage.scalar() or 0,
        }
    )
