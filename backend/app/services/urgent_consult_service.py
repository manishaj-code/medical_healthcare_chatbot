"""Urgent tele-consult: broadcast to doctors, first accept wins."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, time, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Appointment,
    Doctor,
    Notification,
    Patient,
    UrgentConsultOffer,
    UrgentConsultRequest,
    User,
)
from app.models.enums import (
    AppointmentStatus,
    NotificationType,
    UrgentConsultOfferStatus,
    UrgentConsultRequestStatus,
)
from app.services.agent_tools import tool_search_doctors
from app.services.appointment_service import format_apt_id
from app.services.video_consultation_service import (
    build_join_url,
    enable_video_consultation,
    video_room_id_for_appointment,
)

logger = logging.getLogger(__name__)

URGENT_CONSULT_TTL_MINUTES = 15


def _round_up_time(now: datetime) -> time:
    minute = ((now.minute // 5) + 1) * 5
    hour = now.hour
    if minute >= 60:
        minute = 0
        hour = (hour + 1) % 24
    return time(hour=hour, minute=minute)


def _doctor_summary(doc: dict) -> dict:
    return {
        "id": doc["id"],
        "name": doc["name"],
        "specialty": doc.get("specialty") or "General Physician",
        "rating": doc.get("rating"),
        "experience_years": doc.get("experience_years"),
        "profile_image_url": doc.get("profile_image_url"),
        "hospital_name": doc.get("hospital_name"),
    }


async def _book_urgent_appointment(
    db: AsyncSession,
    patient_id: UUID,
    doctor_id: UUID,
    patient_user_id: UUID,
) -> Appointment:
    now = datetime.now(timezone.utc)
    appt = Appointment(
        patient_id=patient_id,
        doctor_id=doctor_id,
        slot_date=now.date(),
        slot_time=_round_up_time(now),
        status=AppointmentStatus.confirmed,
        consultation_mode="video",
    )
    db.add(appt)
    await db.flush()
    appt.video_room_id = video_room_id_for_appointment(appt.id)
    appt.video_enabled_at = now
    db.add(
        Notification(
            user_id=patient_user_id,
            type=NotificationType.booking_confirmation,
            message=f"Urgent video consultation confirmed ({format_apt_id(appt.id)}).",
        )
    )
    await db.flush()
    return appt


def serialize_request(
    request: UrgentConsultRequest,
    *,
    doctors: list[dict] | None = None,
    accepted_doctor_name: str | None = None,
    join_url: str | None = None,
    appointment_id: str | None = None,
) -> dict:
    data = {
        "id": str(request.id),
        "status": request.status,
        "specialty": request.specialty,
        "risk_level": request.risk_level,
        "symptoms": list(request.symptoms_json or []),
        "expires_at": request.expires_at.isoformat() if request.expires_at else None,
        "assigned_at": request.assigned_at.isoformat() if request.assigned_at else None,
        "accepted_doctor_id": str(request.accepted_doctor_id) if request.accepted_doctor_id else None,
        "accepted_doctor_name": accepted_doctor_name,
        "appointment_id": appointment_id or (str(request.appointment_id) if request.appointment_id else None),
        "apt_id": format_apt_id(request.appointment_id) if request.appointment_id else None,
        "join_url": join_url,
        "doctors": doctors or [],
    }
    return data


def _patient_profile_dict(patient: Patient, user: User) -> dict:
    return {
        "patient_id": str(patient.id),
        "patient_name": user.name,
        "patient_email": user.email,
        "patient_phone": patient.phone,
        "patient_dob": str(patient.dob) if patient.dob else None,
        "patient_gender": patient.gender,
        "patient_blood_group": patient.blood_group,
    }


async def _build_doctor_urgent_item(
    db: AsyncSession,
    offer: UrgentConsultOffer,
    request: UrgentConsultRequest,
    patient: Patient,
    user: User,
    *,
    doctor_id: UUID,
) -> dict:
    accepted_name = None
    if request.accepted_doctor_id:
        accepted_name = await _doctor_name(db, request.accepted_doctor_id)
    now = datetime.now(timezone.utc)
    item = {
        "offer_id": str(offer.id),
        "request_id": str(request.id),
        "offer_status": offer.status,
        "request_status": request.status,
        "symptoms": list(request.symptoms_json or []),
        "specialty": request.specialty,
        "risk_level": request.risk_level,
        "patient_message": request.patient_message,
        "created_at": request.created_at.isoformat() if request.created_at else None,
        "notified_at": offer.notified_at.isoformat() if offer.notified_at else None,
        "responded_at": offer.responded_at.isoformat() if offer.responded_at else None,
        "expires_at": request.expires_at.isoformat() if request.expires_at else None,
        "assigned_at": request.assigned_at.isoformat() if request.assigned_at else None,
        "accepted_doctor_name": accepted_name,
        "appointment_id": str(request.appointment_id) if request.appointment_id else None,
        "apt_id": format_apt_id(request.appointment_id) if request.appointment_id else None,
        "can_accept": (
            offer.status == UrgentConsultOfferStatus.notified.value
            and request.status == UrgentConsultRequestStatus.pending.value
            and request.expires_at > now
        ),
        **_patient_profile_dict(patient, user),
    }
    return item


async def _get_active_pending_request(
    db: AsyncSession,
    patient_id: UUID,
    *,
    conversation_id: UUID | None = None,
) -> UrgentConsultRequest | None:
    """Return the patient's current non-expired pending urgent request, if any."""
    now = datetime.now(timezone.utc)
    query = (
        select(UrgentConsultRequest)
        .where(
            UrgentConsultRequest.patient_id == patient_id,
            UrgentConsultRequest.status == UrgentConsultRequestStatus.pending.value,
            UrgentConsultRequest.expires_at > now,
        )
        .order_by(UrgentConsultRequest.created_at.desc())
        .limit(1)
    )
    if conversation_id is not None:
        query = query.where(UrgentConsultRequest.conversation_id == conversation_id)
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def _payload_for_request(db: AsyncSession, request: UrgentConsultRequest) -> dict:
    doctors = await _notified_doctors_for_request(db, request.id)
    return serialize_request(request, doctors=doctors)


