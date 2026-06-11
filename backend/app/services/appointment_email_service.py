import logging
from dataclasses import dataclass
from datetime import date, time
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Appointment, Doctor, Notification, Patient, Specialization, User
from app.models.doctor_ops import DoctorSpecialization
from app.models.enums import NotificationType
from app.services.email_service import send_email
from app.services.email_templates import (
    render_appointment_cancelled_doctor_email,
    render_appointment_cancelled_patient_email,
    render_appointment_doctor_email,
    render_appointment_patient_email,
    render_appointment_rescheduled_doctor_email,
    render_appointment_rescheduled_patient_email,
)

logger = logging.getLogger(__name__)


def _format_doctor_name(name: str) -> str:
    raw = (name or "").strip()
    if not raw:
        return "Doctor"
    lowered = raw.lower()
    if lowered.startswith("dr.") or lowered.startswith("dr "):
        return raw
    return f"Dr. {raw}"


def _format_slot_time(slot_time: time) -> str:
    return slot_time.strftime("%I:%M %p").lstrip("0")


def _format_slot_date(slot_date: date) -> str:
    return slot_date.strftime("%A, %B %d, %Y")


def _format_when(slot_date: date, slot_time: time) -> tuple[str, str]:
    return _format_slot_date(slot_date), _format_slot_time(slot_time)


def _format_previous_when(slot_date: date, slot_time: time) -> str:
    when_date, when_time = _format_when(slot_date, slot_time)
    return f"{when_date} at {when_time}"


def _cancellation_reason_label(reason: str | None) -> str:
    text = (reason or "").strip()
    return text if text else "Not specified"


async def _doctor_specialty(db: AsyncSession, doctor_id) -> str | None:
    row = await db.execute(
        select(Specialization.name)
        .join(DoctorSpecialization, DoctorSpecialization.specialization_id == Specialization.id)
        .where(DoctorSpecialization.doctor_id == doctor_id)
        .limit(1)
    )
    return row.scalar_one_or_none()


@dataclass
class _AppointmentParticipants:
    patient_name: str
    patient_email: str
    patient_user_id: UUID
    doctor_name: str
    doctor_email: str
    doctor_user_id: UUID
    specialty_line: str
    apt_id: str
    when_date: str
    when_time: str
    doctor_display: str


async def _load_participants(db: AsyncSession, appt: Appointment) -> _AppointmentParticipants | None:
    patient_row = await db.execute(
        select(User.name, User.email, User.id)
        .join(Patient, Patient.user_id == User.id)
        .where(Patient.id == appt.patient_id)
    )
    patient = patient_row.one_or_none()
    if not patient:
        logger.warning("Appointment %s: patient user not found for email", appt.id)
        return None

    doctor_row = await db.execute(
        select(User.name, User.email, User.id)
        .join(Doctor, Doctor.user_id == User.id)
        .where(Doctor.id == appt.doctor_id)
    )
    doctor = doctor_row.one_or_none()
    if not doctor:
        logger.warning("Appointment %s: doctor user not found for email", appt.id)
        return None

    patient_name, patient_email, patient_user_id = patient
    doctor_name_raw, doctor_email, doctor_user_id = doctor
    doctor_name = _format_doctor_name(doctor_name_raw)
    specialty = await _doctor_specialty(db, appt.doctor_id)
    specialty_line = f" ({specialty})" if specialty else ""
    when_date, when_time = _format_when(appt.slot_date, appt.slot_time)

    return _AppointmentParticipants(
        patient_name=patient_name,
        patient_email=patient_email,
        patient_user_id=patient_user_id,
        doctor_name=doctor_name,
        doctor_email=doctor_email,
        doctor_user_id=doctor_user_id,
        specialty_line=specialty_line,
        apt_id=f"APT-{appt.id.hex[:5].upper()}",
        when_date=when_date,
        when_time=when_time,
        doctor_display=f"{doctor_name}{specialty_line}",
    )


