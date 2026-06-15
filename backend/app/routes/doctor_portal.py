from datetime import date, datetime, time, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_doctor_profile, require_doctor
from app.database import get_db
from app.models import (
    Appointment,
    Conversation,
    Doctor,
    DoctorNote,
    Message,
    Patient,
    PatientSummary,
    Report,
    SymptomAssessment,
    User,
)
from app.services.flow_state import get_flow
from app.services.patient_context import load_patient_context
from app.services.symptom_extraction import resolve_detected_symptoms
from app.models import DoctorAvailability
from app.models.enums import AppointmentStatus
from app.schemas.common import ResponseEnvelope
from app.services.doctor_service import create_default_availability, get_availability
from app.schemas.notifications import (
    MarkNotificationsReadRequest,
    MarkNotificationsReadResponse,
    NotificationUnreadCountResponse,
)
from app.services.notification_service import (
    count_unread_notifications,
    list_notifications_for_user,
    mark_notifications_read,
)
from app.services.refill_service import (
    approve_refill_request,
    deny_refill_request,
    list_refills_for_doctor,
)
from app.services.vitals_service import extract_health_vitals_from_reports

router = APIRouter(prefix="/doctor", tags=["doctor-portal"])


class AddSlotsRequest(BaseModel):
    slot_date: date
    times: list[str] = Field(min_length=1, description="Times like 09:00, 14:30")


class SOAPNote(BaseModel):
    subjective: str | None = None
    objective: str | None = None
    assessment: str | None = None
    plan: str | None = None
    appointment_id: UUID | None = None


class RefillDenyRequest(BaseModel):
    reason: str | None = None


async def _verify_access(db: AsyncSession, doctor_id: UUID, patient_id: UUID) -> bool:
    result = await db.execute(
        select(Appointment).where(
            Appointment.doctor_id == doctor_id,
            Appointment.patient_id == patient_id,
            Appointment.status.in_([AppointmentStatus.confirmed, AppointmentStatus.completed, AppointmentStatus.pending]),
        ).limit(1)
    )
    return result.scalar_one_or_none() is not None


def _format_appt_row(a: Appointment, patient_id: UUID, patient_name: str) -> dict:
    status = a.status.value if hasattr(a.status, "value") else str(a.status)
    return {
        "appointment_id": str(a.id),
        "patient_id": str(patient_id),
        "patient_name": patient_name,
        "date": str(a.slot_date),
        "time": str(a.slot_time),
        "status": status,
    }


@router.get("/appointments")
async def all_appointments(doctor: Doctor = Depends(get_doctor_profile), db: AsyncSession = Depends(get_db)):
    """All appointments for the logged-in doctor."""
    result = await db.execute(
        select(Appointment, Patient, User)
        .join(Patient, Appointment.patient_id == Patient.id)
        .join(User, Patient.user_id == User.id)
        .where(Appointment.doctor_id == doctor.id)
        .order_by(Appointment.slot_date.desc(), Appointment.slot_time.desc())
    )
    return ResponseEnvelope(
        data=[_format_appt_row(a, p.id, u.name) for a, p, u in result.all()]
    )


@router.get("/availability")
async def my_availability(doctor: Doctor = Depends(get_doctor_profile), db: AsyncSession = Depends(get_db)):
    return ResponseEnvelope(data=await get_availability(db, doctor.id))


@router.post("/availability")
async def add_availability(
    data: AddSlotsRequest,
    doctor: Doctor = Depends(get_doctor_profile),
    db: AsyncSession = Depends(get_db),
):
    added = 0
    for t_str in data.times:
        parts = t_str.strip().split(":")
        hour, minute = int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
        slot_time = time(hour, minute)
        exists = await db.execute(
            select(DoctorAvailability).where(
                DoctorAvailability.doctor_id == doctor.id,
                DoctorAvailability.slot_date == data.slot_date,
                DoctorAvailability.slot_time == slot_time,
            )
        )
        if not exists.scalar_one_or_none():
            db.add(DoctorAvailability(
                doctor_id=doctor.id, slot_date=data.slot_date, slot_time=slot_time, status="available"
            ))
            added += 1
    await db.flush()
    return ResponseEnvelope(data={"added": added})


