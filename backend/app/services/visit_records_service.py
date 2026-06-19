"""Per-visit consultation records for the doctor patient chart."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Appointment, Consultation, DoctorNote, Patient, PatientSummary, Report, SymptomAssessment, User
from app.services.appointment_service import format_apt_id, is_active_appointment_status, appointment_supports_video_call, is_slot_past
from app.services.medication_timeline_service import (
    build_patient_medication_timeline,
    load_prescription_items_by_appointment,
)
from app.services.patient_context import load_patient_context
from app.services.symptom_service import assessment_payload_from_row
from app.services.consultation_transcript_service import load_transcript_cards_by_consultation_ids


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


def _linked_report_payload(report: Report | None) -> dict | None:
    if not report:
        return None
    meta = (report.analysis_json or {}).get("_meta") or {}
    analysis = report.analysis_json or {}
    return {
        "report_id": str(report.id),
        "filename": meta.get("filename") or "Medical report",
        "summary": (analysis.get("summary") or "").strip(),
        "abnormal": analysis.get("abnormal") or [],
        "created_at": report.created_at.isoformat() if report.created_at else None,
    }


async def list_visit_records_for_doctor(
    db: AsyncSession,
    doctor_id: UUID,
    patient_id: UUID,
) -> dict:
    patient = await db.get(Patient, patient_id)
    if not patient:
        return {"visits": [], "medications": [], "medication_timeline": {
            "medications": [],
            "active_medications": [],
            "ended_medications": [],
            "pending_refills": [],
            "summary": {
                "total_prescribed": 0,
                "active_count": 0,
                "ended_count": 0,
                "pending_refill_count": 0,
            },
        }, "conditions": [], "allergies": [], "reports": []}

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

    consultations_by_appt: dict[str, Consultation] = {}
    if appt_ids:
        consultation_rows = await db.execute(
            select(Consultation).where(Consultation.appointment_id.in_(appt_ids))
        )
        for row in consultation_rows.scalars().all():
            consultations_by_appt[str(row.appointment_id)] = row

    consultation_ids = [c.id for c in consultations_by_appt.values()]
    transcript_cards = await load_transcript_cards_by_consultation_ids(db, consultation_ids)

    linked_report_ids = {a.linked_report_id for a in appointments if a.linked_report_id}
    reports_by_id: dict = {}
    if linked_report_ids:
        linked_rows = await db.execute(select(Report).where(Report.id.in_(linked_report_ids)))
        reports_by_id = {r.id: r for r in linked_rows.scalars().all()}

    prescription_items_by_appt = await load_prescription_items_by_appointment(db, consultations_by_appt)

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
        consultation = consultations_by_appt.get(appt_key)
        linked_report = (
            _linked_report_payload(reports_by_id.get(appt.linked_report_id))
            if appt.linked_report_id
            else None
        )
        visits.append({
            "appointment_id": appt_key,
            "apt_id": format_apt_id(appt.id),
            "date": str(appt.slot_date),
            "time": str(appt.slot_time),
            "status": status,
            "completed_at": appt.completed_at.isoformat() if appt.completed_at else None,
            "consultation_mode": appt.consultation_mode or "in_person",
            "is_video": appointment_supports_video_call(appt),
            "appointment_reason": appt.appointment_reason,
            "visit_type": "report_discussion" if appt.linked_report_id else "symptom",
            "linked_report": linked_report,
            "chief_complaint": consultation.chief_complaint if consultation else None,
            "follow_up_date": (
                str(consultation.follow_up_date)
                if consultation and consultation.follow_up_date
                else None
            ),
            "summary": summaries_by_appt.get(appt_key) or (
                summaries_by_appt.get("__latest__") if status == "completed" else None
            ),
            "soap_note": notes_by_appt.get(appt_key),
            "assessment": assessment_payload_from_row(matched) if matched else None,
            "prescription_items": prescription_items_by_appt.get(appt_key, []),
            **(
                transcript_cards.get(str(consultation.id), {})
                if consultation and appointment_supports_video_call(appt)
                else {}
            ),
        })

    medication_timeline = await build_patient_medication_timeline(db, doctor_id, patient_id)

    return {
        "visits": visits,
        "medications": ctx.get("medications") or [],
        "medication_timeline": medication_timeline,
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

    consultations_by_appt: dict[str, Consultation] = {}
    if appt_ids:
        consultation_rows = await db.execute(
            select(Consultation).where(
                Consultation.doctor_id == doctor_id,
                Consultation.appointment_id.in_(appt_ids),
            )
        )
        for row in consultation_rows.scalars().all():
            consultations_by_appt[str(row.appointment_id)] = row

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

    prescription_items_by_appt = await load_prescription_items_by_appointment(db, consultations_by_appt)

    records: list[dict] = []
    for appt, patient, user in rows:
        appt_key = str(appt.id)
        pid = str(patient.id)
        status = appt.status.value if hasattr(appt.status, "value") else str(appt.status)
        matched = _pick_assessment_for_visit(appt, assessments_by_patient.get(pid, []))
        assessment = assessment_payload_from_row(matched) if matched else None
        note = notes_by_appt.get(appt_key)
        consultation = consultations_by_appt.get(appt_key)
        symptoms = assessment.get("symptoms", []) if assessment else []
        slot_past = is_slot_past(appt.slot_date, appt.slot_time)
        visit_rx = prescription_items_by_appt.get(appt_key, [])
        visit_medications = [
            {
                "name": item["medicine_name"],
                "dosage": item["strength"],
                "frequency": item["frequency"],
                "duration": item["duration"],
            }
            for item in visit_rx
        ]

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
            "is_video": appointment_supports_video_call(appt),
            "appointment_reason": appt.appointment_reason,
            "symptoms": symptoms,
            "risk_level": assessment.get("risk_level") if assessment else None,
            "recommended_specialty": assessment.get("recommended_specialty") if assessment else None,
            "duration": assessment.get("duration") if assessment else None,
            "medications": visit_medications,
            "prescription_items": visit_rx,
            "treatment_plan": note.plan if note else None,
            "soap_assessment": note.assessment if note else None,
            "has_soap_note": note is not None,
            "follow_up_date": (
                str(consultation.follow_up_date)
                if consultation and consultation.follow_up_date
                else None
            ),
            "summary_excerpt": _summary_excerpt(summaries_by_appt.get(appt_key)),
        })

    return {"records": records, "total": len(records)}
