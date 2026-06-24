"""Dynamic agent tools — all data loaded from the database at runtime."""
import json
import re
from datetime import date, time, timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Appointment, Doctor, DoctorAvailability, Medication, Notification, Patient, User
from app.models.enums import AppointmentStatus, NotificationType
from app.services.appointment_service import (
    book_appointment,
    cancel_appointment,
    format_apt_id,
    get_latest_confirmed,
    reschedule_appointment,
    schedule_reminder,
)
from app.services.doctor_service import _fetch_doctor_slots, get_availability, list_doctors_with_availability
from app.services.summary_service import prepare_appointment_summary
from app.services.symptom_service import assess_symptoms, save_assessment


def _format_time(t: time) -> str:
    h = t.hour % 12 or 12
    ampm = "AM" if t.hour < 12 else "PM"
    return f"{h}:{t.minute:02d} {ampm}"


def _day_label(d: date) -> str:
    from app.utils.clinic_time import clinic_today

    today = clinic_today()
    if d == today:
        return "Today"
    if d == today + timedelta(days=1):
        return "Tomorrow"
    return str(d)


def serialize_slot(doctor_id: UUID, doctor_name: str, slot_date: date, slot_time: time) -> dict:
    return {
        "doctor_id": str(doctor_id),
        "doctor_name": doctor_name,
        "slot_date": slot_date.isoformat(),
        "slot_time": slot_time.isoformat(),
        "label": f"{_day_label(slot_date)}: {_format_time(slot_time)}",
    }


def deserialize_slot(s: dict) -> dict:
    return {
        "doctor_id": UUID(s["doctor_id"]),
        "doctor_name": s.get("doctor_name", ""),
        "slot_date": date.fromisoformat(s["slot_date"]),
        "slot_time": time.fromisoformat(s["slot_time"]),
        "label": s["label"],
    }


def slot_for_storage(slot: dict) -> dict:
    """JSON-safe slot dict for Redis session storage."""
    if isinstance(slot.get("slot_date"), str) and isinstance(slot.get("slot_time"), str):
        return {
            "doctor_id": str(slot["doctor_id"]),
            "doctor_name": slot.get("doctor_name", ""),
            "slot_date": slot["slot_date"],
            "slot_time": slot["slot_time"],
            "label": slot["label"],
        }
    parsed = slot if isinstance(slot.get("slot_date"), date) else deserialize_slot(slot)
    return {
        "doctor_id": str(parsed["doctor_id"]),
        "doctor_name": parsed.get("doctor_name", ""),
        "slot_date": parsed["slot_date"].isoformat(),
        "slot_time": parsed["slot_time"].isoformat(),
        "label": parsed["label"],
    }


def _match_doctor(text: str, doctors: list[dict]) -> dict | None:
    t = text.lower()
    for doc in doctors:
        name = doc["name"].lower()
        last = name.split()[-1].replace(".", "")
        if last in t or name.replace(".", "") in t.replace(".", ""):
            return doc
    return None


def _parse_slot_time(text: str) -> time | None:
    t = text.lower().strip()
    t = re.sub(r"(\d{1,2})\.(\d{2})", r"\1:\2", t)
    m = re.search(r"(\d{1,2})\s*:\s*(\d{2})\s*(am|pm)?", t)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2))
        ampm = m.group(3)
        if ampm == "pm" and hour != 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0
        elif not ampm and 1 <= hour <= 6:
            hour += 12
        return time(hour, minute)
    m = re.search(r"(\d{1,2})\s*(am|pm)", t)
    if m:
        hour = int(m.group(1))
        if m.group(2) == "pm" and hour != 12:
            hour += 12
        if m.group(2) == "am" and hour == 12:
            hour = 0
        return time(hour, 0)
    return None


def _filter_slots_by_day(slots: list[dict], text: str) -> list[dict]:
    t = text.lower()
    if "today" in t:
        return [s for s in slots if "today" in s["label"].lower()]
    if "tomorrow" in t:
        return [s for s in slots if "tomorrow" in s["label"].lower()]
    return slots


