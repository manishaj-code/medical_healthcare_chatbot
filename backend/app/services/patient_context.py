"""Load live patient profile for dynamic agent context."""
from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Allergy,
    Appointment,
    ConversationMemory,
    Doctor,
    MedicalHistory,
    Medication,
    Patient,
    User,
)
from app.models.enums import AppointmentStatus
from app.healthcare_policy import patient_first_name
from app.services.appointment_service import format_apt_id


async def resolve_patient_first_name(
    db: AsyncSession,
    patient_ctx: dict | None,
    patient: Patient | None = None,
) -> str:
    """First name for chat replies — falls back to User.name when context is empty."""
    raw = ((patient_ctx or {}).get("name") or "").strip()
    pname = patient_first_name(raw)
    if pname != "there":
        return pname
    if patient is not None:
        user = await db.get(User, patient.user_id)
        if user and (user.name or "").strip():
            return patient_first_name(user.name)
    return "there"


def _age(dob: date | None) -> int | None:
    if not dob:
        return None
    today = date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def _format_appt(db_row: tuple[Appointment, str]) -> dict:
    appt, doctor_name = db_row
    h = appt.slot_time.hour % 12 or 12
    ampm = "AM" if appt.slot_time.hour < 12 else "PM"
    status = appt.status.value if hasattr(appt.status, "value") else str(appt.status)
    return {
        "id": str(appt.id),
        "apt_id": format_apt_id(appt.id),
        "doctor_name": doctor_name,
        "date": str(appt.slot_date),
        "time": f"{h}:{appt.slot_time.minute:02d} {ampm}",
        "status": status,
    }


async def load_patient_context(db: AsyncSession, patient: Patient) -> dict:
    user = await db.get(User, patient.user_id)
    history = await db.execute(select(MedicalHistory).where(MedicalHistory.patient_id == patient.id))
    meds = await db.execute(
        select(Medication).where(Medication.patient_id == patient.id, Medication.is_active.is_(True))
    )
    allergies = await db.execute(select(Allergy).where(Allergy.patient_id == patient.id))

    appt_rows = await db.execute(
        select(Appointment, User.name)
        .join(Doctor, Doctor.id == Appointment.doctor_id)
        .join(User, User.id == Doctor.user_id)
        .where(
            Appointment.patient_id == patient.id,
            Appointment.status.in_([AppointmentStatus.confirmed, AppointmentStatus.pending]),
        )
        .order_by(Appointment.slot_date, Appointment.slot_time)
    )
    active_appts = [_format_appt(row) for row in appt_rows.all()]

    past_rows = await db.execute(
        select(Appointment, User.name)
        .join(Doctor, Doctor.id == Appointment.doctor_id)
        .join(User, User.id == Doctor.user_id)
        .where(
            Appointment.patient_id == patient.id,
            Appointment.status == AppointmentStatus.completed,
        )
        .order_by(Appointment.completed_at.desc())
        .limit(3)
    )
    past_visits = [_format_appt(row) for row in past_rows.all()]

    mem_rows = await db.execute(
        select(ConversationMemory)
        .where(ConversationMemory.patient_id == patient.id)
        .order_by(ConversationMemory.created_at.desc())
        .limit(12)
    )
    memory_facts = [m.fact for m in mem_rows.scalars().all()]

    return {
        "patient_id": str(patient.id),
        "name": (user.name or "").strip() if user else "",
        "age": _age(patient.dob),
        "gender": patient.gender,
        "blood_group": patient.blood_group,
        "conditions": [h.condition for h in history.scalars().all()],
        "medications": [
            {"name": m.name, "dosage": m.dosage, "frequency": m.frequency} for m in meds.scalars().all()
        ],
        "allergies": [a.allergen for a in allergies.scalars().all()],
        "active_appointments": active_appts,
        "recent_visits": past_visits,
        "memory_facts": memory_facts,
    }