@router.post("/availability/seed-default")
async def seed_my_availability(doctor: Doctor = Depends(get_doctor_profile), db: AsyncSession = Depends(get_db)):
    """Generate 14 days of default slots if doctor has none."""
    added = await create_default_availability(db, doctor.id)
    return ResponseEnvelope(data={"added": added})


@router.get("/appointments/today")
async def today_appointments(doctor: Doctor = Depends(get_doctor_profile), db: AsyncSession = Depends(get_db)):
    today = date.today()
    result = await db.execute(
        select(Appointment, Patient, User)
        .join(Patient, Appointment.patient_id == Patient.id)
        .join(User, Patient.user_id == User.id)
        .where(Appointment.doctor_id == doctor.id, Appointment.slot_date == today)
        .order_by(Appointment.slot_time)
    )
    return ResponseEnvelope(
        data=[_format_appt_row(a, p.id, u.name) for a, p, u in result.all()]
    )


@router.get("/patients")
async def my_patients(doctor: Doctor = Depends(get_doctor_profile), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Patient, User)
        .join(User, Patient.user_id == User.id)
        .join(Appointment, Appointment.patient_id == Patient.id)
        .where(Appointment.doctor_id == doctor.id)
        .distinct()
    )
    return ResponseEnvelope(data=[{"patient_id": str(p.id), "name": u.name} for p, u in result.all()])


