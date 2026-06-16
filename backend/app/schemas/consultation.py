"""Pydantic schemas for clinical consultation workflow."""
from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field


class PrescriptionItemIn(BaseModel):
    medicine_name: str = Field(min_length=1, max_length=255)
    strength: str | None = None
    frequency: str | None = None
    duration: str | None = None
    instructions: str | None = None
    source: str = "manual"


class LabOrderIn(BaseModel):
    test_code: str
    test_name: str
    notes: str | None = None


class ConsultationDraftIn(BaseModel):
    chief_complaint: str | None = None
    clinical_findings: str | None = None
    diagnosis: str | None = None
    doctor_notes: str | None = None
    treatment_plan: str | None = None
    follow_up_date: date | None = None
    prescription_items: list[PrescriptionItemIn] = Field(default_factory=list)
    lab_orders: list[LabOrderIn] = Field(default_factory=list)


class CompleteConsultationIn(ConsultationDraftIn):
    doctor_signature_name: str | None = None
    ai_suggestion_audit: list[dict] = Field(default_factory=list)


class PrescriptionItemOut(BaseModel):
    id: UUID
    medicine_name: str
    strength: str | None
    frequency: str | None
    duration: str | None
    instructions: str | None
    source: str


class LabOrderOut(BaseModel):
    id: UUID
    test_code: str
    test_name: str
    notes: str | None
    status: str


class ConsultationOut(BaseModel):
    id: UUID
    appointment_id: UUID
    patient_id: UUID
    doctor_id: UUID
    status: str
    consultation_mode: str
    chief_complaint: str | None
    clinical_findings: str | None
    diagnosis: str | None
    doctor_notes: str | None
    treatment_plan: str | None
    follow_up_date: date | None
    completed_at: datetime | None
    prescription_items: list[PrescriptionItemOut] = Field(default_factory=list)
    lab_orders: list[LabOrderOut] = Field(default_factory=list)


class LabCatalogOut(BaseModel):
    test_code: str
    test_name: str
    keywords: list[str] = Field(default_factory=list)
    category: str | None = None
    description: str | None = None
    sort_order: int = 0


class AiSuggestionsOut(BaseModel):
    batch_id: UUID
    differential_considerations: list[str] = Field(default_factory=list)
    suggested_investigations: list[str] = Field(default_factory=list)
    matched_catalog_tests: list[LabCatalogOut] = Field(default_factory=list)
    suggested_follow_up_days: int | None = None
    clinical_notes_draft: str | None = None
    suggested_medications: list[dict] = Field(default_factory=list)
    allergy_warnings: list[str] = Field(default_factory=list)
    disclaimer: str = (
        "AI suggestions are for assistance only. Doctor must review before use."
    )