def match_slot_from_text(
    text: str,
    slots: list[dict],
    *,
    doctor_id: str | None = None,
) -> dict | None:
    t = text.lower().replace(".", "")
    deserialized = [
        deserialize_slot(s) if "slot_date" in s and isinstance(s["slot_date"], str) else s
        for s in slots
    ]

    candidate_slots = deserialized
    if doctor_id:
        candidate_slots = [
            s for s in candidate_slots if str(s.get("doctor_id")) == str(doctor_id)
        ]

    # If patient named a doctor in text, only match that doctor's slots
    for s in deserialized:
        doc_name = s.get("doctor_name", "").lower()
        if not doc_name:
            continue
        last = doc_name.split()[-1].replace(".", "")
        if last in t or doc_name.replace(".", "") in t.replace(".", ""):
            candidate_slots = [
                x for x in candidate_slots if x.get("doctor_name", "").lower() == doc_name
            ]
            break

    if not candidate_slots:
        return None

    for s in candidate_slots:
        label_lower = s["label"].lower()
        if label_lower in t or t.strip() == label_lower:
            return s

    pool = _filter_slots_by_day(candidate_slots, text)
    parsed = _parse_slot_time(text)
    if parsed:
        exact = [
            s for s in pool
            if s["slot_time"].hour == parsed.hour and s["slot_time"].minute == parsed.minute
        ]
        if len(exact) == 1:
            return exact[0]
        if len(exact) > 1:
            return exact[0]

        fmt = _format_time(parsed).lower()
        label_matches = [s for s in pool if fmt in s["label"].lower()]
        if len(label_matches) == 1:
            return label_matches[0]

    if len(pool) == 1:
        return pool[0]

    return None


async def tool_search_doctors(db: AsyncSession, specialty: str | None = None) -> dict:
    """Load all doctors from PostgreSQL with live availability slots."""
    doctors = await list_doctors_with_availability(db, specialty=specialty, slots_per_doctor=30)
    all_slots = [s for d in doctors for s in d.get("slots", [])]
    return {
        "doctors": doctors,
        "all_slots": all_slots,
        "specialty_filter": specialty or "all",
        "total": len(doctors),
    }


async def tool_get_doctor_slots(db: AsyncSession, doctor_id: UUID, limit: int = 8) -> dict:
    doc = await db.get(Doctor, doctor_id)
    if not doc:
        return {"slots": [], "doctor_name": "Unknown"}
    user = await db.get(User, doc.user_id)
    doctor_name = user.name if user else "Doctor"
    slots = await _fetch_doctor_slots(db, doctor_id, doctor_name, limit=limit)
    return {"doctor_name": doctor_name, "slots": slots}


async def tool_list_appointments(db: AsyncSession, patient_id: UUID) -> dict:
    from app.models import Appointment

    rows = await db.execute(
        select(Appointment, User.name)
        .join(Doctor, Doctor.id == Appointment.doctor_id)
        .join(User, User.id == Doctor.user_id)
        .where(
            Appointment.patient_id == patient_id,
            Appointment.status.in_([AppointmentStatus.confirmed, AppointmentStatus.pending]),
        )
        .order_by(Appointment.slot_date, Appointment.slot_time)
    )
    appts = []
    for appt, doc_name in rows.all():
        appts.append({
            "id": str(appt.id),
            "apt_id": format_apt_id(appt.id),
            "doctor_name": doc_name,
            "label": f"{_day_label(appt.slot_date)} {_format_time(appt.slot_time)}",
            "status": appt.status.value if hasattr(appt.status, "value") else str(appt.status),
        })
    return {"appointments": appts}


async def tool_book_slot(
    db: AsyncSession,
    patient: Patient,
    user_id: UUID,
    slot: dict,
    conversation_id: UUID | None = None,
    *,
    booking_context: dict | None = None,
) -> dict:
    s = deserialize_slot(slot) if isinstance(slot.get("slot_date"), str) else slot
    ctx = booking_context or {}
    linked_report_id = ctx.get("linked_report_id")
    appt = await book_appointment(
        db,
        patient.id,
        s["doctor_id"],
        s["slot_date"],
        s["slot_time"],
        user_id,
        consultation_mode=ctx.get("pending_consultation_mode", "in_person"),
        appointment_reason=ctx.get("appointment_reason"),
        linked_report_id=UUID(str(linked_report_id)) if linked_report_id else None,
    )
    try:
        await prepare_appointment_summary(db, appt.id, conversation_id)
    except Exception:
        pass
    return {
        "success": True,
        "apt_id": format_apt_id(appt.id),
        "doctor_name": s.get("doctor_name", ""),
        "label": s["label"],
        "appointment_id": str(appt.id),
    }


