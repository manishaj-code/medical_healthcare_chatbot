"""Aggregate patient consult summary from appointments, visits, and reports."""
from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Appointment, Consultation, Report
from app.services.appointment_service import format_apt_id, is_active_appointment_status
from app.services.consultation_service import clean_clinical_findings_for_record


def _report_filename(report: Report) -> str:
    meta = (report.analysis_json or {}).get("_meta") or {}
    return meta.get("filename") or "Medical report"


def _report_summary(report: Report) -> str:
    analysis = report.analysis_json or {}
    return (analysis.get("summary") or "").strip()


def _report_abnormal(report: Report) -> list[dict]:
    analysis = report.analysis_json or {}
    return analysis.get("abnormal") or []


def _unique_nonempty(values: list[str | None], *, limit: int = 12) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in values:
        text = (raw or "").strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= limit:
            break
    return out


def _excerpt(text: str | None, limit: int = 200) -> str | None:
    if not text or not text.strip():
        return None
    cleaned = " ".join(text.split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"


def _appt_sort_key(appt: Appointment) -> datetime:
    return datetime.combine(appt.slot_date, appt.slot_time, tzinfo=timezone.utc)


def _is_upcoming(appt: Appointment, today: date) -> bool:
    status = appt.status.value if hasattr(appt.status, "value") else str(appt.status)
    if not is_active_appointment_status(status):
        return False
    return appt.slot_date >= today


def _build_narrative(
    *,
    completed_count: int,
    reports_count: int,
    upcoming_count: int,
    latest_visit: dict | None,
    latest_report: dict | None,
    latest_follow_up: str | None,
) -> str:
    parts: list[str] = []
    if completed_count:
        parts.append(
            f"{completed_count} completed consultation{'s' if completed_count != 1 else ''} with you"
        )
    if reports_count:
        parts.append(f"{reports_count} uploaded medical report{'s' if reports_count != 1 else ''}")
    if upcoming_count:
        parts.append(f"{upcoming_count} upcoming appointment{'s' if upcoming_count != 1 else ''}")

    if not parts:
        return "No completed visits or uploaded reports recorded for this patient yet."

    intro = "Patient has " + ", ".join(parts) + "."

    details: list[str] = []
    if latest_visit:
        label = latest_visit.get("apt_id") or "Latest visit"
        when = latest_visit.get("date") or ""
        diagnosis = (latest_visit.get("diagnosis") or "").strip()
        if diagnosis:
            details.append(f"Most recent visit ({label}, {when}): {diagnosis}")
        elif latest_visit.get("chief_complaint"):
            details.append(
                f"Most recent visit ({label}, {when}): {latest_visit['chief_complaint']}"
            )

    if latest_report and latest_report.get("summary"):
        name = latest_report.get("filename") or "report"
        excerpt = _excerpt(latest_report["summary"], 140)
        if excerpt:
            details.append(f'Latest report ({name}): "{excerpt}"')

    if latest_follow_up:
        details.append(f"Next follow-up scheduled for {latest_follow_up}")

    if not details:
        return intro
    return intro + " " + " ".join(details)


def build_consult_overview_payload(
    appointments: list[Appointment],
    consultations_by_appt: dict[str, Consultation],
    reports: list[Report],
    reports_by_id: dict[UUID, Report],
    *,
    today: date | None = None,
) -> dict:
    """Pure builder for tests and API serialization."""
    today = today or date.today()

    completed_visits: list[dict] = []
    upcoming_visits: list[dict] = []
    timeline: list[dict] = []

    for appt in appointments:
        appt_key = str(appt.id)
        status = appt.status.value if hasattr(appt.status, "value") else str(appt.status)
        consultation = consultations_by_appt.get(appt_key)
        linked = reports_by_id.get(appt.linked_report_id) if appt.linked_report_id else None
        linked_payload = None
        if linked:
            linked_payload = {
                "report_id": str(linked.id),
                "filename": _report_filename(linked),
                "summary": _report_summary(linked),
                "abnormal": _report_abnormal(linked),
            }

        base = {
            "apt_id": format_apt_id(appt.id),
            "appointment_id": appt_key,
            "date": str(appt.slot_date),
            "time": str(appt.slot_time),
            "consultation_mode": appt.consultation_mode or "in_person",
            "appointment_reason": appt.appointment_reason,
            "linked_report": linked_payload,
        }

        if status == "completed" and consultation:
            findings = clean_clinical_findings_for_record(consultation.clinical_findings)
            visit = {
                **base,
                "status": status,
                "completed_at": (
                    consultation.completed_at.isoformat() if consultation.completed_at else None
                ),
                "chief_complaint": consultation.chief_complaint,
                "diagnosis": consultation.diagnosis,
                "clinical_findings": findings,
                "clinical_findings_excerpt": _excerpt(findings),
                "treatment_plan": consultation.treatment_plan,
                "doctor_notes": consultation.doctor_notes,
                "follow_up_date": (
                    str(consultation.follow_up_date) if consultation.follow_up_date else None
                ),
            }
            completed_visits.append(visit)
            title = appt.appointment_reason or consultation.chief_complaint or "Completed visit"
            timeline.append({
                "type": "visit_completed",
                "sort_at": visit["completed_at"] or f"{base['date']}T{base['time']}",
                **visit,
                "title": title,
                "subtitle": consultation.diagnosis or consultation.chief_complaint,
            })
        elif _is_upcoming(appt, today):
            upcoming = {**base, "status": status}
            upcoming_visits.append(upcoming)
            title = appt.appointment_reason or "Upcoming appointment"
            timeline.append({
                "type": "visit_upcoming",
                "sort_at": f"{base['date']}T{base['time']}",
                **upcoming,
                "title": title,
                "subtitle": linked_payload["filename"] if linked_payload else None,
            })

    report_entries: list[dict] = []
    for report in reports:
        entry = {
            "report_id": str(report.id),
            "filename": _report_filename(report),
            "summary": _report_summary(report),
            "abnormal": _report_abnormal(report),
            "created_at": report.created_at.isoformat() if report.created_at else None,
        }
        report_entries.append(entry)
        timeline.append({
            "type": "report_uploaded",
            "sort_at": entry["created_at"] or "",
            "title": entry["filename"],
            "subtitle": _excerpt(entry["summary"], 120),
            "report": entry,
        })

    timeline.sort(key=lambda item: item.get("sort_at") or "", reverse=True)
    for item in timeline:
        item.pop("sort_at", None)

    latest_follow_up = None
    for visit in sorted(
        completed_visits,
        key=lambda v: v.get("completed_at") or f"{v['date']}T{v['time']}",
        reverse=True,
    ):
        if visit.get("follow_up_date"):
            latest_follow_up = visit["follow_up_date"]
            break

    rollup = {
        "completed_visits": len(completed_visits),
        "reports_count": len(report_entries),
        "upcoming_visits": len(upcoming_visits),
        "chief_complaints": _unique_nonempty([v.get("chief_complaint") for v in completed_visits]),
        "diagnoses": _unique_nonempty([v.get("diagnosis") for v in completed_visits]),
        "treatment_plans": _unique_nonempty([v.get("treatment_plan") for v in completed_visits]),
        "report_summaries": _unique_nonempty(
            [r.get("summary") for r in report_entries],
            limit=6,
        ),
        "latest_follow_up": latest_follow_up,
    }

    if completed_visits:
        completed_visits.sort(
            key=lambda v: v.get("completed_at") or f"{v['date']}T{v['time']}",
            reverse=True,
        )
    latest_visit = completed_visits[0] if completed_visits else None

    latest_report = report_entries[0] if report_entries else None

    narrative = _build_narrative(
        completed_count=rollup["completed_visits"],
        reports_count=rollup["reports_count"],
        upcoming_count=rollup["upcoming_visits"],
        latest_visit=latest_visit,
        latest_report=latest_report,
        latest_follow_up=latest_follow_up,
    )

    return {
        "rollup": rollup,
        "completed_visits": completed_visits,
        "upcoming_visits": upcoming_visits,
        "reports": report_entries,
        "timeline": timeline,
        "narrative": narrative,
    }


async def build_patient_consult_overview(
    db: AsyncSession,
    doctor_id: UUID,
    patient_id: UUID,
) -> dict:
    appt_rows = await db.execute(
        select(Appointment)
        .where(Appointment.doctor_id == doctor_id, Appointment.patient_id == patient_id)
        .order_by(Appointment.slot_date.desc(), Appointment.slot_time.desc())
    )
    appointments = list(appt_rows.scalars().all())
    appt_ids = [a.id for a in appointments]

    consultations_by_appt: dict[str, Consultation] = {}
    if appt_ids:
        consultation_rows = await db.execute(
            select(Consultation).where(Consultation.appointment_id.in_(appt_ids))
        )
        for row in consultation_rows.scalars().all():
            consultations_by_appt[str(row.appointment_id)] = row

    report_rows = await db.execute(
        select(Report)
        .where(Report.patient_id == patient_id)
        .order_by(Report.created_at.desc())
    )
    reports = list(report_rows.scalars().all())
    reports_by_id = {r.id: r for r in reports}

    return build_consult_overview_payload(
        appointments,
        consultations_by_appt,
        reports,
        reports_by_id,
    )
