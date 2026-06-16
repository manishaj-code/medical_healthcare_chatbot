"""Per-visit consultation records for the doctor patient chart."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Appointment, DoctorNote, Medication, Patient, PatientSummary, Report, SymptomAssessment, User
from app.services.appointment_service import format_apt_id, is_active_appointment_status, is_slot_past
from app.services.patient_context import load_patient_context
from app.services.symptom_service import assessment_payload_from_row


def _appt_datetime(appt: Appointment) -> datetime:
    return datetime.combine(appt.slot_date, appt.slot_time, tzinfo=timezone.utc)


def _pick_assessment_for_visit(
    appt: Appointment,
    assessments: list[SymptomAssessment],
) -> SymptomAssessment | None:
    if not assessments:
        return None
    anchor = appt.completed_at or _appt_datetime(appt)
    for row in assessments:
        if row.completed_at and row.completed_at <= anchor:
            return row
    return assessments[0]


async def list_visit_records_for_doctor(
    db: AsyncSession,
    doctor_id: UUID,
    patient_id: UUID,
) -> dict:
    patient = await db.get(Patient, patient_id)
    if not patient:
        return {"visits": [], "medications": [], "conditions": [], "allergies": [], "reports": []}

    ctx = await load_patient_context(db, patient)

    appt_rows = await db.execute(
        select(Appointment)
        .where(Appointment.doctor_id == doctor_id, Appointment.patient_id == patient_id)
        .order_by(Appointment.slot_date.desc(), Appointment.slot_time.desc())
    )
    appointments = list(appt_rows.scalars().all())
    appt_ids = [a.id for a in appointments]

    notes_by_appt: dict[str, dict] = {}
    if appt_ids:
        note_rows = await db.execute(
            select(DoctorNote).where(
                DoctorNote.doctor_id == doctor_id,
                DoctorNote.patient_id == patient_id,
                DoctorNote.appointment_id.in_(appt_ids),
            )
        )
        for note in note_rows.scalars().all():
            if note.appointment_id:
                notes_by_appt[str(note.appointment_id)] = {
                    "id": str(note.id),
                    "subjective": note.subjective,
                    "objective": note.objective,
                    "assessment": note.assessment,
                    "plan": note.plan,
                    "created_at": note.created_at.isoformat() if note.created_at else None,
                }

    summaries_by_appt: dict[str, str] = {}
    summary_rows = await db.execute(
        select(PatientSummary)
        .where(PatientSummary.patient_id == patient_id)
        .order_by(PatientSummary.generated_at.desc())
    )
    for summary in summary_rows.scalars().all():
        key = str(summary.appointment_id) if summary.appointment_id else "__latest__"
        if key not in summaries_by_appt:
            summaries_by_appt[key] = summary.summary_text

    assessment_rows = await db.execute(
        select(SymptomAssessment)
        .where(SymptomAssessment.patient_id == patient_id)
        .order_by(SymptomAssessment.completed_at.desc().nullslast())
    )
    assessments = list(assessment_rows.scalars().all())

    report_rows = await db.execute(
        select(Report)
        .where(Report.patient_id == patient_id)
        .order_by(Report.created_at.desc())
    )
    reports = [
        {
            "id": str(r.id),
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "analysis": r.analysis_json,
        }
        for r in report_rows.scalars().all()
    ]

    visits: list[dict] = []
    for appt in appointments:
        appt_key = str(appt.id)
        status = appt.status.value if hasattr(appt.status, "value") else str(appt.status)
        matched = _pick_assessment_for_visit(appt, assessments)
        visits.append({
            "appointment_id": appt_key,
            "apt_id": format_apt_id(appt.id),
            "date": str(appt.slot_date),
            "time": str(appt.slot_time),
            "status": status,
            "completed_at": appt.completed_at.isoformat() if appt.completed_at else None,
            "consultation_mode": appt.consultation_mode or "in_person",
            "is_video": bool(appt.video_room_id),
            "summary": summaries_by_appt.get(appt_key) or (
                summaries_by_appt.get("__latest__") if status == "completed" else None
            ),
            "soap_note": notes_by_appt.get(appt_key),
            "assessment": assessment_payload_from_row(matched) if matched else None,
        })

    return {
        "visits": visits,
        "medications": ctx.get("medications") or [],
        "conditions": ctx.get("conditions") or [],
        "allergies": ctx.get("allergies") or [],
        "reports": reports,
    }


def _summary_excerpt(text: str | None, limit: int = 180) -> str | None:
    if not text or not text.strip():
        return None
    cleaned = " ".join(text.split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"


async def list_consultation_history_for_doctor(
    db: AsyncSession,
    doctor_id: UUID,
    *,
    limit: int = 200,
) -> dict:
    """Cross-patient visit history for the doctor portal — symptoms, meds, and consult notes."""
    result = await db.execute(
        select(Appointment, Patient, User)
        .join(Patient, Appointment.patient_id == Patient.id)
        .join(User, Patient.user_id == User.id)
        .where(Appointment.doctor_id == doctor_id)
        .order_by(Appointment.slot_date.desc(), Appointment.slot_time.desc())
        .limit(limit)
    )
    rows = result.all()
    if not rows:
        return {"records": [], "total": 0}

    patient_ids = list({p.id for _, p, _ in rows})
    appt_ids = [a.id for a, _, _ in rows]

    notes_by_appt: dict[str, DoctorNote] = {}
    if appt_ids:
        note_rows = await db.execute(
            select(DoctorNote).where(
                DoctorNote.doctor_id == doctor_id,
                DoctorNote.appointment_id.in_(appt_ids),
            )
        )
        for note in note_rows.scalars().all():
            if note.appointment_id:
                notes_by_appt[str(note.appointment_id)] = note

    summaries_by_appt: dict[str, str] = {}
    summary_rows = await db.execute(
        select(PatientSummary).where(PatientSummary.patient_id.in_(patient_ids))
        .order_by(PatientSummary.generated_at.desc())
    )
    for summary in summary_rows.scalars().all():
        if summary.appointment_id:
            key = str(summary.appointment_id)
            if key not in summaries_by_appt:
                summaries_by_appt[key] = summary.summary_text

    assessments_by_patient: dict[str, list[SymptomAssessment]] = {}
    assessment_rows = await db.execute(
        select(SymptomAssessment)
        .where(SymptomAssessment.patient_id.in_(patient_ids))
        .order_by(SymptomAssessment.completed_at.desc().nullslast())
    )
    for assessment in assessment_rows.scalars().all():
        assessments_by_patient.setdefault(str(assessment.patient_id), []).append(assessment)

    meds_by_patient: dict[str, list[dict]] = {}
    med_rows = await db.execute(
        select(Medication).where(
            Medication.patient_id.in_(patient_ids),
            Medication.is_active.is_(True),
        )
    )
    for med in med_rows.scalars().all():
        meds_by_patient.setdefault(str(med.patient_id), []).append({
            "name": med.name,
            "dosage": med.dosage,
            "frequency": med.frequency,
        })

    records: list[dict] = []
    for appt, patient, user in rows:
        appt_key = str(appt.id)
        pid = str(patient.id)
        status = appt.status.value if hasattr(appt.status, "value") else str(appt.status)
        matched = _pick_assessment_for_visit(appt, assessments_by_patient.get(pid, []))
        assessment = assessment_payload_from_row(matched) if matched else None
        note = notes_by_appt.get(appt_key)
        symptoms = assessment.get("symptoms", []) if assessment else []
        slot_past = is_slot_past(appt.slot_date, appt.slot_time)

        records.append({
            "appointment_id": appt_key,
            "apt_id": format_apt_id(appt.id),
            "patient_id": pid,
            "patient_name": user.name if user else "Patient",
            "date": str(appt.slot_date),
            "time": str(appt.slot_time),
            "status": status,
            "is_past": slot_past,
            "is_overdue": slot_past and is_active_appointment_status(status),
            "completed_at": appt.completed_at.isoformat() if appt.completed_at else None,
            "consultation_mode": appt.consultation_mode or "in_person",
            "is_video": bool(appt.video_room_id),
            "symptoms": symptoms,
            "risk_level": assessment.get("risk_level") if assessment else None,
            "recommended_specialty": assessment.get("recommended_specialty") if assessment else None,
            "duration": assessment.get("duration") if assessment else None,
            "medications": meds_by_patient.get(pid, []),
            "treatment_plan": note.plan if note else None,
            "soap_assessment": note.assessment if note else None,
            "has_soap_note": note is not None,
            "summary_excerpt": _summary_excerpt(summaries_by_appt.get(appt_key)),
        })

    return {"records": records, "total": len(records)}
