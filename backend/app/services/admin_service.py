from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import hash_password
from app.models import (
    Allergy,
    Appointment,
    AppointmentReminder,
    Conversation,
    ConversationMemory,
    Doctor,
    DoctorAvailability,
    DoctorNote,
    DoctorSpecialization,
    MedicalHistory,
    Medication,
    Message,
    Notification,
    Patient,
    PatientSummary,
    RefreshToken,
    Report,
    Specialization,
    SymptomAssessment,
    User,
)
from app.models.enums import UserRole
from app.services.doctor_seed_service import seed_doctor_catalog

OPERATIONAL_TRUNCATE_SQL = """
TRUNCATE TABLE
    messages,
    symptom_assessments,
    conversation_memory,
    conversations,
    patient_summaries,
    doctor_notes,
    reports,
    appointments,
    allergies,
    medications,
    medical_history,
    patients,
    refresh_tokens,
    notifications,
    audit_logs
RESTART IDENTITY CASCADE
"""


async def _truncate_operational_tables(db: AsyncSession) -> None:
    await db.execute(text(OPERATIONAL_TRUNCATE_SQL))


async def _ensure_seed_doctors(db: AsyncSession) -> int:
    added, _updated, _removed = await seed_doctor_catalog(db)
    return added


async def truncate_keep_doctors(db: AsyncSession) -> dict:
    await _truncate_operational_tables(db)
    result = await db.execute(
        delete(User).where(User.role != UserRole.doctor.value).returning(User.id)
    )
    removed_users = len(result.fetchall())

    doctor_count = len((await db.execute(select(Doctor.id))).scalars().all())
    added_doctors = 0
    if not doctor_count:
        added_doctors = await _ensure_seed_doctors(db)

    return {
        "mode": "keep_doctors",
        "removed_users": removed_users,
        "doctors_in_catalog": doctor_count + added_doctors,
        "doctors_reseeded": added_doctors,
    }


async def truncate_all_data(db: AsyncSession) -> dict:
    await _truncate_operational_tables(db)
    await db.execute(delete(DoctorAvailability))
    await db.execute(delete(DoctorSpecialization))
    await db.execute(delete(Doctor))
    result = await db.execute(
        delete(User).where(User.role.in_([UserRole.patient.value, UserRole.doctor.value])).returning(User.id)
    )
    removed_users = len(result.fetchall())
    added_doctors = await _ensure_seed_doctors(db)
    return {
        "mode": "all_data",
        "removed_users": removed_users,
        "doctors_in_catalog": added_doctors,
        "doctors_reseeded": added_doctors,
    }


async def _delete_user_tokens(db: AsyncSession, user_id: UUID) -> None:
    await db.execute(delete(RefreshToken).where(RefreshToken.user_id == user_id))
    await db.execute(delete(Notification).where(Notification.user_id == user_id))


async def _delete_patient_records(db: AsyncSession, patient_id: UUID) -> None:
    conv_ids = (
        await db.execute(select(Conversation.id).where(Conversation.patient_id == patient_id))
    ).scalars().all()
    if conv_ids:
        await db.execute(delete(Message).where(Message.conversation_id.in_(conv_ids)))
    await db.execute(delete(Conversation).where(Conversation.patient_id == patient_id))
    await db.execute(delete(ConversationMemory).where(ConversationMemory.patient_id == patient_id))
    await db.execute(delete(SymptomAssessment).where(SymptomAssessment.patient_id == patient_id))
    await db.execute(delete(Report).where(Report.patient_id == patient_id))
    await db.execute(delete(PatientSummary).where(PatientSummary.patient_id == patient_id))
    await db.execute(delete(DoctorNote).where(DoctorNote.patient_id == patient_id))
    await db.execute(delete(Appointment).where(Appointment.patient_id == patient_id))
    await db.execute(delete(Allergy).where(Allergy.patient_id == patient_id))
    await db.execute(delete(Medication).where(Medication.patient_id == patient_id))
    from app.models import RefillRequest

    await db.execute(delete(RefillRequest).where(RefillRequest.patient_id == patient_id))
    await db.execute(delete(MedicalHistory).where(MedicalHistory.patient_id == patient_id))