@router.get("/patients/{patient_id}")
async def patient_detail(
    patient_id: UUID, doctor: Doctor = Depends(get_doctor_profile), db: AsyncSession = Depends(get_db)
):
    if not await _verify_access(db, doctor.id, patient_id):
        raise HTTPException(status_code=403, detail="Forbidden")

    patient = await db.get(Patient, patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    user = await db.get(User, patient.user_id)

    appt_rows = await db.execute(
        select(Appointment)
        .where(Appointment.doctor_id == doctor.id, Appointment.patient_id == patient_id)
        .order_by(Appointment.slot_date.desc(), Appointment.slot_time.desc())
    )
    appointments = [
        {
            "appointment_id": str(a.id),
            "date": str(a.slot_date),
            "time": str(a.slot_time),
            "status": a.status.value if hasattr(a.status, "value") else str(a.status),
        }
        for a in appt_rows.scalars().all()
    ]

    summary_row = await db.execute(
        select(PatientSummary)
        .where(PatientSummary.patient_id == patient_id)
        .order_by(PatientSummary.generated_at.desc())
        .limit(1)
    )
    summary = summary_row.scalar_one_or_none()

    return ResponseEnvelope(
        data={
            "patient_id": str(patient_id),
            "name": user.name if user else "Patient",
            "email": user.email if user else "",
            "dob": str(patient.dob) if patient.dob else None,
            "gender": patient.gender,
            "blood_group": patient.blood_group,
            "appointments": appointments,
            "summary": summary.summary_text if summary else "No AI summary yet. Summary is generated when patient books via chatbot.",
        }
    )


@router.get("/patients/{patient_id}/summary")
async def patient_summary(
    patient_id: UUID, doctor: Doctor = Depends(get_doctor_profile), db: AsyncSession = Depends(get_db)
):
    if not await _verify_access(db, doctor.id, patient_id):
        raise HTTPException(status_code=403, detail="Forbidden")
    result = await db.execute(
        select(PatientSummary).where(PatientSummary.patient_id == patient_id).order_by(PatientSummary.generated_at.desc()).limit(1)
    )
    summary = result.scalar_one_or_none()
    return ResponseEnvelope(data={"summary": summary.summary_text if summary else "No summary yet"})


@router.get("/patients/{patient_id}/consultation-summary")
async def patient_consultation_summary(
    patient_id: UUID, doctor: Doctor = Depends(get_doctor_profile), db: AsyncSession = Depends(get_db)
):
    if not await _verify_access(db, doctor.id, patient_id):
        raise HTTPException(status_code=403, detail="Forbidden")

    patient = await db.get(Patient, patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    ctx = await load_patient_context(db, patient)

    assessment_rows = await db.execute(
        select(SymptomAssessment)
        .where(SymptomAssessment.patient_id == patient_id)
        .order_by(SymptomAssessment.completed_at.desc())
        .limit(10)
    )
    from app.services.symptom_service import assessment_payload_from_row

    assessments = [assessment_payload_from_row(a) for a in assessment_rows.scalars().all()]

    conv_rows = await db.execute(
        select(Conversation)
        .where(Conversation.patient_id == patient_id)
        .order_by(Conversation.created_at.desc())
    )
    conversations = conv_rows.scalars().all()

    detected_symptoms: list[str] = []
    seen_symptoms: set[str] = set()
    consultation_history = []
    emergency_flag = False
    total_messages = 0

    for conv in conversations:
        emergency_flag = emergency_flag or bool(conv.emergency_flag)
        msg_rows = await db.execute(
            select(Message)
            .where(Message.conversation_id == conv.id)
            .order_by(Message.created_at, Message.id)
        )
        msgs = msg_rows.scalars().all()
        total_messages += len(msgs)
        history = [
            {
                "role": m.role.value if hasattr(m.role, "value") else str(m.role),
                "content": m.content,
            }
            for m in msgs
        ]
        flow = await get_flow(conv.id)
        session = flow.get("session") or {}
        conv_symptoms = await resolve_detected_symptoms(session, history)
        for s in conv_symptoms:
            key = s.strip().lower()
            if key and key not in seen_symptoms:
                seen_symptoms.add(key)
                detected_symptoms.append(s.strip())

        preview = ""
        for m in msgs:
            role = m.role.value if hasattr(m.role, "value") else str(m.role)
            if role == "user" and m.content:
                preview = m.content.strip()[:160]
                break
        if not preview and msgs:
            preview = (msgs[-1].content or "").strip()[:160]

        consultation_history.append({
            "conversation_id": str(conv.id),
            "title": conv.title or "Health Chat",
            "created_at": conv.created_at.isoformat() if conv.created_at else None,
            "message_count": len(msgs),
            "emergency_flag": conv.emergency_flag,
            "detected_symptoms": conv_symptoms,
            "preview": preview,
        })

    latest = assessments[0] if assessments else None
    return ResponseEnvelope(
        data={
            "detected_symptoms": detected_symptoms,
            "risk_level": latest.get("risk_level") if latest else None,
            "recommended_specialty": latest.get("recommended_specialty") if latest else None,
            "recommendation_text": latest.get("recommendation_text") if latest else None,
            "duration": latest.get("duration") if latest else None,
            "emergency_flag": emergency_flag,
            "conversation_count": len(conversations),
            "total_messages": total_messages,
            "assessments": assessments,
            "consultation_history": consultation_history,
            "conditions": ctx.get("conditions") or [],
            "medications": ctx.get("medications") or [],
            "allergies": ctx.get("allergies") or [],
            "memory_facts": ctx.get("memory_facts") or [],
        }
    )


@router.get("/patients/{patient_id}/conversations")
async def patient_conversations(
    patient_id: UUID, doctor: Doctor = Depends(get_doctor_profile), db: AsyncSession = Depends(get_db)
):
    if not await _verify_access(db, doctor.id, patient_id):
        raise HTTPException(status_code=403)
    convs = await db.execute(
        select(Conversation)
        .where(Conversation.patient_id == patient_id)
        .order_by(Conversation.created_at.desc())
    )
    data = []
    for c in convs.scalars().all():
        msgs = await db.execute(
            select(Message)
            .where(Message.conversation_id == c.id)
            .order_by(Message.created_at)
        )
        data.append({
            "conversation_id": str(c.id),
            "title": c.title or "Health Chat",
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "emergency_flag": c.emergency_flag,
            "messages": [
                {
                    "role": m.role.value if hasattr(m.role, "value") else str(m.role),
                    "content": m.content,
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                }
                for m in msgs.scalars().all()
            ],
        })
    return ResponseEnvelope(data=data)


@router.get("/patients/{patient_id}/reports")
async def patient_reports(
    patient_id: UUID, doctor: Doctor = Depends(get_doctor_profile), db: AsyncSession = Depends(get_db)
):
    if not await _verify_access(db, doctor.id, patient_id):
        raise HTTPException(status_code=403)
    result = await db.execute(select(Report).where(Report.patient_id == patient_id))
    return ResponseEnvelope(data=[{"id": str(r.id), "analysis": r.analysis_json} for r in result.scalars().all()])


@router.get("/patients/{patient_id}/health-vitals")
async def patient_health_vitals(
    patient_id: UUID, doctor: Doctor = Depends(get_doctor_profile), db: AsyncSession = Depends(get_db)
):
    if not await _verify_access(db, doctor.id, patient_id):
        raise HTTPException(status_code=403)
    result = await db.execute(
        select(Report).where(Report.patient_id == patient_id).order_by(Report.created_at.desc())
    )
    reports = list(result.scalars().all())
    vitals = extract_health_vitals_from_reports(reports)
    return ResponseEnvelope(data={"vitals": vitals, "has_data": len(vitals) > 0})


@router.post("/patients/{patient_id}/soap-notes")
async def create_soap(
    patient_id: UUID,
    data: SOAPNote,
    doctor: Doctor = Depends(get_doctor_profile),
    db: AsyncSession = Depends(get_db),
):
    if not await _verify_access(db, doctor.id, patient_id):
        raise HTTPException(status_code=403)
    note = DoctorNote(doctor_id=doctor.id, patient_id=patient_id, **data.model_dump())
    db.add(note)
    await db.flush()
    return ResponseEnvelope(data={"id": str(note.id)})


@router.post("/appointments/{appointment_id}/complete")
async def complete_appointment(
    appointment_id: UUID, doctor: Doctor = Depends(get_doctor_profile), db: AsyncSession = Depends(get_db)
):
    appt = await db.get(Appointment, appointment_id)
    if not appt or appt.doctor_id != doctor.id:
        raise HTTPException(status_code=404)
    appt.status = AppointmentStatus.completed
    appt.completed_at = datetime.now(timezone.utc)
    await db.flush()
    return ResponseEnvelope(data={"status": "completed"})


@router.get("/refill-requests")
async def doctor_refill_requests(
    status: str | None = None,
    doctor: Doctor = Depends(get_doctor_profile),
    db: AsyncSession = Depends(get_db),
):
    data = await list_refills_for_doctor(db, doctor.id, status=status)
    return ResponseEnvelope(data=data)


@router.post("/refill-requests/{request_id}/approve")
async def doctor_approve_refill(
    request_id: UUID,
    doctor: Doctor = Depends(get_doctor_profile),
    db: AsyncSession = Depends(get_db),
):
    result = await approve_refill_request(db, doctor.id, request_id)
    return ResponseEnvelope(data=result)


@router.post("/refill-requests/{request_id}/deny")
async def doctor_deny_refill(
    request_id: UUID,
    data: RefillDenyRequest,
    doctor: Doctor = Depends(get_doctor_profile),
    db: AsyncSession = Depends(get_db),
):
    result = await deny_refill_request(db, doctor.id, request_id, data.reason)
    return ResponseEnvelope(data=result)


@router.get("/notifications")
async def doctor_notifications(
    doctor: Doctor = Depends(get_doctor_profile),
    db: AsyncSession = Depends(get_db),
):
    data = await list_notifications_for_user(db, doctor.user_id)
    return ResponseEnvelope(data=data)


@router.get("/notifications/unread-count", response_model=ResponseEnvelope[NotificationUnreadCountResponse])
async def doctor_notifications_unread_count(
    doctor: Doctor = Depends(get_doctor_profile),
    db: AsyncSession = Depends(get_db),
):
    count = await count_unread_notifications(db, doctor.user_id)
    return ResponseEnvelope(data=NotificationUnreadCountResponse(count=count))


@router.post("/notifications/mark-read", response_model=ResponseEnvelope[MarkNotificationsReadResponse])
async def doctor_notifications_mark_read(
    data: MarkNotificationsReadRequest,
    doctor: Doctor = Depends(get_doctor_profile),
    db: AsyncSession = Depends(get_db),
):
    marked = await mark_notifications_read(db, doctor.user_id, data.ids)
    return ResponseEnvelope(data=MarkNotificationsReadResponse(marked=marked))
