"""Clinical consultation API — doctor workflow + patient health records (all visit modes)."""
from __future__ import annotations

import logging
import os
import shutil
import time
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, get_current_user, get_doctor_profile, get_patient_profile, get_settings
from app.models import Appointment, Consultation, Doctor, Patient, User
from app.schemas.common import ResponseEnvelope
from app.schemas.consultation import CompleteConsultationIn, ConsultationDraftIn
from app.services.consultation_ai_service import (
    generate_clinical_suggestions,
    generate_suggestions_from_transcript,
)
from app.schemas.transcript import TranscriptSegmentIn
from app.services.consultation_transcript_service import (
    add_transcript_segment,
    get_patient_transcript_for_appointment,
    get_transcript_snapshot,
    ingest_audio_chunk,
    start_transcript_session,
    stop_transcript_session,
)
from app.services.consultation_service import (
    complete_consultation,
    get_consultation_prep,
    get_patient_consultation_detail,
    list_patient_consultations,
    save_consultation_draft,
    start_consultation,
)
from app.services.stt_service import get_transcript_stt_config, transcribe_audio_chunk
from app.services.lab_catalog_service import list_active_lab_catalog
from app.services.video_consultation_service import get_doctor_video_session

logger = logging.getLogger(__name__)
router = APIRouter(tags=["consultations"])


@router.get("/doctor/lab-catalog")
async def doctor_lab_catalog(
    doctor: Doctor = Depends(get_doctor_profile),
    db: AsyncSession = Depends(get_db),
):
    """Active orderable lab tests for consultations."""
    data = await list_active_lab_catalog(db)
    return ResponseEnvelope(data=data)


@router.get("/doctor/appointments/{appointment_id}/consultation-prep")
async def doctor_consultation_prep(
    appointment_id: UUID,
    doctor: Doctor = Depends(get_doctor_profile),
    db: AsyncSession = Depends(get_db),
):
    data = await get_consultation_prep(db, appointment_id, doctor.id)
    return ResponseEnvelope(data=data)


@router.post("/doctor/appointments/{appointment_id}/consultation/start")
async def doctor_start_consultation(
    appointment_id: UUID,
    doctor: Doctor = Depends(get_doctor_profile),
    db: AsyncSession = Depends(get_db),
):
    data = await start_consultation(db, appointment_id, doctor.id)
    return ResponseEnvelope(data=data)