async def create_urgent_request(
    db: AsyncSession,
    patient: Patient,
    conversation_id: UUID | None,
    *,
    symptoms: list[str],
    specialty: str,
    risk_level: str,
    patient_message: str,
) -> dict:
    existing = await _get_active_pending_request(db, patient.id)
    if existing:
        return await _payload_for_request(db, existing)

    now = datetime.now(timezone.utc)
    request = UrgentConsultRequest(
        patient_id=patient.id,
        conversation_id=conversation_id,
        symptoms_json=symptoms,
        specialty=specialty,
        risk_level=risk_level,
        status=UrgentConsultRequestStatus.pending.value,
        patient_message=patient_message,
        expires_at=now + timedelta(minutes=URGENT_CONSULT_TTL_MINUTES),
    )
    db.add(request)
    await db.flush()

    search = await tool_search_doctors(db, specialty)
    doctors = search.get("doctors") or []
    if not doctors:
        from app.services.doctor_service import list_doctors_with_availability

        doctors = await list_doctors_with_availability(
            db, specialty=specialty, include_without_slots=True, slots_per_doctor=1
        )

    notified: list[dict] = []
    for doc in doctors[:12]:
        doctor_id = UUID(str(doc["id"]))
        doctor_row = await db.get(Doctor, doctor_id)
        if not doctor_row:
            continue
        offer = UrgentConsultOffer(
            request_id=request.id,
            doctor_id=doctor_id,
            status=UrgentConsultOfferStatus.notified.value,
        )
        db.add(offer)
        symptom_text = ", ".join(symptoms[:3]) if symptoms else "urgent symptoms"
        db.add(
            Notification(
                user_id=doctor_row.user_id,
                type=NotificationType.urgent_consult_request,
                message=(
                    f"🚨 Urgent consult request: patient reports {symptom_text}. "
                    f"Tap Accept to start immediate video consultation."
                ),
            )
        )
        notified.append(_doctor_summary(doc))

    await db.flush()
    return serialize_request(request, doctors=notified)


