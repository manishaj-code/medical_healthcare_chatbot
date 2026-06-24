"""Clinical consultation workflow — prep, draft, complete, patient records (all visit modes)."""
from __future__ import annotations

import re
from datetime import date, datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import (
    Appointment,
    Consultation,
    Doctor,
    DoctorNote,
    LabOrder,
    Medication,
    Patient,
    PatientSummary,
    Prescription,
    PrescriptionItem,
    User,
)
from app.models.enums import AppointmentStatus, NotificationType
from app.models.system import Notification
from app.schemas.consultation import CompleteConsultationIn, ConsultationDraftIn
from app.services.appointment_service import format_apt_id
from app.services.pre_visit_intake_service import ensure_consultation_intake
from app.services.lab_catalog_service import list_active_lab_catalog
from app.services.appointment_service import appointment_supports_video_call
from app.services.video_consultation_service import video_room_id_for_appointment


async def _get_appointment_for_doctor(
    db: AsyncSession, appointment_id: UUID, doctor_id: UUID
) -> Appointment:
    appt = await db.get(Appointment, appointment_id)
    if not appt or appt.doctor_id != doctor_id:
        raise HTTPException(status_code=404, detail="Appointment not found")
    return appt


async def _get_or_create_consultation(
    db: AsyncSession, appt: Appointment, doctor_id: UUID, *, status: str = "draft"
) -> Consultation:
    result = await db.execute(
        select(Consultation).where(Consultation.appointment_id == appt.id)
    )
    row = result.scalar_one_or_none()
    if row:
        return row
    row = Consultation(
        appointment_id=appt.id,
        patient_id=appt.patient_id,
        doctor_id=doctor_id,
        status=status,
        consultation_mode=appt.consultation_mode or "in_person",
    )
    db.add(row)
    await db.flush()
    return row


_PREVISIT_STRUCTURED_RE = re.compile(
    r"(?:^|\n)"
    r"(?:Presenting symptoms|Duration|Medical history|Current medications|Known allergies):\s*"
    r"[^\n]+",
    re.IGNORECASE,
)

_PREVISIT_NARRATIVE_RE = re.compile(
    r"The patient (?:presents with|has no known|is recommended to)[^.!?\n]+[.!?]\s*",
    re.IGNORECASE,
)


def clean_clinical_findings_for_record(
    findings: str | None,
    *,
    recommendation_text: str | None = None,
) -> str | None:
    """Remove pre-consultation triage/self-care text from examination findings."""
    if not findings or not findings.strip():
        return findings

    text = findings.strip()
    rec = (recommendation_text or "").strip()
    if rec:
        text = text.replace(rec, "").strip()
        for sentence in re.split(r"(?<=[.!?])\s+", rec):
            part = sentence.strip()
            if len(part) > 12:
                text = text.replace(part, "").strip()

    text = _PREVISIT_STRUCTURED_RE.sub("", text).strip()
    text = _PREVISIT_NARRATIVE_RE.sub("", text).strip()
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text or None


def _appointment_is_today(appt: Appointment) -> bool:
    return appt.slot_date == date.today()


def _can_start_consultation(appt: Appointment) -> bool:
    return (
        appt.status in (AppointmentStatus.confirmed, AppointmentStatus.pending)
        and _appointment_is_today(appt)
    )