async def tool_cancel_appointment(db: AsyncSession, patient_id: UUID, appointment_id: UUID | None = None) -> dict:
    if appointment_id:
        from app.models import Appointment

        result = await db.execute(
            select(Appointment).where(Appointment.id == appointment_id, Appointment.patient_id == patient_id)
        )
        appt = result.scalar_one_or_none()
    else:
        appt = await get_latest_confirmed(db, patient_id)
    if not appt:
        return {"success": False, "message": "No active appointment found."}
    await cancel_appointment(db, appt.id, patient_id, "Patient requested via chat")
    return {"success": True, "apt_id": format_apt_id(appt.id)}


async def tool_reschedule(
    db: AsyncSession, patient_id: UUID, user_id: UUID, appointment_id: UUID, new_slot: dict
) -> dict:
    s = deserialize_slot(new_slot) if isinstance(new_slot.get("slot_date"), str) else new_slot
    await reschedule_appointment(db, appointment_id, patient_id, s["slot_date"], s["slot_time"], user_id)
    return {"success": True, "label": s["label"], "apt_id": format_apt_id(appointment_id)}


async def tool_reschedule_alternatives(
    db: AsyncSession, patient_id: UUID, appointment_id: UUID | None = None
) -> dict:
    if appointment_id:
        result = await db.execute(
            select(Appointment).where(
                Appointment.id == appointment_id,
                Appointment.patient_id == patient_id,
                Appointment.status == AppointmentStatus.confirmed,
            )
        )
        appt = result.scalar_one_or_none()
    else:
        appt = await get_latest_confirmed(db, patient_id)
    if not appt:
        return {"success": False, "message": "No active appointment to reschedule."}
    doc = await db.get(Doctor, appt.doctor_id)
    user = await db.get(User, doc.user_id) if doc else None
    slots_result = await tool_get_doctor_slots(db, appt.doctor_id, limit=10)
    alt = [
        s for s in slots_result["slots"]
        if s["slot_date"] != appt.slot_date.isoformat() or s["slot_time"] != appt.slot_time.isoformat()
    ][:6]
    return {
        "success": True,
        "appointment_id": str(appt.id),
        "apt_id": format_apt_id(appt.id),
        "doctor_name": user.name if user else "Doctor",
        "current": f"{_day_label(appt.slot_date)} {_format_time(appt.slot_time)}",
        "alternatives": alt,
    }


async def tool_get_medications(db: AsyncSession, patient_id: UUID) -> dict:
    rows = await db.execute(
        select(Medication).where(Medication.patient_id == patient_id, Medication.is_active.is_(True))
    )
    meds = [{"name": m.name, "dosage": m.dosage, "frequency": m.frequency} for m in rows.scalars().all()]
    return {"medications": meds}


async def tool_request_refill(db: AsyncSession, patient_id: UUID, user_id: UUID, medication_name: str | None) -> dict:
    from app.models import Patient
    from app.services.refill_service import create_refill_request

    patient = await db.get(Patient, patient_id)
    if not patient:
        return {"success": False, "message": "Patient not found."}
    result = await create_refill_request(db, patient, medication_name)
    if not result.get("success"):
        return result
    return {
        "success": True,
        "request_id": result.get("request_id"),
        "medication": result.get("medication"),
        "doctor_name": result.get("doctor_name"),
        "message": result.get("message"),
    }


async def tool_analyze_report(
    db: AsyncSession,
    patient_id: UUID,
    report_id: UUID,
) -> dict:
    """Fetch or generate analysis for a patient report from stored file + OCR."""
    from app.models import Report
    from app.services.report_service import analyze_report_record

    report = await db.get(Report, report_id)
    if not report or report.patient_id != patient_id:
        return {"success": False, "message": "Report not found."}

    try:
        analysis = await analyze_report_record(db, report)
    except ValueError as exc:
        return {"success": False, "message": str(exc)}

    return {
        "success": True,
        "report_id": str(report.id),
        "analysis": analysis,
        "ocr_text": report.ocr_text,
    }


def _merge_symptom_assessment(rule_result: dict, llm_result: dict) -> dict:
    """Trust LLM assessment; keyword rules may only escalate to emergency."""
    from app.models.enums import RiskLevel

    risk_map = {
        "low": RiskLevel.low,
        "medium": RiskLevel.medium,
        "high": RiskLevel.high,
        "emergency": RiskLevel.emergency,
    }
    llm_risk = risk_map.get(str(llm_result.get("risk_level", "low")).lower(), RiskLevel.low)
    risk = llm_risk
    if rule_result["risk_level"] == RiskLevel.emergency:
        risk = RiskLevel.emergency
    return {
        "risk_level": risk.value if hasattr(risk, "value") else str(risk),
        "recommended_specialty": llm_result.get("recommended_specialty")
        or rule_result["recommended_specialty"],
        "recommendation": llm_result.get("recommendation")
        or rule_result.get("recommendation_text", "Please consult a clinician if symptoms persist."),
    }


