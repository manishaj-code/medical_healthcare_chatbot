"""Live consultation transcript capture and retrieval."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Appointment, Consultation, ConsultationTranscriptSegment, ConsultationTranscriptSession
from app.services.stt_service import build_transcript_stt_payload, transcribe_audio_chunk


async def _latest_session(
    db: AsyncSession,
    consultation_id: UUID,
) -> ConsultationTranscriptSession | None:
    result = await db.execute(
        select(ConsultationTranscriptSession)
        .where(ConsultationTranscriptSession.consultation_id == consultation_id)
        .order_by(ConsultationTranscriptSession.started_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _segment_count(db: AsyncSession, session_id: UUID) -> int:
    result = await db.execute(
        select(func.count())
        .select_from(ConsultationTranscriptSegment)
        .where(ConsultationTranscriptSegment.session_id == session_id)
    )
    return int(result.scalar_one() or 0)


def _excerpt(text: str | None, limit: int = 280) -> str | None:
    if not text or not text.strip():
        return None
    cleaned = " ".join(text.split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"


def transcript_card_from_session(
    session: ConsultationTranscriptSession | None,
    *,
    segment_count: int = 0,
) -> dict:
    if not session:
        return {
            "has_transcript": False,
            "transcript_preview": None,
            "transcript_summary": None,
            "transcript_segment_count": 0,
            "transcript_session_id": None,
            "transcript_session_status": None,
        }

    insights = session.last_insights or {}
    summary = insights.get("transcript_summary")
    preview = _excerpt(session.full_transcript_text, 320)
    if not preview and summary:
        preview = _excerpt(str(summary), 320)

    has_transcript = bool(
        session.full_transcript_text
        or segment_count > 0
        or summary
    )
    return {
        "has_transcript": has_transcript,
        "transcript_preview": preview,
        "transcript_summary": summary,
        "transcript_segment_count": segment_count,
        "transcript_session_id": str(session.id),
        "transcript_session_status": session.status,
    }


async def load_transcript_cards_by_consultation_ids(
    db: AsyncSession,
    consultation_ids: list[UUID],
) -> dict[str, dict]:
    if not consultation_ids:
        return {}

    session_rows = await db.execute(
        select(ConsultationTranscriptSession)
        .where(ConsultationTranscriptSession.consultation_id.in_(consultation_ids))
        .order_by(ConsultationTranscriptSession.started_at.desc())
    )
    latest_by_consultation: dict[str, ConsultationTranscriptSession] = {}
    for session in session_rows.scalars().all():
        key = str(session.consultation_id)
        if key not in latest_by_consultation:
            latest_by_consultation[key] = session

    session_ids = [s.id for s in latest_by_consultation.values()]
    counts: dict[UUID, int] = {}
    if session_ids:
        count_rows = await db.execute(
            select(
                ConsultationTranscriptSegment.session_id,
                func.count(ConsultationTranscriptSegment.id),
            )
            .where(ConsultationTranscriptSegment.session_id.in_(session_ids))
            .group_by(ConsultationTranscriptSegment.session_id)
        )
        counts = {row[0]: int(row[1]) for row in count_rows.all()}

    return {
        cid: transcript_card_from_session(
            session,
            segment_count=counts.get(session.id, 0),
        )
        for cid, session in latest_by_consultation.items()
    }


async def get_transcript_prep_payload(
    db: AsyncSession,
    consultation_id: UUID,
    *,
    segment_limit: int = 100,
) -> dict:
    session = await _latest_session(db, consultation_id)
    if not session:
        return {
            "session": None,
            "segments": [],
            "has_transcript": False,
            "transcript_preview": None,
            "transcript_summary": None,
            "transcript_segment_count": 0,
        }

    seg_result = await db.execute(
        select(ConsultationTranscriptSegment)
        .where(ConsultationTranscriptSegment.session_id == session.id)
        .order_by(ConsultationTranscriptSegment.created_at)
        .limit(segment_limit)
    )
    segments = [_segment_payload(s) for s in seg_result.scalars().all()]
    segment_count = await _segment_count(db, session.id)
    card = transcript_card_from_session(session, segment_count=segment_count)
    return {
        "session": _session_payload(session),
        "segments": segments,
        **card,
    }


async def list_patient_video_transcripts(
    db: AsyncSession,
    doctor_id: UUID,
    patient_id: UUID,
) -> list[dict]:
    from app.models import Appointment
    from app.services.appointment_service import appointment_supports_video_call, format_apt_id

    appt_rows = await db.execute(
        select(Appointment, Consultation)
        .outerjoin(Consultation, Consultation.appointment_id == Appointment.id)
        .where(
            Appointment.doctor_id == doctor_id,
            Appointment.patient_id == patient_id,
        )
        .order_by(Appointment.slot_date.desc(), Appointment.slot_time.desc())
    )

    items: list[dict] = []
    consultation_ids: list[UUID] = []
    row_meta: list[tuple] = []

    for appt, consultation in appt_rows.all():
        if not appointment_supports_video_call(appt):
            continue
        consultation_id = consultation.id if consultation else None
        if consultation_id:
            consultation_ids.append(consultation_id)
        row_meta.append((appt, consultation_id))

    cards = await load_transcript_cards_by_consultation_ids(db, consultation_ids)

    for appt, consultation_id in row_meta:
        status = appt.status.value if hasattr(appt.status, "value") else str(appt.status)
        card = cards.get(str(consultation_id), transcript_card_from_session(None)) if consultation_id else transcript_card_from_session(None)
        items.append(
            {
                "appointment_id": str(appt.id),
                "apt_id": format_apt_id(appt.id),
                "date": str(appt.slot_date),
                "time": str(appt.slot_time),
                "status": status,
                **card,
            }
        )
    return items


async def get_patient_transcript_for_appointment(
    db: AsyncSession,
    appointment_id: UUID,
    patient_id: UUID,
    *,
    segment_limit: int = 200,
) -> dict:
    appt = await db.get(Appointment, appointment_id)
    if not appt or appt.patient_id != patient_id:
        raise HTTPException(status_code=404, detail="Appointment not found")

    result = await db.execute(
        select(Consultation).where(Consultation.appointment_id == appointment_id)
    )
    consultation = result.scalar_one_or_none()
    if not consultation:
        return {
            "session": None,
            "segments": [],
            "has_transcript": False,
            "transcript_preview": None,
            "transcript_summary": None,
            "transcript_segment_count": 0,
        }

    payload = await get_transcript_prep_payload(db, consultation.id, segment_limit=segment_limit)
    return payload


async def stop_transcript_for_consultation(
    db: AsyncSession,
    consultation_id: UUID,
) -> dict:
    """Finalize the active transcript session for a consultation (idempotent)."""
    session = await _active_session(db, consultation_id)
    if not session:
        return {"session": None, "stopped": False}

    await _rebuild_full_transcript(db, session)
    session.status = "completed"
    session.ended_at = datetime.now(timezone.utc)
    await db.flush()
    return {"session": _session_payload(session), "stopped": True}


async def _get_consultation_for_doctor(
    db: AsyncSession,
    appointment_id: UUID,
    doctor_id: UUID,
) -> tuple[Appointment, Consultation]:
    appt = await db.get(Appointment, appointment_id)
    if not appt or appt.doctor_id != doctor_id:
        raise HTTPException(status_code=404, detail="Appointment not found")

    result = await db.execute(
        select(Consultation).where(Consultation.appointment_id == appointment_id)
    )
    consultation = result.scalar_one_or_none()
    if not consultation:
        raise HTTPException(status_code=400, detail="Start consultation before enabling transcript.")
    return appt, consultation


async def _active_session(
    db: AsyncSession,
    consultation_id: UUID,
) -> ConsultationTranscriptSession | None:
    result = await db.execute(
        select(ConsultationTranscriptSession)
        .where(
            ConsultationTranscriptSession.consultation_id == consultation_id,
            ConsultationTranscriptSession.status == "active",
        )
        .order_by(ConsultationTranscriptSession.started_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def _session_payload(session: ConsultationTranscriptSession) -> dict:
    return {
        "id": session.id,
        "consultation_id": session.consultation_id,
        "appointment_id": session.appointment_id,
        "room_id": session.room_id,
        "status": session.status,
        "full_transcript_text": session.full_transcript_text,
        "last_insights": session.last_insights,
        "started_at": session.started_at,
        "ended_at": session.ended_at,
    }


def _segment_payload(segment: ConsultationTranscriptSegment) -> dict:
    return {
        "id": segment.id,
        "speaker_role": segment.speaker_role,
        "speaker_label": segment.speaker_label,
        "text": segment.text,
        "confidence": segment.confidence,
        "start_ms": segment.start_ms,
        "end_ms": segment.end_ms,
        "is_final": segment.is_final,
        "created_at": segment.created_at,
    }


async def start_transcript_session(
    db: AsyncSession,
    appointment_id: UUID,
    doctor_id: UUID,
    *,
    room_id: str | None = None,
    consent: bool = True,
) -> dict:
    _appt, consultation = await _get_consultation_for_doctor(db, appointment_id, doctor_id)

    stt = await build_transcript_stt_payload()

    existing = await _active_session(db, consultation.id)
    if existing:
        return {"session": _session_payload(existing), "resumed": True, "stt": stt}

    session = ConsultationTranscriptSession(
        consultation_id=consultation.id,
        appointment_id=appointment_id,
        room_id=room_id,
        status="active",
        consent_recorded_at=datetime.now(timezone.utc) if consent else None,
    )
    db.add(session)
    await db.flush()
    return {"session": _session_payload(session), "resumed": False, "stt": stt}


async def ingest_audio_chunk(
    db: AsyncSession,
    appointment_id: UUID,
    doctor_id: UUID,
    file: UploadFile,
    *,
    speaker_role: str = "unknown",
    speaker_label: str | None = None,
) -> dict:
    _appt, consultation = await _get_consultation_for_doctor(db, appointment_id, doctor_id)
    session = await _active_session(db, consultation.id)
    if not session:
        raise HTTPException(status_code=400, detail="Transcript session not started.")

    data = await file.read()
    if not data or len(data) < 1500:
        return {"segment": None, "skipped": True}

    stt = await transcribe_audio_chunk(
        data,
        filename=file.filename or "chunk.webm",
        mime_type=file.content_type or "audio/webm",
    )
    text = (stt.get("text") or "").strip()
    if not text:
        return {"segment": None, "skipped": True, "reason": "no_speech", "bytes": len(data)}

    role = speaker_role if speaker_role in ("doctor", "patient", "unknown") else "unknown"
    label = speaker_label or (
        "Doctor" if role == "doctor" else "Patient" if role == "patient" else "Discussion"
    )

    last_result = await db.execute(
        select(ConsultationTranscriptSegment)
        .where(ConsultationTranscriptSegment.session_id == session.id)
        .order_by(ConsultationTranscriptSegment.created_at.desc())
        .limit(1)
    )
    last_segment = last_result.scalar_one_or_none()
    if last_segment and last_segment.text.strip().lower() == text.lower():
        return {"segment": None, "skipped": True}

    segment = ConsultationTranscriptSegment(
        session_id=session.id,
        speaker_role=role,
        speaker_label=label,
        text=text,
        confidence=stt.get("confidence"),
        is_final=True,
    )
    db.add(segment)
    await db.flush()
    await _rebuild_full_transcript(db, session)
    await db.flush()
    return {"segment": _segment_payload(segment), "skipped": False}


async def add_transcript_segment(
    db: AsyncSession,
    appointment_id: UUID,
    doctor_id: UUID,
    *,
    text: str,
    speaker_role: str = "unknown",
    speaker_label: str | None = None,
    confidence: float | None = None,
    is_final: bool = True,
) -> dict:
    """Insert a transcript segment (Deepgram live or manual fallback)."""
    _appt, consultation = await _get_consultation_for_doctor(db, appointment_id, doctor_id)
    session = await _active_session(db, consultation.id)
    if not session:
        raise HTTPException(status_code=400, detail="Transcript session not started.")

    cleaned = text.strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="Empty transcript text.")

    if not is_final:
        return {"segment": None, "skipped": True}

    role = speaker_role if speaker_role in ("doctor", "patient", "unknown") else "unknown"
    label = speaker_label or (
        "Doctor" if role == "doctor" else "Patient" if role == "patient" else "Discussion"
    )

    last_result = await db.execute(
        select(ConsultationTranscriptSegment)
        .where(ConsultationTranscriptSegment.session_id == session.id)
        .order_by(ConsultationTranscriptSegment.created_at.desc())
        .limit(1)
    )
    last_segment = last_result.scalar_one_or_none()
    if last_segment and last_segment.text.strip().lower() == cleaned.lower():
        return {"segment": _segment_payload(last_segment), "skipped": True}

    segment = ConsultationTranscriptSegment(
        session_id=session.id,
        speaker_role=role,
        speaker_label=label,
        text=cleaned,
        confidence=confidence,
        is_final=True,
    )
    db.add(segment)
    await db.flush()
    await _rebuild_full_transcript(db, session)
    await db.flush()
    return {"segment": _segment_payload(segment)}


async def _rebuild_full_transcript(db: AsyncSession, session: ConsultationTranscriptSession) -> None:
    result = await db.execute(
        select(ConsultationTranscriptSegment)
        .where(ConsultationTranscriptSegment.session_id == session.id)
        .order_by(ConsultationTranscriptSegment.created_at)
    )
    lines: list[str] = []
    for row in result.scalars().all():
        label = row.speaker_label or row.speaker_role.title()
        lines.append(f"{label}: {row.text}")
    session.full_transcript_text = "\n".join(lines) if lines else None


async def stop_transcript_session(
    db: AsyncSession,
    appointment_id: UUID,
    doctor_id: UUID,
) -> dict:
    _appt, consultation = await _get_consultation_for_doctor(db, appointment_id, doctor_id)
    return await stop_transcript_for_consultation(db, consultation.id)


async def get_transcript_snapshot(
    db: AsyncSession,
    appointment_id: UUID,
    doctor_id: UUID,
    *,
    since_id: UUID | None = None,
) -> dict:
    _appt, consultation = await _get_consultation_for_doctor(db, appointment_id, doctor_id)

    session_result = await db.execute(
        select(ConsultationTranscriptSession)
        .where(ConsultationTranscriptSession.consultation_id == consultation.id)
        .order_by(ConsultationTranscriptSession.started_at.desc())
        .limit(1)
    )
    session = session_result.scalar_one_or_none()
    if not session:
        return {"session": None, "segments": []}

    query = (
        select(ConsultationTranscriptSegment)
        .where(ConsultationTranscriptSegment.session_id == session.id)
        .order_by(ConsultationTranscriptSegment.created_at)
    )
    if since_id:
        since_seg = await db.get(ConsultationTranscriptSegment, since_id)
        if since_seg:
            query = query.where(ConsultationTranscriptSegment.created_at > since_seg.created_at)

    seg_result = await db.execute(query)
    segments = [_segment_payload(s) for s in seg_result.scalars().all()]
    return {"session": _session_payload(session), "segments": segments}


async def get_full_transcript_text(db: AsyncSession, consultation_id: UUID) -> str:
    session_result = await db.execute(
        select(ConsultationTranscriptSession)
        .where(ConsultationTranscriptSession.consultation_id == consultation_id)
        .order_by(ConsultationTranscriptSession.started_at.desc())
        .limit(1)
    )
    session = session_result.scalar_one_or_none()
    if not session:
        return ""
    if session.full_transcript_text:
        return session.full_transcript_text

    result = await db.execute(
        select(ConsultationTranscriptSegment)
        .where(ConsultationTranscriptSegment.session_id == session.id)
        .order_by(ConsultationTranscriptSegment.created_at)
    )
    lines = [
        f"{row.speaker_label or row.speaker_role}: {row.text}"
        for row in result.scalars().all()
    ]
    return "\n".join(lines)


async def save_transcript_insights(
    db: AsyncSession,
    consultation_id: UUID,
    insights: dict,
) -> None:
    session_result = await db.execute(
        select(ConsultationTranscriptSession)
        .where(ConsultationTranscriptSession.consultation_id == consultation_id)
        .order_by(ConsultationTranscriptSession.started_at.desc())
        .limit(1)
    )
    session = session_result.scalar_one_or_none()
    if session:
        session.last_insights = insights
        await db.flush()
