from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, get_settings, require_admin
from app.models import Appointment, Conversation, SymptomAssessment, User
from app.models.system import AuditLog
from app.schemas.admin import (
    ClearDoctorAppointmentsResponse,
    DeleteAccountResponse,
    EmailStatusResponse,
    EmailTestRequest,
    EmailTestResponse,
    ResetDataRequest,
    ResetDataResponse,
)
from app.schemas.common import ResponseEnvelope
from app.services.email_service import smtp_status
from app.services.otp_service import generate_otp, send_otp_email
from app.services.admin_service import (
    clear_doctor_appointments,
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


@router.delete("/doctors/{doctor_id}/appointments", response_model=ResponseEnvelope[ClearDoctorAppointmentsResponse])
async def remove_doctor_appointments(
    doctor_id: UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_admin),
):
    result = await clear_doctor_appointments(db, doctor_id)
    await db.commit()
    deleted = result["deleted_appointments"]
    freed = result["slots_freed"]
    message = (
        f"Removed {deleted} appointment(s) for {result['doctor_email']}. "
        f"{freed} slot(s) marked available for booking."
        if deleted
        else f"No appointments to remove for {result['doctor_email']}."
    )
    return ResponseEnvelope(data=ClearDoctorAppointmentsResponse(**result, message=message))


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


@router.get("/email/status", response_model=ResponseEnvelope[EmailStatusResponse])
async def email_status(_=Depends(require_admin)):
    status = smtp_status()
    return ResponseEnvelope(
        data=EmailStatusResponse(
            smtp_configured=bool(status["smtp_configured"]),
            smtp_host=str(status["smtp_host"]),
            smtp_port=int(status["smtp_port"]),
            smtp_from=str(status["smtp_from"]),
        )
    )


@router.post("/email/test", response_model=ResponseEnvelope[EmailTestResponse])
async def email_test(data: EmailTestRequest, _=Depends(require_admin)):
    """Send a sample chat verification email using the same SMTP path as guest OTP."""
    otp = generate_otp()
    try:
        result = await send_otp_email(data.email, otp)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"SMTP send failed: {exc}") from exc

    settings = get_settings()
    if result.mode == "smtp":
        message = f"Sample verification email sent to {data.email} via SMTP."
    else:
        message = f"SMTP not configured — sample OTP logged on the server for {data.email}."

    return ResponseEnvelope(
        data=EmailTestResponse(
            message=message,
            mode=result.mode,
            dev_otp=otp if settings.dev_otp or result.mode == "console" else None,
        )
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