async def tool_assess_symptoms_llm(
    symptoms: list[str],
    duration: str | None,
    conditions: list[str],
    collected: dict | None = None,
) -> dict | None:
    from app.multi_agent.llm import llm

    if not llm.available:
        return None
    payload = json.dumps(
        {"symptoms": symptoms, "duration": duration, "conditions": conditions, "collected": collected or {}},
        default=str,
    )
    prompt = (
        "Based on symptom triage data, recommend next steps. Return ONLY JSON:\n"
        '{"risk_level": "low|medium|high|emergency", '
        '"recommended_specialty": "General Physician|Cardiologist|...", '
        '"recommendation": "2-3 short sentences in plain, simple English (easy for non-native speakers). '
        'Use common words and short sentences. Focus on rest, hydration, and when to see a doctor. '
        'Do not diagnose or prescribe. Do not start with booking or scheduling — that comes later."}\n\n'
        f"DATA:\n{payload}"
    )
    result = await llm.json_prompt(prompt)
    if result:
        return {
            "risk_level": result.get("risk_level", "low"),
            "recommended_specialty": result.get("recommended_specialty", "General Physician"),
            "recommendation": result.get("recommendation", "Please consult a clinician if symptoms persist."),
        }
    return None


async def tool_assess_symptoms(
    db: AsyncSession,
    patient_id: UUID,
    symptoms: list[str],
    duration: str | None,
    conditions: list[str],
    conversation_id: UUID | None = None,
    collected: dict | None = None,
) -> dict:
    rule_result = assess_symptoms(symptoms, duration, conditions)
    llm_result = await tool_assess_symptoms_llm(symptoms, duration, conditions, collected)
    if llm_result:
        merged = _merge_symptom_assessment(rule_result, llm_result)
        await save_assessment(
            db, patient_id, symptoms, duration, conditions, conversation_id=conversation_id
        )
        return merged
    result = assess_symptoms(symptoms, duration, conditions)
    await save_assessment(
        db, patient_id, symptoms, duration, conditions, conversation_id=conversation_id
    )
    return {
        "risk_level": result["risk_level"].value if hasattr(result["risk_level"], "value") else str(result["risk_level"]),
        "recommended_specialty": result["recommended_specialty"],
        "recommendation": result["recommendation_text"],
    }


async def tool_schedule_reminder(db: AsyncSession, user_id: UUID, appointment_id: UUID, minutes: int = 30) -> dict:
    result = await schedule_reminder(db, user_id, appointment_id, minutes)
    return {
        "success": result.get("success", True),
        "minutes": minutes,
        "message": result.get("message"),
        "already_scheduled": result.get("already_scheduled"),
    }


async def tool_list_reports(db: AsyncSession, patient_id: UUID) -> dict:
    from app.models import Report

    rows = await db.execute(select(Report).where(Report.patient_id == patient_id).order_by(Report.created_at.desc()))
    reports = [
        {
            "id": str(r.id),
            "created_at": str(r.created_at),
            "has_analysis": bool(r.analysis_json),
        }
        for r in rows.scalars().all()
    ]
    return {"reports": reports, "total": len(reports)}


async def tool_get_report_analysis(db: AsyncSession, patient_id: UUID, report_id: UUID) -> dict:
    from app.models import Report

    report = await db.get(Report, report_id)
    if not report or report.patient_id != patient_id:
        return {"success": False, "message": "Report not found."}
    return {
        "success": True,
        "report_id": str(report.id),
        "ocr_text": report.ocr_text,
        "analysis": report.analysis_json,
        "created_at": str(report.created_at),
    }


async def tool_retrieve_evidence(db: AsyncSession, patient_id: UUID, args: dict) -> dict:
    from app.rag.retriever import chunks_to_citations, retrieve_evidence
    from app.rag.schemas import IndexType

    query = str(args.get("query") or "").strip()
    if not query:
        return {"chunks": [], "citations": []}

    raw_indexes = args.get("indexes") or [IndexType.PATIENT_CHART.value]
    indexes = [str(i) for i in raw_indexes]
    top_k = args.get("top_k")

    chunks = await retrieve_evidence(
        db,
        query=query,
        indexes=indexes,
        patient_id=patient_id,
        top_k=int(top_k) if top_k else None,
    )
    serialized = [c.model_dump() for c in chunks]
    return {"chunks": serialized, "citations": chunks_to_citations(chunks)}