async def get_consultation_prep(
    db: AsyncSession, appointment_id: UUID, doctor_id: UUID
) -> dict:
    appt = await _get_appointment_for_doctor(db, appointment_id, doctor_id)
    patient = await db.get(Patient, appt.patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    user = await db.get(User, patient.user_id)
    intake = await ensure_consultation_intake(db, patient, appt.id)
    consultation = await _get_or_create_consultation(db, appt, doctor_id)

    doctor_user = await db.execute(
        select(User.name).join(Doctor, Doctor.user_id == User.id).where(Doctor.id == doctor_id)
    )
    doctor_name = doctor_user.scalar_one_or_none() or "Doctor"

    structured = intake.structured_intake or {}
    consultation_mode = appt.consultation_mode or "in_person"
    video_available = appointment_supports_video_call(appt)
    video_room_id = appt.video_room_id or video_room_id_for_appointment(appt.id)
    from app.services.consultation_transcript_service import get_transcript_prep_payload

    transcript = await get_transcript_prep_payload(db, consultation.id)
    return {
        "appointment": {
            "appointment_id": str(appt.id),
            "apt_id": format_apt_id(appt.id),
            "date": str(appt.slot_date),
            "time": str(appt.slot_time),
            "status": appt.status.value if hasattr(appt.status, "value") else str(appt.status),
            "consultation_mode": consultation_mode,
            "is_video": video_available,
            "video_room_id": video_room_id if video_available else appt.video_room_id,
            "appointment_reason": appt.appointment_reason,
        },
        "patient": {
            "patient_id": str(patient.id),
            "name": user.name if user else "Patient",
            "dob": str(patient.dob) if patient.dob else None,
            "gender": patient.gender,
            "blood_group": patient.blood_group,
        },
        "doctor_name": doctor_name,
        "visit_type": structured.get("visit_type") or ("report_discussion" if appt.linked_report_id else "symptom"),
        "appointment_reason": appt.appointment_reason,
        "linked_report": structured.get("linked_report"),
        "ai_risk_level": intake.ai_risk_level,
        "ai_summary": structured,
        "consultation": await serialize_consultation(db, consultation),
        "lab_catalog": await list_active_lab_catalog(db),
        "can_start": _can_start_consultation(appt),
        "is_completed": appt.status == AppointmentStatus.completed,
        "transcript": transcript,
    }


async def start_consultation(db: AsyncSession, appointment_id: UUID, doctor_id: UUID) -> dict:
    appt = await _get_appointment_for_doctor(db, appointment_id, doctor_id)
    if appt.status == AppointmentStatus.completed:
        raise HTTPException(status_code=400, detail="Appointment already completed")
    if appt.status == AppointmentStatus.cancelled:
        raise HTTPException(status_code=400, detail="Appointment is cancelled")
    if not _appointment_is_today(appt):
        raise HTTPException(
            status_code=400,
            detail="Consultations can only be started on the appointment day",
        )

    patient = await db.get(Patient, appt.patient_id)
    if patient:
        intake = await ensure_consultation_intake(db, patient, appt.id)
        structured = intake.structured_intake or {}
    else:
        structured = {}

    consultation = await _get_or_create_consultation(db, appt, doctor_id, status="in_progress")
    consultation.status = "in_progress"
    if not consultation.chief_complaint and structured.get("chief_complaint"):
        consultation.chief_complaint = structured["chief_complaint"]
    await db.flush()
    return await serialize_consultation(db, consultation)


async def save_consultation_draft(
    db: AsyncSession,
    appointment_id: UUID,
    doctor_id: UUID,
    data: ConsultationDraftIn,
) -> dict:
    appt = await _get_appointment_for_doctor(db, appointment_id, doctor_id)
    if appt.status == AppointmentStatus.completed:
        raise HTTPException(status_code=400, detail="Consultation already completed")

    consultation = await _get_or_create_consultation(db, appt, doctor_id)
    _apply_draft_fields(consultation, data)
    if consultation.status != "completed":
        consultation.status = "draft" if consultation.status == "draft" else "in_progress"

    await _replace_prescription_and_labs(db, consultation, data)
    await db.flush()
    return await serialize_consultation(db, consultation)


def _apply_draft_fields(consultation: Consultation, data: ConsultationDraftIn) -> None:
    consultation.chief_complaint = data.chief_complaint
    consultation.clinical_findings = data.clinical_findings
    consultation.diagnosis = data.diagnosis
    consultation.doctor_notes = data.doctor_notes
    consultation.treatment_plan = data.treatment_plan
    consultation.follow_up_date = data.follow_up_date


async def _replace_prescription_and_labs(
    db: AsyncSession, consultation: Consultation, data: ConsultationDraftIn
) -> None:
    existing_rx = await db.execute(
        select(Prescription).where(Prescription.consultation_id == consultation.id)
    )
    for rx in existing_rx.scalars().all():
        items = await db.execute(
            select(PrescriptionItem).where(PrescriptionItem.prescription_id == rx.id)
        )
        for item in items.scalars().all():
            await db.delete(item)
        await db.delete(rx)

    existing_labs = await db.execute(
        select(LabOrder).where(LabOrder.consultation_id == consultation.id)
    )
    for lab in existing_labs.scalars().all():
        await db.delete(lab)

    if data.prescription_items:
        rx = Prescription(
            consultation_id=consultation.id,
            doctor_id=consultation.doctor_id,
            patient_id=consultation.patient_id,
        )
        db.add(rx)
        await db.flush()
        for i, item in enumerate(data.prescription_items):
            db.add(
                PrescriptionItem(
                    prescription_id=rx.id,
                    medicine_name=item.medicine_name,
                    strength=item.strength,
                    frequency=item.frequency,
                    duration=item.duration,
                    instructions=item.instructions,
                    sort_order=i,
                    source=item.source or "manual",
                )
            )

    for lab in data.lab_orders:
        db.add(
            LabOrder(
                consultation_id=consultation.id,
                test_code=lab.test_code,
                test_name=lab.test_name,
                notes=lab.notes,
            )
        )


async def complete_consultation(
    db: AsyncSession,
    appointment_id: UUID,
    doctor_id: UUID,
    data: CompleteConsultationIn,
) -> dict:
    appt = await _get_appointment_for_doctor(db, appointment_id, doctor_id)
    if appt.status == AppointmentStatus.completed:
        raise HTTPException(status_code=400, detail="Appointment already completed")

    if not (data.diagnosis or data.treatment_plan):
        raise HTTPException(
            status_code=422,
            detail="Diagnosis or treatment plan is required to complete consultation",
        )

    consultation = await _get_or_create_consultation(db, appt, doctor_id)
    _apply_draft_fields(consultation, data)
    await _replace_prescription_and_labs(db, consultation, data)

    patient = await db.get(Patient, appt.patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    intake_row = await ensure_consultation_intake(db, patient, appt.id)
    intake = intake_row.structured_intake or {}
    consultation.clinical_findings = clean_clinical_findings_for_record(
        consultation.clinical_findings,
        recommendation_text=intake.get("recommendation_text"),
    )
    consultation.ai_summary_snapshot = intake

    now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
    consultation.status = "completed"
    consultation.completed_at = now_naive
    consultation.doctor_signature_json = {
        "name": data.doctor_signature_name,
        "signed_at": datetime.now(timezone.utc).isoformat(),
    }

    appt.status = AppointmentStatus.completed
    appt.completed_at = now_naive

    note = await db.execute(
        select(DoctorNote).where(DoctorNote.appointment_id == appt.id).limit(1)
    )
    soap = note.scalar_one_or_none()
    if not soap:
        soap = DoctorNote(
            doctor_id=doctor_id,
            patient_id=appt.patient_id,
            appointment_id=appt.id,
        )
        db.add(soap)
    soap.subjective = data.chief_complaint
    soap.objective = consultation.clinical_findings
    soap.assessment = data.diagnosis
    soap.plan = data.treatment_plan
    soap.private_notes = data.doctor_notes

    summary_text = _build_patient_summary_text(consultation, data)
    db.add(
        PatientSummary(
            patient_id=appt.patient_id,
            appointment_id=appt.id,
            summary_text=summary_text,
        )
    )

    await _sync_medications_from_prescription(db, appt.patient_id, data.prescription_items)

    from app.services.consultation_transcript_service import stop_transcript_for_consultation

    await stop_transcript_for_consultation(db, consultation.id)

    db.add(
        Notification(
            user_id=patient.user_id,
            type=NotificationType.consultation_completed,
            message=(
                "Your consultation with your doctor has been completed. "
                "View your health records for diagnosis, prescription, and follow-up details."
            ),
        )
    )

    await db.flush()
    from app.services.appointment_card_service import sync_appointment_status_on_patient_cards

    await sync_appointment_status_on_patient_cards(db, appointment_id)
    return {
        "status": "completed",
        "appointment_id": str(appointment_id),
        "apt_id": format_apt_id(appt.id),
        "consultation": await serialize_consultation(db, consultation),
    }


def _build_patient_summary_text(consultation: Consultation, data: CompleteConsultationIn) -> str:
    lines = [
        f"Chief complaint: {data.chief_complaint or '—'}",
        f"Diagnosis: {data.diagnosis or '—'}",
        f"Treatment plan: {data.treatment_plan or '—'}",
    ]
    if data.prescription_items:
        meds = ", ".join(p.medicine_name for p in data.prescription_items)
        lines.append(f"Prescribed: {meds}")
    if data.follow_up_date:
        lines.append(f"Follow-up: {data.follow_up_date}")
    return "\n".join(lines)


async def _sync_medications_from_prescription(
    db: AsyncSession, patient_id: UUID, items: list
) -> None:
    for item in items:
        name = item.medicine_name.strip()
        if not name:
            continue
        existing = await db.execute(
            select(Medication).where(
                Medication.patient_id == patient_id,
                Medication.name.ilike(name),
                Medication.is_active.is_(True),
            )
        )
        if existing.scalar_one_or_none():
            continue
        db.add(
            Medication(
                patient_id=patient_id,
                name=name,
                dosage=item.strength,
                frequency=item.frequency,
                is_active=True,
            )
        )


async def serialize_consultation(db: AsyncSession, consultation: Consultation) -> dict:
    items: list[dict] = []
    labs: list[dict] = []

    rx_rows = await db.execute(
        select(Prescription).where(Prescription.consultation_id == consultation.id)
    )
    for rx in rx_rows.scalars().all():
        item_rows = await db.execute(
            select(PrescriptionItem)
            .where(PrescriptionItem.prescription_id == rx.id)
            .order_by(PrescriptionItem.sort_order)
        )
        for it in item_rows.scalars().all():
            items.append({
                "id": str(it.id),
                "medicine_name": it.medicine_name,
                "strength": it.strength,
                "frequency": it.frequency,
                "duration": it.duration,
                "instructions": it.instructions,
                "source": it.source,
            })

    lab_rows = await db.execute(
        select(LabOrder).where(LabOrder.consultation_id == consultation.id)
    )
    for lab in lab_rows.scalars().all():
        labs.append({
            "id": str(lab.id),
            "test_code": lab.test_code,
            "test_name": lab.test_name,
            "notes": lab.notes,
            "status": lab.status,
        })

    return {
        "id": str(consultation.id),
        "appointment_id": str(consultation.appointment_id),
        "patient_id": str(consultation.patient_id),
        "doctor_id": str(consultation.doctor_id),
        "status": consultation.status,
        "consultation_mode": consultation.consultation_mode,
        "chief_complaint": consultation.chief_complaint,
        "clinical_findings": consultation.clinical_findings,
        "diagnosis": consultation.diagnosis,
        "doctor_notes": consultation.doctor_notes,
        "treatment_plan": consultation.treatment_plan,
        "follow_up_date": str(consultation.follow_up_date) if consultation.follow_up_date else None,
        "completed_at": consultation.completed_at.isoformat() if consultation.completed_at else None,
        "prescription_items": items,
        "lab_orders": labs,
    }


async def list_patient_consultations(db: AsyncSession, patient_id: UUID) -> list[dict]:
    rows = await db.execute(
        select(Consultation, Appointment, User.name)
        .join(Appointment, Appointment.id == Consultation.appointment_id)
        .join(Doctor, Doctor.id == Consultation.doctor_id)
        .join(User, User.id == Doctor.user_id)
        .where(
            Consultation.patient_id == patient_id,
            Consultation.status == "completed",
        )
        .order_by(Consultation.completed_at.desc())
    )
    out = []
    for consultation, appt, doctor_name in rows.all():
        serialized = await serialize_consultation(db, consultation)
        out.append({
            **serialized,
            "appointment_date": str(appt.slot_date),
            "appointment_time": str(appt.slot_time),
            "doctor_name": doctor_name,
            "apt_id": format_apt_id(appt.id),
        })
    return out


async def get_patient_consultation_detail(
    db: AsyncSession, patient_id: UUID, consultation_id: UUID
) -> dict:
    consultation = await db.get(Consultation, consultation_id)
    if not consultation or consultation.patient_id != patient_id:
        raise HTTPException(status_code=404, detail="Consultation not found")
    if consultation.status != "completed":
        raise HTTPException(status_code=403, detail="Consultation not available yet")

    appt = await db.get(Appointment, consultation.appointment_id)
    doctor_name = "Doctor"
    doc_row = await db.execute(
        select(User.name).join(Doctor, Doctor.user_id == User.id).where(Doctor.id == consultation.doctor_id)
    )
    if doc_row.scalar_one_or_none():
        doctor_name = doc_row.scalar_one()

    data = await serialize_consultation(db, consultation)
    safe = {**data}
    safe.pop("doctor_notes", None)
    return {
        **safe,
        "appointment_date": str(appt.slot_date) if appt else None,
        "appointment_time": str(appt.slot_time) if appt else None,
        "doctor_name": doctor_name,
        "apt_id": format_apt_id(appt.id) if appt else None,
    }