async def get_request_for_patient(
    db: AsyncSession,
    patient_id: UUID,
    request_id: UUID,
) -> dict:
    request = await _load_request(db, request_id)
    if request.patient_id != patient_id:
        raise HTTPException(status_code=404, detail="Urgent consult request not found")

    accepted_name = None
    join_url = None
    appointment_id = None
    doctors = await _notified_doctors_for_request(db, request.id)

    if request.status == UrgentConsultRequestStatus.assigned.value and request.appointment_id:
        appointment_id = str(request.appointment_id)
        if request.accepted_doctor_id:
            accepted_name = await _doctor_name(db, request.accepted_doctor_id)
        patient = await db.get(Patient, patient_id)
        user = await db.get(User, patient.user_id) if patient else None
        appt = await db.get(Appointment, request.appointment_id)
        if appt and appt.video_room_id and user:
            join_url = build_join_url(appt.video_room_id, user.name.split()[0])

    return serialize_request(
        request,
        doctors=doctors,
        accepted_doctor_name=accepted_name,
        join_url=join_url,
        appointment_id=appointment_id,
    )


async def list_pending_for_doctor(db: AsyncSession, doctor_id: UUID) -> list[dict]:
    """Actionable urgent consults this doctor can still accept."""
    now = datetime.now(timezone.utc)
    rows = await db.execute(
        select(UrgentConsultOffer, UrgentConsultRequest, Patient, User)
        .join(UrgentConsultRequest, UrgentConsultRequest.id == UrgentConsultOffer.request_id)
        .join(Patient, Patient.id == UrgentConsultRequest.patient_id)
        .join(User, User.id == Patient.user_id)
        .where(
            UrgentConsultOffer.doctor_id == doctor_id,
            UrgentConsultOffer.status == UrgentConsultOfferStatus.notified.value,
            UrgentConsultRequest.status == UrgentConsultRequestStatus.pending.value,
            UrgentConsultRequest.expires_at > now,
        )
        .order_by(UrgentConsultRequest.created_at.desc())
    )
    items: list[dict] = []
    seen_requests: set[str] = set()
    for offer, request, patient, user in rows.all():
        request_key = str(request.id)
        if request_key in seen_requests:
            continue
        seen_requests.add(request_key)
        items.append(
            await _build_doctor_urgent_item(
                db, offer, request, patient, user, doctor_id=doctor_id
            )
        )
    return items


_HISTORY_BUCKETS: dict[str, list[str]] = {
    "attended": [UrgentConsultOfferStatus.accepted.value],
    "declined": [UrgentConsultOfferStatus.declined.value],
    "missed": [UrgentConsultOfferStatus.superseded.value],
}


