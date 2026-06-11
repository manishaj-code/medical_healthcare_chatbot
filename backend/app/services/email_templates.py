"""HTML email templates for transactional messages."""
import html
from datetime import datetime
from pathlib import Path

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "email_templates"


def _render_template(template_name: str, **values: str) -> str:
    template_path = _TEMPLATES_DIR / template_name
    rendered = template_path.read_text(encoding="utf-8")
    for key, value in values.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", html.escape(value))
    return rendered


def format_otp_display(otp: str) -> str:
    """Format 6-digit OTP as '123 456' for readability."""
    digits = "".join(c for c in otp if c.isdigit())
    if len(digits) == 6:
        return f"{digits[:3]} {digits[3:]}"
    return otp.strip()


def render_otp_verification_email(otp: str, expiry_minutes: int) -> str:
    return _render_template(
        "otp_verification.html",
        otp_display=format_otp_display(otp),
        expiry_minutes=str(expiry_minutes),
        year=str(datetime.now().year),
    )


def render_appointment_patient_email(
    *,
    patient_name: str,
    apt_id: str,
    doctor_display: str,
    when_date: str,
    when_time: str,
) -> str:
    return _render_template(
        "appointment_patient.html",
        patient_name=patient_name,
        apt_id=apt_id,
        doctor_display=doctor_display,
        when_date=when_date,
        when_time=when_time,
        year=str(datetime.now().year),
    )


def render_appointment_doctor_email(
    *,
    doctor_name: str,
    apt_id: str,
    patient_name: str,
    when_date: str,
    when_time: str,
) -> str:
    return _render_template(
        "appointment_doctor.html",
        doctor_name=doctor_name,
        apt_id=apt_id,
        patient_name=patient_name,
        when_date=when_date,
        when_time=when_time,
        year=str(datetime.now().year),
    )


def render_appointment_cancelled_patient_email(
    *,
    patient_name: str,
    apt_id: str,
    doctor_display: str,
    when_date: str,
    when_time: str,
    cancellation_reason: str,
) -> str:
    return _render_template(
        "appointment_cancelled_patient.html",
        patient_name=patient_name,
        apt_id=apt_id,
        doctor_display=doctor_display,
        when_date=when_date,
        when_time=when_time,
        cancellation_reason=cancellation_reason,
        year=str(datetime.now().year),
    )


def render_appointment_cancelled_doctor_email(
    *,
    doctor_name: str,
    apt_id: str,
    patient_name: str,
    when_date: str,
    when_time: str,
    cancellation_reason: str,
) -> str:
    return _render_template(
        "appointment_cancelled_doctor.html",
        doctor_name=doctor_name,
        apt_id=apt_id,
        patient_name=patient_name,
        when_date=when_date,
        when_time=when_time,
        cancellation_reason=cancellation_reason,
        year=str(datetime.now().year),
    )


def render_appointment_rescheduled_patient_email(
    *,
    patient_name: str,
    apt_id: str,
    doctor_display: str,
    when_date: str,
    when_time: str,
    previous_when: str,
) -> str:
    return _render_template(
        "appointment_rescheduled_patient.html",
        patient_name=patient_name,
        apt_id=apt_id,
        doctor_display=doctor_display,
        when_date=when_date,
        when_time=when_time,
        previous_when=previous_when,
        year=str(datetime.now().year),
    )


def render_appointment_rescheduled_doctor_email(
    *,
    doctor_name: str,
    apt_id: str,
    patient_name: str,
    when_date: str,
    when_time: str,
    previous_when: str,
) -> str:
    return _render_template(
        "appointment_rescheduled_doctor.html",
        doctor_name=doctor_name,
        apt_id=apt_id,
        patient_name=patient_name,
        when_date=when_date,
        when_time=when_time,
        previous_when=previous_when,
        year=str(datetime.now().year),
    )