async def tool_save_memory(
    db: AsyncSession,
    patient_id: UUID,
    fact: str,
    conversation_id: UUID | None = None,
) -> dict:
    from app.models import ConversationMemory

    fact = fact.strip()
    if not fact:
        return {"success": False, "message": "Empty fact."}
    db.add(
        ConversationMemory(
            patient_id=patient_id,
            fact=fact[:2000],
            source_conversation_id=conversation_id,
        )
    )
    await db.flush()
    return {"success": True, "fact": fact}


async def _assess_symptoms_without_patient(
    args: dict,
    patient_ctx: dict,
) -> dict:
    """Symptom assessment for guests — no DB persistence until after sign-in."""
    symptoms = args.get("symptoms", [])
    duration = args.get("duration")
    conditions = patient_ctx.get("conditions", [])
    collected = args.get("collected") or args.get("summary")
    rule_result = assess_symptoms(symptoms, duration, conditions)
    llm_result = await tool_assess_symptoms_llm(symptoms, duration, conditions, collected)
    if llm_result:
        return _merge_symptom_assessment(rule_result, llm_result)
    result = assess_symptoms(symptoms, duration, conditions)
    return {
        "risk_level": result["risk_level"].value if hasattr(result["risk_level"], "value") else str(result["risk_level"]),
        "recommended_specialty": result["recommended_specialty"],
        "recommendation": result["recommendation_text"],
    }


async def execute_agent_tool(
    db: AsyncSession,
    patient: Patient | None,
    tool: str,
    args: dict,
    conversation_id: UUID,
    patient_ctx: dict | None = None,
) -> dict:
    """Execute any registered agent tool — single gateway for the orchestrator."""
    patient_ctx = patient_ctx or {}
    if tool == "search_doctors":
        return await tool_search_doctors(db, args.get("specialty"))
    if tool == "get_doctor_slots":
        return await tool_get_doctor_slots(db, UUID(args["doctor_id"]))
    if patient is None:
        if tool == "assess_symptoms":
            return await _assess_symptoms_without_patient(args, patient_ctx)
        if tool in {"search_doctors", "get_doctor_slots"}:
            pass
        else:
            return {"success": False, "message": "Please verify your email to continue this action."}

    if tool == "list_appointments":
        return await tool_list_appointments(db, patient.id)
    if tool == "get_medications":
        return await tool_get_medications(db, patient.id)
    if tool == "book_slot":
        return await tool_book_slot(db, patient, patient.user_id, args["slot"], conversation_id)
    if tool == "cancel_appointment":
        appt_id = UUID(args["appointment_id"]) if args.get("appointment_id") else None
        return await tool_cancel_appointment(db, patient.id, appt_id)
    if tool == "reschedule_alternatives":
        appt_id = UUID(args["appointment_id"]) if args.get("appointment_id") else None
        return await tool_reschedule_alternatives(db, patient.id, appt_id)
    if tool == "reschedule_appointment":
        return await tool_reschedule(
            db, patient.id, patient.user_id, UUID(args["appointment_id"]), args["slot"]
        )
    if tool == "request_refill":
        return await tool_request_refill(db, patient.id, patient.user_id, args.get("medication_name"))
    if tool == "assess_symptoms":
        return await tool_assess_symptoms(
            db,
            patient.id,
            args.get("symptoms", []),
            args.get("duration"),
            patient_ctx.get("conditions", []),
            conversation_id,
            collected=args.get("collected") or args.get("summary"),
        )
    if tool == "schedule_reminder":
        return await tool_schedule_reminder(db, patient.user_id, UUID(args["appointment_id"]))
    if tool == "list_reports":
        return await tool_list_reports(db, patient.id)
    if tool == "get_report_analysis":
        return await tool_get_report_analysis(db, patient.id, UUID(args["report_id"]))
    if tool == "analyze_report":
        return await tool_analyze_report(db, patient.id, UUID(args["report_id"]))
    if tool == "save_memory":
        return await tool_save_memory(db, patient.id, args.get("fact", ""), conversation_id)
    if tool == "retrieve_evidence":
        if patient is None:
            return {"chunks": [], "citations": []}
        return await tool_retrieve_evidence(db, patient.id, args)
    return {"error": f"Unknown tool: {tool}"}