@router.post("/doctor/appointments/{appointment_id}/video")
async def doctor_start_video_consultation(
    appointment_id: UUID,
    doctor: Doctor = Depends(get_doctor_profile),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await get_doctor_video_session(
        db,
        appointment_id,
        doctor.id,
        user.id,
        doctor_name=user.name,
    )
    return ResponseEnvelope(data=data)


@router.get("/doctor/appointments/{appointment_id}/video")
async def doctor_get_video_consultation(
    appointment_id: UUID,
    doctor: Doctor = Depends(get_doctor_profile),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = await get_doctor_video_session(
        db,
        appointment_id,
        doctor.id,
        user.id,
        doctor_name=user.name,
    )
    return ResponseEnvelope(data=data)


@router.put("/doctor/appointments/{appointment_id}/consultation")
async def doctor_save_consultation_draft(
    appointment_id: UUID,
    body: ConsultationDraftIn,
    doctor: Doctor = Depends(get_doctor_profile),
    db: AsyncSession = Depends(get_db),
):
    data = await save_consultation_draft(db, appointment_id, doctor.id, body)
    return ResponseEnvelope(data=data)


@router.post("/doctor/appointments/{appointment_id}/consultation/ai-suggestions")
async def doctor_ai_suggestions(
    appointment_id: UUID,
    doctor: Doctor = Depends(get_doctor_profile),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import select

    appt = await db.get(Appointment, appointment_id)
    if not appt or appt.doctor_id != doctor.id:
        raise HTTPException(status_code=404, detail="Appointment not found")

    result = await db.execute(
        select(Consultation).where(Consultation.appointment_id == appointment_id)
    )
    consultation = result.scalar_one_or_none()
    if not consultation:
        raise HTTPException(status_code=400, detail="Start consultation first")

    patient = await db.get(Patient, appt.patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    user = await db.get(User, doctor.user_id)
    doctor_name = user.name if user else "Doctor"
    data = await generate_clinical_suggestions(db, consultation, patient, doctor_name)
    return ResponseEnvelope(data=data)


@router.get("/doctor/transcript/health")
async def doctor_transcript_health(
    doctor: Doctor = Depends(get_doctor_profile),
):
    """STT readiness for the voice transcript test page (no PHI)."""
    del doctor
    settings = get_settings()
    ffmpeg = shutil.which("ffmpeg") or shutil.which(os.environ.get("FFMPEG_PATH", "ffmpeg"))
    stt = get_transcript_stt_config()
    return ResponseEnvelope(
        data={
            "transcript_enabled": settings.transcript_enabled,
            **stt,
            "ffmpeg_available": bool(ffmpeg),
        }
    )


@router.post("/doctor/transcript/transcribe")
async def doctor_transcript_transcribe(
    doctor: Doctor = Depends(get_doctor_profile),
    file: UploadFile = File(...),
):
    """Transcribe a mic recording directly — no appointment session required."""
    del doctor
    if not get_settings().transcript_enabled:
        raise HTTPException(status_code=503, detail="Transcription is disabled.")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty audio file.")

    started = time.perf_counter()
    stt = await transcribe_audio_chunk(
        data,
        filename=file.filename or "recording.webm",
        mime_type=file.content_type or "audio/webm",
        include_debug=True,
    )
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    text = (stt.get("text") or "").strip()

    return ResponseEnvelope(
        data={
            "stt_config": get_transcript_stt_config(),
            "bytes": len(data),
            "mime_type": file.content_type or "audio/webm",
            "text": text,
            "confidence": stt.get("confidence"),
            "error": stt.get("error"),
            "no_speech": not text and not stt.get("error"),
            "elapsed_ms": elapsed_ms,
            "debug": stt.get("debug"),
        }
    )


@router.post("/doctor/appointments/{appointment_id}/transcript/start")
async def doctor_start_transcript(
    appointment_id: UUID,
    doctor: Doctor = Depends(get_doctor_profile),
    db: AsyncSession = Depends(get_db),
    room_id: str | None = Query(None),
):
    if not get_settings().transcript_enabled:
        raise HTTPException(status_code=503, detail="Transcription is disabled.")
    data = await start_transcript_session(db, appointment_id, doctor.id, room_id=room_id)
    await db.commit()
    return ResponseEnvelope(data=data)


@router.post("/doctor/appointments/{appointment_id}/transcript/chunk")
async def doctor_transcript_chunk(
    appointment_id: UUID,
    doctor: Doctor = Depends(get_doctor_profile),
    db: AsyncSession = Depends(get_db),
    file: UploadFile = File(...),
    speaker_role: str = Form("unknown"),
    speaker_label: str | None = Form(None),
):
    if not get_settings().transcript_enabled:
        raise HTTPException(status_code=503, detail="Transcription is disabled.")
    data = await ingest_audio_chunk(
        db,
        appointment_id,
        doctor.id,
        file,
        speaker_role=speaker_role,
        speaker_label=speaker_label,
    )
    await db.commit()
    return ResponseEnvelope(data=data)


@router.post("/doctor/appointments/{appointment_id}/transcript/segment")
async def doctor_transcript_segment(
    appointment_id: UUID,
    body: TranscriptSegmentIn,
    doctor: Doctor = Depends(get_doctor_profile),
    db: AsyncSession = Depends(get_db),
):
    if not get_settings().transcript_enabled:
        raise HTTPException(status_code=503, detail="Transcription is disabled.")
    data = await add_transcript_segment(
        db,
        appointment_id,
        doctor.id,
        text=body.text,
        speaker_role=body.speaker_role,
        speaker_label=body.speaker_label,
        confidence=body.confidence,
        is_final=body.is_final,
    )
    await db.commit()
    return ResponseEnvelope(data=data)


@router.post("/doctor/appointments/{appointment_id}/transcript/stop")
async def doctor_stop_transcript(
    appointment_id: UUID,
    doctor: Doctor = Depends(get_doctor_profile),
    db: AsyncSession = Depends(get_db),
):
    data = await stop_transcript_session(db, appointment_id, doctor.id)
    await db.commit()
    return ResponseEnvelope(data=data)


@router.get("/doctor/appointments/{appointment_id}/transcript")
async def doctor_get_transcript(
    appointment_id: UUID,
    doctor: Doctor = Depends(get_doctor_profile),
    db: AsyncSession = Depends(get_db),
    since_id: UUID | None = None,
):
    data = await get_transcript_snapshot(db, appointment_id, doctor.id, since_id=since_id)
    return ResponseEnvelope(data=data)


@router.post("/doctor/appointments/{appointment_id}/consultation/ai-from-transcript")
async def doctor_ai_from_transcript(
    appointment_id: UUID,
    doctor: Doctor = Depends(get_doctor_profile),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import select

    appt = await db.get(Appointment, appointment_id)
    if not appt or appt.doctor_id != doctor.id:
        raise HTTPException(status_code=404, detail="Appointment not found")

    result = await db.execute(
        select(Consultation).where(Consultation.appointment_id == appointment_id)
    )
    consultation = result.scalar_one_or_none()
    if not consultation:
        raise HTTPException(status_code=400, detail="Start consultation first")

    patient = await db.get(Patient, appt.patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    user = await db.get(User, doctor.user_id)
    doctor_name = user.name if user else "Doctor"
    try:
        data = await generate_suggestions_from_transcript(db, consultation, patient, doctor_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("ai-from-transcript failed for appointment %s", appointment_id)
        raise HTTPException(
            status_code=503,
            detail="Could not analyze transcript. Check LLM API keys (GROQ_API_KEY or GEMINI_API_KEY) and try again.",
        ) from exc
    return ResponseEnvelope(data=data)


@router.post("/doctor/appointments/{appointment_id}/complete-consultation")
async def doctor_complete_consultation(
    appointment_id: UUID,
    body: CompleteConsultationIn,
    doctor: Doctor = Depends(get_doctor_profile),
    db: AsyncSession = Depends(get_db),
):
    data = await complete_consultation(db, appointment_id, doctor.id, body)
    return ResponseEnvelope(data=data)


@router.get("/patients/me/consultations")
async def patient_list_consultations(
    patient: Patient = Depends(get_patient_profile),
    db: AsyncSession = Depends(get_db),
):
    data = await list_patient_consultations(db, patient.id)
    return ResponseEnvelope(data=data)


@router.get("/patients/me/consultations/{consultation_id}")
async def patient_consultation_detail(
    consultation_id: UUID,
    patient: Patient = Depends(get_patient_profile),
    db: AsyncSession = Depends(get_db),
):
    data = await get_patient_consultation_detail(db, patient.id, consultation_id)
    return ResponseEnvelope(data=data)


@router.get("/patients/me/appointments/{appointment_id}/transcript")
async def patient_appointment_transcript(
    appointment_id: UUID,
    patient: Patient = Depends(get_patient_profile),
    db: AsyncSession = Depends(get_db),
):
    data = await get_patient_transcript_for_appointment(db, appointment_id, patient.id)
    return ResponseEnvelope(data=data)