async def send_appointment_scheduled_emails(db: AsyncSession, appt: Appointment) -> None:
    """Email patient and doctor when an appointment is confirmed."""
    ctx = await _load_participants(db, appt)
    if not ctx:
        return

    patient_subject = f"Appointment confirmed — {ctx.apt_id}"
    patient_body = (
        f"Hello {ctx.patient_name},\n\n"
        f"Your appointment has been scheduled.\n\n"
        f"Appointment ID: {ctx.apt_id}\n"
        f"Doctor: {ctx.doctor_display}\n"
        f"Date: {ctx.when_date}\n"
        f"Time: {ctx.when_time}\n\n"
        "Please arrive a few minutes early. You can view or manage this appointment in your Patient Portal.\n\n"
        "— MediAI Platform"
    )

    doctor_subject = f"New appointment scheduled — {ctx.apt_id}"
    doctor_body = (
        f"Hello {ctx.doctor_name},\n\n"
        f"A new appointment has been booked with you.\n\n"
        f"Appointment ID: {ctx.apt_id}\n"
        f"Patient: {ctx.patient_name}\n"
        f"Date: {ctx.when_date}\n"
        f"Time: {ctx.when_time}\n\n"
        "Please review the appointment in your doctor portal.\n\n"
        "— MediAI Platform"
    )

    patient_html = render_appointment_patient_email(
        patient_name=ctx.patient_name,
        apt_id=ctx.apt_id,
        doctor_display=ctx.doctor_display,
        when_date=ctx.when_date,
        when_time=ctx.when_time,
    )
    doctor_html = render_appointment_doctor_email(
        doctor_name=ctx.doctor_name,
        apt_id=ctx.apt_id,
        patient_name=ctx.patient_name,
        when_date=ctx.when_date,
        when_time=ctx.when_time,
    )

    await send_email(ctx.patient_email, patient_subject, patient_body, html_body=patient_html)
    await send_email(ctx.doctor_email, doctor_subject, doctor_body, html_body=doctor_html)

    db.add(
        Notification(
            user_id=ctx.doctor_user_id,
            type=NotificationType.booking_confirmation,
            message=(
                f"New appointment {ctx.apt_id} with {ctx.patient_name} on {appt.slot_date} at {ctx.when_time}."
            ),
        )
    )
    await db.flush()


async def send_appointment_cancelled_emails(
    db: AsyncSession,
    appt: Appointment,
    *,
    slot_date: date,
    slot_time: time,
    reason: str | None = None,
) -> None:
    """Email patient and doctor when an appointment is cancelled."""
    ctx = await _load_participants(db, appt)
    if not ctx:
        return

    when_date, when_time = _format_when(slot_date, slot_time)
    reason_label = _cancellation_reason_label(reason)

    patient_subject = f"Appointment cancelled — {ctx.apt_id}"
    patient_body = (
        f"Hello {ctx.patient_name},\n\n"
        f"Your appointment has been cancelled.\n\n"
        f"Appointment ID: {ctx.apt_id}\n"
        f"Doctor: {ctx.doctor_display}\n"
        f"Date: {when_date}\n"
        f"Time: {when_time}\n"
        f"Reason: {reason_label}\n\n"
        "You can book a new appointment from your Patient Portal.\n\n"
        "— MediAI Platform"
    )

    doctor_subject = f"Appointment cancelled — {ctx.apt_id}"
    doctor_body = (
        f"Hello {ctx.doctor_name},\n\n"
        f"An appointment has been cancelled.\n\n"
        f"Appointment ID: {ctx.apt_id}\n"
        f"Patient: {ctx.patient_name}\n"
        f"Date: {when_date}\n"
        f"Time: {when_time}\n"
        f"Reason: {reason_label}\n\n"
        "The time slot is now available in your doctor portal.\n\n"
        "— MediAI Platform"
    )

    patient_html = render_appointment_cancelled_patient_email(
        patient_name=ctx.patient_name,
        apt_id=ctx.apt_id,
        doctor_display=ctx.doctor_display,
        when_date=when_date,
        when_time=when_time,
        cancellation_reason=reason_label,
    )
    doctor_html = render_appointment_cancelled_doctor_email(
        doctor_name=ctx.doctor_name,
        apt_id=ctx.apt_id,
        patient_name=ctx.patient_name,
        when_date=when_date,
        when_time=when_time,
        cancellation_reason=reason_label,
    )

    await send_email(ctx.patient_email, patient_subject, patient_body, html_body=patient_html)
    await send_email(ctx.doctor_email, doctor_subject, doctor_body, html_body=doctor_html)

    db.add(
        Notification(
            user_id=ctx.doctor_user_id,
            type=NotificationType.cancellation,
            message=(
                f"Appointment {ctx.apt_id} with {ctx.patient_name} on {slot_date} at {when_time} was cancelled."
            ),
        )
    )
    db.add(
        Notification(
            user_id=ctx.patient_user_id,
            type=NotificationType.cancellation,
            message=f"Your appointment {ctx.apt_id} on {slot_date} at {when_time} was cancelled.",
        )
    )
    await db.flush()