async def list_urgent_consult_history_for_doctor(
    db: AsyncSession,
    doctor_id: UUID,
    *,
    bucket: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """Audit history — patients this doctor attended, declined, or missed."""
    offer_statuses: list[str] = []
    if bucket:
        offer_statuses = _HISTORY_BUCKETS.get(bucket, [])
        if not offer_statuses:
            raise HTTPException(status_code=400, detail="Invalid history bucket.")
    else:
        for statuses in _HISTORY_BUCKETS.values():
            offer_statuses.extend(statuses)

    rows = await db.execute(
        select(UrgentConsultOffer, UrgentConsultRequest, Patient, User)
        .join(UrgentConsultRequest, UrgentConsultRequest.id == UrgentConsultOffer.request_id)
        .join(Patient, Patient.id == UrgentConsultRequest.patient_id)
        .join(User, User.id == Patient.user_id)
        .where(
            UrgentConsultOffer.doctor_id == doctor_id,
            UrgentConsultOffer.status.in_(offer_statuses),
        )
        .order_by(
            UrgentConsultOffer.responded_at.desc().nullslast(),
            UrgentConsultRequest.created_at.desc(),
        )
        .limit(limit)
    )
    items: list[dict] = []
    for offer, request, patient, user in rows.all():
        item = await _build_doctor_urgent_item(
            db, offer, request, patient, user, doctor_id=doctor_id
        )
        item["history_bucket"] = next(
            (name for name, statuses in _HISTORY_BUCKETS.items() if offer.status in statuses),
            "other",
        )
        items.append(item)
    return items


async def accept_urgent_request(
    db: AsyncSession,
    doctor_id: UUID,
    request_id: UUID,
    *,
    doctor_user_id: UUID,
    doctor_name: str,
) -> dict:
    result = await db.execute(
        select(UrgentConsultRequest).where(UrgentConsultRequest.id == request_id).with_for_update()
    )
    request = result.scalar_one_or_none()
    if not request:
        raise HTTPException(status_code=404, detail="Urgent consult request not found")

    if request.expires_at <= datetime.now(timezone.utc):
        request.status = UrgentConsultRequestStatus.expired.value
        raise HTTPException(status_code=410, detail="This urgent consult request has expired.")

    offer_result = await db.execute(
        select(UrgentConsultOffer).where(
            UrgentConsultOffer.request_id == request_id,
            UrgentConsultOffer.doctor_id == doctor_id,
        )
    )
    offer = offer_result.scalar_one_or_none()
    if not offer:
        raise HTTPException(status_code=404, detail="You were not notified for this request.")

    if request.status != UrgentConsultRequestStatus.pending.value:
        assigned_name = await _doctor_name(db, request.accepted_doctor_id) if request.accepted_doctor_id else None
        raise HTTPException(
            status_code=409,
            detail=f"Already assigned to {assigned_name or 'another doctor'}.",
        )

    if offer.status == UrgentConsultOfferStatus.superseded.value:
        raise HTTPException(status_code=409, detail="Another doctor already accepted this request.")

    patient = await db.get(Patient, request.patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    now = datetime.now(timezone.utc)
    appt = await _book_urgent_appointment(db, patient.id, doctor_id, patient.user_id)
    request.status = UrgentConsultRequestStatus.assigned.value
    request.accepted_doctor_id = doctor_id
    request.appointment_id = appt.id
    request.assigned_at = now
    offer.status = UrgentConsultOfferStatus.accepted.value
    offer.responded_at = now

    other_offers = await db.execute(
        select(UrgentConsultOffer, Doctor).join(Doctor, Doctor.id == UrgentConsultOffer.doctor_id).where(
            UrgentConsultOffer.request_id == request_id,
            UrgentConsultOffer.id != offer.id,
            UrgentConsultOffer.status == UrgentConsultOfferStatus.notified.value,
        )
    )
    for other_offer, other_doctor in other_offers.all():
        other_offer.status = UrgentConsultOfferStatus.superseded.value
        other_offer.responded_at = now
        db.add(
            Notification(
                user_id=other_doctor.user_id,
                type=NotificationType.urgent_consult_superseded,
                message=(
                    f"Urgent consult request was assigned to {doctor_name}. "
                    "No further action needed."
                ),
            )
        )

    patient_user = await db.get(User, patient.user_id)
    patient_name = patient_user.name.split()[0] if patient_user and patient_user.name else "Patient"
    video = await enable_video_consultation(
        db,
        appt.id,
        patient.id,
        patient.user_id,
        patient_name=patient_name,
        bypass_time_window=True,
    )
    db.add(
        Notification(
            user_id=patient.user_id,
            type=NotificationType.urgent_consult_assigned,
            message=(
                f"✅ {doctor_name} accepted your urgent consultation. "
                "You can join the video call now."
            ),
        )
    )
    await db.flush()

    return {
        "success": True,
        "request": serialize_request(
            request,
            accepted_doctor_name=doctor_name,
            join_url=video.get("join_url"),
            appointment_id=str(appt.id),
        ),
        "appointment_id": str(appt.id),
        "apt_id": format_apt_id(appt.id),
        "doctor_name": doctor_name,
        "join_url": video.get("join_url"),
        "doctor_join_url": build_join_url(appt.video_room_id or "", doctor_name),
    }


async def decline_urgent_request(db: AsyncSession, doctor_id: UUID, request_id: UUID) -> dict:
    offer_result = await db.execute(
        select(UrgentConsultOffer).where(
            UrgentConsultOffer.request_id == request_id,
            UrgentConsultOffer.doctor_id == doctor_id,
        )
    )
    offer = offer_result.scalar_one_or_none()
    if not offer:
        raise HTTPException(status_code=404, detail="Offer not found")
    if offer.status != UrgentConsultOfferStatus.notified.value:
        return {"success": True, "status": offer.status}
    offer.status = UrgentConsultOfferStatus.declined.value
    offer.responded_at = datetime.now(timezone.utc)
    await db.flush()
    return {"success": True, "status": offer.status}


async def _load_request(db: AsyncSession, request_id: UUID) -> UrgentConsultRequest:
    request = await db.get(UrgentConsultRequest, request_id)
    if not request:
        raise HTTPException(status_code=404, detail="Urgent consult request not found")
    return request


async def _doctor_name(db: AsyncSession, doctor_id: UUID) -> str | None:
    doctor = await db.get(Doctor, doctor_id)
    if not doctor:
        return None
    user = await db.get(User, doctor.user_id)
    return user.name if user else None


async def _notified_doctors_for_request(db: AsyncSession, request_id: UUID) -> list[dict]:
    rows = await db.execute(
        select(UrgentConsultOffer, Doctor, User)
        .join(Doctor, Doctor.id == UrgentConsultOffer.doctor_id)
        .join(User, User.id == Doctor.user_id)
        .where(UrgentConsultOffer.request_id == request_id)
    )
    doctors: list[dict] = []
    for offer, doctor, user in rows.all():
        doctors.append(
            {
                "id": str(doctor.id),
                "name": user.name,
                "offer_status": offer.status,
            }
        )
    return doctors


async def complete_guest_resume_urgent_consult(
    db: AsyncSession,
    patient,
    conversation_id: UUID,
    session: dict,
) -> dict | None:
    """Create urgent consult request after guest verifies email in portal."""
    action = session.get("guest_resume_action") or session.get("pending_auth_action")
    if action != "urgent_consult":
        return None

    pending = session.get("pending_urgent_consult")
    existing_id = session.get("urgent_consult_request_id")
    active = await _get_active_pending_request(db, patient.id, conversation_id=conversation_id)
    if not session.get("resume_after_auth") and not pending and not existing_id and not active:
        return None

    from app.emergency_detection import build_urgent_consult_opener
    from app.services.chat_ui import build_urgent_consult_pending_ui

    if not pending:
        if existing_id:
            payload = await get_request_for_patient(db, patient.id, UUID(str(existing_id)))
        elif active:
            payload = await _payload_for_request(db, active)
            session["urgent_consult_request_id"] = payload["id"]
        else:
            return None
        reply = build_urgent_consult_opener(
            payload["specialty"],
            er_advisory=payload.get("risk_level") == "emergency",
            symptoms=payload.get("symptoms"),
        )
        for key in (
            "pending_urgent_consult",
            "pending_urgent_message",
            "awaiting",
            "resume_after_auth",
            "pending_auth_action",
            "guest_resume_action",
            "guest_email",
        ):
            session.pop(key, None)
        session.update({
            "care_goal": "urgent_consult",
            "skip_triage": True,
            "active_specialist": "scheduling_agent",
        })
        return {
            "reply": reply,
            "agent": "scheduling_agent",
            "emergency": payload.get("risk_level") == "emergency",
            "ui": build_urgent_consult_pending_ui(payload),
            "session": session,
        }

    payload = await create_urgent_request(
        db,
        patient,
        conversation_id,
        symptoms=pending.get("symptoms") or [],
        specialty=pending["specialty"],
        risk_level=pending.get("risk_level", "high"),
        patient_message=session.get("pending_urgent_message") or "",
    )

    reply = build_urgent_consult_opener(
        pending["specialty"],
        er_advisory=pending.get("er_advisory", True),
        symptoms=pending.get("symptoms"),
    )

    for key in (
        "pending_urgent_consult",
        "pending_urgent_message",
        "awaiting",
        "resume_after_auth",
        "pending_auth_action",
        "guest_resume_action",
        "guest_email",
    ):
        session.pop(key, None)
    session.update({
        "care_goal": "urgent_consult",
        "skip_triage": True,
        "urgent_consult_request_id": payload["id"],
        "active_specialist": "scheduling_agent",
        "recommended_specialty": pending["specialty"],
        "detected_symptoms": pending.get("symptoms") or [],
    })

    return {
        "reply": reply,
        "agent": "scheduling_agent",
        "emergency": pending.get("risk_level") == "emergency",
        "ui": build_urgent_consult_pending_ui(payload),
        "session": session,
    }
