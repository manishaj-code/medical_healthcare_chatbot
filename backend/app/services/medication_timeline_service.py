"""Link prescriptions to visits and surface continue / refill guidance for doctors."""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Appointment,
    Consultation,
    Medication,
    Prescription,
    PrescriptionItem,
    RefillRequest,
)
from app.services.appointment_service import format_apt_id


_OPEN_ENDED_DURATION_RE = re.compile(
    r"\b(ongoing|continuous|chronic|as needed|prn|indefinite|long[\s-]?term)\b",
    re.IGNORECASE,
)
_DURATION_RE = re.compile(
    r"(\d+)\s*(day|days|week|weeks|month|months|year|years)",
    re.IGNORECASE,
)


def parse_duration_days(duration: str | None) -> int | None:
    """Return estimated course length in days, or None when open-ended."""
    if not duration or not duration.strip():
        return None
    text = duration.strip()
    if _OPEN_ENDED_DURATION_RE.search(text):
        return None
    match = _DURATION_RE.search(text)
    if not match:
        return None
    amount = int(match.group(1))
    unit = match.group(2).lower()
    if unit.startswith("week"):
        return amount * 7
    if unit.startswith("month"):
        return amount * 30
    if unit.startswith("year"):
        return amount * 365
    return amount


def estimate_course_end(prescribed_on: date, duration: str | None) -> date | None:
    days = parse_duration_days(duration)
    if days is None:
        return None
    return prescribed_on + timedelta(days=days)


def _continuation_status(
    *,
    prescribed_on: date,
    duration: str | None,
    is_active: bool,
    today: date,
) -> tuple[str, bool]:
    """Return (continuation_status, refill_suggested)."""
    open_ended = parse_duration_days(duration) is None
    course_end = estimate_course_end(prescribed_on, duration)

    if open_ended:
        return ("continue", False)

    if course_end and course_end >= today:
        return ("continue", False)

    if is_active:
        return ("refill_suggested", True)

    return ("course_ended", False)


def _med_key(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().lower())


async def load_prescription_items_by_appointment(
    db: AsyncSession,
    consultations_by_appt: dict[str, Consultation],
) -> dict[str, list[dict]]:
    """Prescription line items keyed by appointment_id string."""
    items_by_appt: dict[str, list[dict]] = {key: [] for key in consultations_by_appt}
    consultation_ids = [c.id for c in consultations_by_appt.values()]
    if not consultation_ids:
        return items_by_appt

    rx_rows = await db.execute(
        select(Prescription).where(Prescription.consultation_id.in_(consultation_ids))
    )
    prescriptions = list(rx_rows.scalars().all())
    rx_by_consultation = {str(rx.consultation_id): rx for rx in prescriptions}
    rx_ids = [rx.id for rx in prescriptions]

    items_by_rx: dict[str, list[PrescriptionItem]] = {}
    if rx_ids:
        item_rows = await db.execute(
            select(PrescriptionItem)
            .where(PrescriptionItem.prescription_id.in_(rx_ids))
            .order_by(PrescriptionItem.sort_order)
        )
        for item in item_rows.scalars().all():
            items_by_rx.setdefault(str(item.prescription_id), []).append(item)

    consult_to_appt = {str(c.id): appt_key for appt_key, c in consultations_by_appt.items()}
    for consult_key, rx in rx_by_consultation.items():
        appt_key = consult_to_appt.get(consult_key)
        if not appt_key:
            continue
        for item in items_by_rx.get(str(rx.id), []):
            items_by_appt[appt_key].append({
                "id": str(item.id),
                "medicine_name": item.medicine_name,
                "strength": item.strength,
                "frequency": item.frequency,
                "duration": item.duration,
                "instructions": item.instructions,
                "source": item.source,
            })
    return items_by_appt