async def send_appointment_rescheduled_emails(
    db: AsyncSession,
    appt: Appointment,
    *,
    previous_date: date,
    previous_time: time,
) -> None:
    """Email patient and doctor when an appointment is rescheduled."""
    ctx = await _load_participants(db, appt)
    if not ctx:
        return

    previous_when = _format_previous_when(previous_date, previous_time)

    patient_subject = f"Appointment rescheduled — {ctx.apt_id}"
    patient_body = (
        f"Hello {ctx.patient_name},\n\n"
        f"Your appointment has been rescheduled.\n\n"
        f"Appointment ID: {ctx.apt_id}\n"
        f"Doctor: {ctx.doctor_display}\n"
        f"Previous: {previous_when}\n"
        f"New date: {ctx.when_date}\n"
        f"New time: {ctx.when_time}\n\n"
        "Please arrive a few minutes early. You can view this appointment in your Patient Portal.\n\n"
        "— MediAI Platform"
    )

    doctor_subject = f"Appointment rescheduled — {ctx.apt_id}"
    doctor_body = (
        f"Hello {ctx.doctor_name},\n\n"
        f"An appointment has been rescheduled.\n\n"
        f"Appointment ID: {ctx.apt_id}\n"
        f"Patient: {ctx.patient_name}\n"
        f"Previous: {previous_when}\n"
        f"New date: {ctx.when_date}\n"
        f"New time: {ctx.when_time}\n\n"
        "Please review the updated schedule in your doctor portal.\n\n"
        "— MediAI Platform"
    )

    patient_html = render_appointment_rescheduled_patient_email(
        patient_name=ctx.patient_name,
        apt_id=ctx.apt_id,
        doctor_display=ctx.doctor_display,
        when_date=ctx.when_date,
        when_time=ctx.when_time,
        previous_when=previous_when,
    )
    doctor_html = render_appointment_rescheduled_doctor_email(
        doctor_name=ctx.doctor_name,
        apt_id=ctx.apt_id,
        patient_name=ctx.patient_name,
        when_date=ctx.when_date,
        when_time=ctx.when_time,
        previous_when=previous_when,
    )

    await send_email(ctx.patient_email, patient_subject, patient_body, html_body=patient_html)
    await send_email(ctx.doctor_email, doctor_subject, doctor_body, html_body=doctor_html)

    db.add(
        Notification(
            user_id=ctx.doctor_user_id,
            type=NotificationType.booking_confirmation,
            message=(
                f"Appointment {ctx.apt_id} with {ctx.patient_name} rescheduled to "
                f"{appt.slot_date} at {ctx.when_time} (was {previous_date} at {previous_time})."
            ),
        )
    )
    db.add(
        Notification(
            user_id=ctx.patient_user_id,
            type=NotificationType.booking_confirmation,
            message=(
                f"Your appointment {ctx.apt_id} was rescheduled to {ctx.when_date} at {ctx.when_time}."
            ),
        )
    )
    await db.flush()
