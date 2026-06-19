"""Schemas for live consultation transcripts."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class TranscriptSegmentOut(BaseModel):
    id: UUID
    speaker_role: str
    speaker_label: str | None = None
    text: str
    confidence: float | None = None
    start_ms: int | None = None
    end_ms: int | None = None
    is_final: bool = True
    created_at: datetime


class TranscriptSessionOut(BaseModel):
    id: UUID
    consultation_id: UUID
    appointment_id: UUID
    room_id: str | None = None
    status: str
    full_transcript_text: str | None = None
    last_insights: dict | None = None
    started_at: datetime
    ended_at: datetime | None = None


class TranscriptSnapshotOut(BaseModel):
    session: TranscriptSessionOut | None = None
    segments: list[TranscriptSegmentOut] = Field(default_factory=list)


class TranscriptSegmentIn(BaseModel):
    text: str
    speaker_role: str = "unknown"
    speaker_label: str | None = None
    is_final: bool = True
    confidence: float | None = None


class TranscriptStartOut(BaseModel):
    session: TranscriptSessionOut
    resumed: bool = False
    stt: dict | None = None


class TranscriptInsightsOut(BaseModel):
    patient_concerns: list[str] = Field(default_factory=list)
    transcript_summary: str | None = None
    key_symptoms: list[str] = Field(default_factory=list)
