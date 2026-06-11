import logging
from datetime import date, time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Appointment, Doctor, Notification, Patient, Specialization, User
from app.models.doctor_ops import DoctorSpecialization
from app.models.enums import NotificationType
from app.services.email_service import send_plain_email

logger = logging.getLogger(__name__)


def _format_slot_time(slot_time: time) -> str:
    return slot_time.strftime("%I:%M %p").lstrip("0")


def _format_slot_date(slot_date: date) -> str:
    return slot_date.strftime("%A, %B %d, %Y")


async def _doctor_specialty(db: AsyncSession, doctor_id) -> str | None:
    row = await db.execute(
        select(Specialization.name)
        .join(DoctorSpecialization, DoctorSpecialization.specialization_id == Specialization.id)
        .where(DoctorSpecialization.doctor_id == doctor_id)
        .limit(1)
    )
    return row.scalar_one_or_none()


async def send_appointment_scheduled_emails(db: AsyncSession, appt: Appointment) -> None:
    """Email patient and doctor when an appointment is confirmed."""
    patient_row = await db.execute(
        select(User.name, User.email, User.id)
        .join(Patient, Patient.user_id == User.id)
        .where(Patient.id == appt.patient_id)
    )
    patient = patient_row.one_or_none()
    if not patient:
        logger.warning("Appointment %s: patient user not found for email", appt.id)
        return

    doctor_row = await db.execute(
        select(User.name, User.email, User.id)
        .join(Doctor, Doctor.user_id == User.id)
        .where(Doctor.id == appt.doctor_id)
    )
    doctor = doctor_row.one_or_none()
    if not doctor:
        logger.warning("Appointment %s: doctor user not found for email", appt.id)
        return

    patient_name, patient_email, _patient_user_id = patient
    doctor_name, doctor_email, doctor_user_id = doctor
    specialty = await _doctor_specialty(db, appt.doctor_id)
    apt_id = f"APT-{appt.id.hex[:5].upper()}"
    when_date = _format_slot_date(appt.slot_date)
    when_time = _format_slot_time(appt.slot_time)
    specialty_line = f" ({specialty})" if specialty else ""

    patient_subject = f"Appointment confirmed — {apt_id}"
    patient_body = (
        f"Hello {patient_name},\n\n"
        f"Your appointment has been scheduled.\n\n"
        f"Appointment ID: {apt_id}\n"
        f"Doctor: Dr. {doctor_name}{specialty_line}\n"
        f"Date: {when_date}\n"
        f"Time: {when_time}\n\n"
        "Please arrive a few minutes early. You can view or manage this appointment in your Patient Portal.\n\n"
        "— MediAI Platform"
    )

    doctor_subject = f"New appointment scheduled — {apt_id}"
    doctor_body = (
        f"Hello Dr. {doctor_name},\n\n"
        f"A new appointment has been booked with you.\n\n"
        f"Appointment ID: {apt_id}\n"
        f"Patient: {patient_name}\n"
        f"Date: {when_date}\n"
        f"Time: {when_time}\n\n"
        "Please review the appointment in your doctor portal.\n\n"
        "— MediAI Platform"
    )

    await send_plain_email(patient_email, patient_subject, patient_body)
    await send_plain_email(doctor_email, doctor_subject, doctor_body)

    db.add(
        Notification(
            user_id=doctor_user_id,
            type=NotificationType.booking_confirmation,
            message=(
                f"New appointment {apt_id} with {patient_name} on {appt.slot_date} at {when_time}."
            ),
        )
    )
    await db.flush()