async def delete_patient_account(db: AsyncSession, patient_id: UUID) -> dict:
    patient = await db.get(Patient, patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    user = await db.get(User, patient.user_id)
    if not user or user.role != UserRole.patient.value:
        raise HTTPException(status_code=400, detail="Account is not a patient")

    await _delete_patient_records(db, patient_id)
    await db.delete(patient)
    await _delete_user_tokens(db, user.id)
    await db.delete(user)
    await db.flush()
    return {"deleted_patient_id": str(patient_id), "email": user.email}


async def delete_doctor_account(db: AsyncSession, doctor_id: UUID) -> dict:
    doctor = await db.get(Doctor, doctor_id)
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")

    user = await db.get(User, doctor.user_id)
    if not user or user.role != UserRole.doctor.value:
        raise HTTPException(status_code=400, detail="Account is not a doctor")

    appt_ids = (
        await db.execute(select(Appointment.id).where(Appointment.doctor_id == doctor_id))
    ).scalars().all()
    if appt_ids:
        await db.execute(delete(AppointmentReminder).where(AppointmentReminder.appointment_id.in_(appt_ids)))
        await db.execute(delete(PatientSummary).where(PatientSummary.appointment_id.in_(appt_ids)))
        await db.execute(delete(DoctorNote).where(DoctorNote.appointment_id.in_(appt_ids)))
    await db.execute(delete(DoctorNote).where(DoctorNote.doctor_id == doctor_id))
    await db.execute(delete(Appointment).where(Appointment.doctor_id == doctor_id))
    await db.execute(delete(DoctorAvailability).where(DoctorAvailability.doctor_id == doctor_id))
    await db.execute(delete(DoctorSpecialization).where(DoctorSpecialization.doctor_id == doctor_id))
    await db.delete(doctor)
    await _delete_user_tokens(db, user.id)
    await db.delete(user)
    await db.flush()
    return {"deleted_doctor_id": str(doctor_id), "email": user.email}


async def list_patients_admin(db: AsyncSession) -> list[dict]:
    rows = (
        await db.execute(
            select(Patient, User)
            .join(User, Patient.user_id == User.id)
            .where(User.role == UserRole.patient.value)
            .order_by(User.created_at.desc())
        )
    ).all()

    appt_map = dict(
        (await db.execute(select(Appointment.patient_id, func.count()).group_by(Appointment.patient_id))).all()
    )
    report_map = dict(
        (await db.execute(select(Report.patient_id, func.count()).group_by(Report.patient_id))).all()
    )
    chat_map = dict(
        (await db.execute(select(Conversation.patient_id, func.count()).group_by(Conversation.patient_id))).all()
    )

    return [
        {
            "id": str(patient.id),
            "user_id": str(user.id),
            "name": user.name,
            "email": user.email,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "appointments_count": int(appt_map.get(patient.id, 0)),
            "reports_count": int(report_map.get(patient.id, 0)),
            "conversations_count": int(chat_map.get(patient.id, 0)),
        }
        for patient, user in rows
    ]


async def list_doctors_admin(db: AsyncSession) -> list[dict]:
    rows = (
        await db.execute(
            select(Doctor, User)
            .join(User, Doctor.user_id == User.id)
            .where(User.role == UserRole.doctor.value)
            .order_by(User.name)
        )
    ).all()

    spec_rows = (
        await db.execute(
            select(DoctorSpecialization.doctor_id, Specialization.name)
            .join(Specialization, DoctorSpecialization.specialization_id == Specialization.id)
        )
    ).all()
    spec_map = {doctor_id: name for doctor_id, name in spec_rows}

    appt_map = dict(
        (await db.execute(select(Appointment.doctor_id, func.count()).group_by(Appointment.doctor_id))).all()
    )

    return [
        {
            "id": str(doctor.id),
            "user_id": str(user.id),
            "name": user.name,
            "email": user.email,
            "specialty": spec_map.get(doctor.id),
            "experience_years": doctor.experience_years,
            "rating": float(doctor.rating),
            "is_verified": doctor.is_verified,
            "appointments_count": int(appt_map.get(doctor.id, 0)),
        }
        for doctor, user in rows
    ]