async def build_patient_medication_timeline(
    db: AsyncSession,
    doctor_id: UUID,
    patient_id: UUID,
    *,
    today: date | None = None,
) -> dict:
    today = today or date.today()

    appt_rows = await db.execute(
        select(Appointment)
        .where(Appointment.doctor_id == doctor_id, Appointment.patient_id == patient_id)
        .order_by(Appointment.slot_date.desc(), Appointment.slot_time.desc())
    )
    appointments = list(appt_rows.scalars().all())
    appt_by_id = {str(a.id): a for a in appointments}
    appt_ids = [a.id for a in appointments]

    consultations_by_appt: dict[str, Consultation] = {}
    if appt_ids:
        consultation_rows = await db.execute(
            select(Consultation).where(Consultation.appointment_id.in_(appt_ids))
        )
        for row in consultation_rows.scalars().all():
            consultations_by_appt[str(row.appointment_id)] = row

    items_by_appt = await load_prescription_items_by_appointment(db, consultations_by_appt)

    active_meds_rows = await db.execute(
        select(Medication).where(
            Medication.patient_id == patient_id,
            Medication.is_active.is_(True),
        )
    )
    active_meds = { _med_key(m.name): m for m in active_meds_rows.scalars().all() }

    refill_rows = await db.execute(
        select(RefillRequest)
        .where(
            RefillRequest.patient_id == patient_id,
            RefillRequest.doctor_id == doctor_id,
            RefillRequest.status == "pending",
        )
        .order_by(RefillRequest.requested_at.desc())
    )
    pending_refills = [
        {
            "id": str(r.id),
            "medication_name": r.medication_name,
            "medication_dosage": r.medication_dosage,
            "medication_frequency": r.medication_frequency,
            "requested_at": r.requested_at.isoformat() if r.requested_at else None,
        }
        for r in refill_rows.scalars().all()
    ]
    pending_by_med = {_med_key(r["medication_name"]) for r in pending_refills}

    timeline_by_med: dict[str, dict] = {}
    for appt_key, items in items_by_appt.items():
        appt = appt_by_id.get(appt_key)
        consultation = consultations_by_appt.get(appt_key)
        if not appt or not items:
            continue

        prescribed_on = appt.completed_at.date() if appt.completed_at else appt.slot_date
        for item in items:
            key = _med_key(item["medicine_name"])
            entry = {
                "id": item["id"],
                "name": item["medicine_name"],
                "dosage": item["strength"],
                "frequency": item["frequency"],
                "duration": item["duration"],
                "instructions": item["instructions"],
                "prescribed_at": prescribed_on.isoformat(),
                "course_end_date": (
                    estimate_course_end(prescribed_on, item["duration"]).isoformat()
                    if estimate_course_end(prescribed_on, item["duration"])
                    else None
                ),
                "days_since_prescribed": (today - prescribed_on).days,
                "source": {
                    "appointment_id": appt_key,
                    "apt_id": format_apt_id(appt.id),
                    "visit_date": str(appt.slot_date),
                    "chief_complaint": consultation.chief_complaint if consultation else None,
                    "diagnosis": consultation.diagnosis if consultation else None,
                    "appointment_reason": appt.appointment_reason,
                },
            }
            existing = timeline_by_med.get(key)
            if not existing or entry["prescribed_at"] > existing["prescribed_at"]:
                timeline_by_med[key] = entry

    timeline: list[dict] = []
    for key, entry in timeline_by_med.items():
        active_row = active_meds.get(key)
        is_active = active_row is not None
        prescribed_on = date.fromisoformat(entry["prescribed_at"])
        status, refill_suggested = _continuation_status(
            prescribed_on=prescribed_on,
            duration=entry["duration"],
            is_active=is_active,
            today=today,
        )
        entry["medication_id"] = str(active_row.id) if active_row else None
        entry["is_active"] = is_active
        entry["continuation_status"] = status
        entry["refill_suggested"] = refill_suggested
        entry["pending_refill"] = key in pending_by_med
        timeline.append(entry)

    timeline.sort(key=lambda row: row["prescribed_at"], reverse=True)

    active_meds = [m for m in timeline if m["continuation_status"] != "course_ended"]
    ended_meds = [m for m in timeline if m["continuation_status"] == "course_ended"]

    return {
        "medications": timeline,
        "active_medications": active_meds,
        "ended_medications": ended_meds,
        "pending_refills": pending_refills,
        "summary": {
            "total_prescribed": len(timeline),
            "active_count": len(active_meds),
            "ended_count": len(ended_meds),
            "pending_refill_count": len(pending_refills),
        },
    }


def serialize_prescription_items(items: list[dict]) -> list[dict]:
    return [
        {
            "id": item["id"],
            "medicine_name": item["medicine_name"],
            "strength": item["strength"],
            "frequency": item["frequency"],
            "duration": item["duration"],
            "instructions": item["instructions"],
            "source": item.get("source"),
        }
        for item in items
    ]
