import uuid as uuid_lib
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_patient_profile
from app.database import get_db
from app.models import Patient, Report
from app.schemas.common import ResponseEnvelope
from app.services.report_service import analyze_report_record, create_and_analyze_report
from app.services.vitals_service import extract_health_vitals_from_reports

router = APIRouter(prefix="/reports", tags=["reports"])


def _report_filename(report: Report) -> str:
    meta = (report.analysis_json or {}).get("_meta") or {}
    return meta.get("filename") or "Medical report.pdf"


def _report_to_list_item(report: Report) -> dict:
    analysis = report.analysis_json or {}
    abnormal = analysis.get("abnormal") or []
    summary = analysis.get("summary")
    return {
        "id": str(report.id),
        "filename": _report_filename(report),
        "created_at": report.created_at.isoformat() if report.created_at else None,
        "has_analysis": bool(summary or abnormal),
        "summary": summary,
        "abnormal_count": len(abnormal),
        "abnormal": abnormal[:5],
    }


class RegisterReport(BaseModel):
    report_id: UUID
    filename: str
    checksum: str | None = None


@router.post("/upload-url")
async def upload_url(patient: Patient = Depends(get_patient_profile)):
    report_id = uuid_lib.uuid4()
    key = f"reports/{patient.id}/{report_id}.pdf"
    return ResponseEnvelope(
        data={
            "report_id": str(report_id),
            "upload_url": f"/local-upload/{key}",
            "s3_key": key,
        }
    )


@router.post("/register")
async def register_report(
    data: RegisterReport,
    patient: Patient = Depends(get_patient_profile),
    db: AsyncSession = Depends(get_db),
):
    key = f"reports/{patient.id}/{data.report_id}.pdf"
    report = Report(
        id=data.report_id,
        patient_id=patient.id,
        s3_key=key,
        file_checksum=data.checksum,
        analysis_json={"_meta": {"filename": data.filename}},
    )
    db.add(report)
    await db.flush()
    return ResponseEnvelope(data={"id": str(report.id)})


@router.post("/upload")
async def upload_report(
    file: UploadFile = File(...),
    patient: Patient = Depends(get_patient_profile),
    db: AsyncSession = Depends(get_db),
):
    """Upload a medical report (PDF, image, Word, Excel, CSV, text), extract content, and analyze."""
    data = await file.read()
    filename = file.filename or "Medical report.pdf"
    try:
        report = await create_and_analyze_report(
            db,
            patient.id,
            data,
            filename,
            file.content_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    analysis = report.analysis_json or {}
    return ResponseEnvelope(
        data={
            "id": str(report.id),
            "report_id": str(report.id),
            "filename": filename,
            "analysis": analysis,
            "summary": analysis.get("summary"),
            "abnormal": analysis.get("abnormal") or [],
        }
    )


@router.post("/{report_id}/analyze")
async def analyze_report(
    report_id: UUID,
    force: bool = Query(default=False),
    patient: Patient = Depends(get_patient_profile),
    db: AsyncSession = Depends(get_db),
):
    report = await db.get(Report, report_id)
    if not report or report.patient_id != patient.id:
        raise HTTPException(status_code=404, detail="Report not found")

    try:
        analysis = await analyze_report_record(db, report, force=force)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return ResponseEnvelope(data=analysis)


@router.get("/health-vitals")
async def health_vitals(patient: Patient = Depends(get_patient_profile), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Report).where(Report.patient_id == patient.id).order_by(Report.created_at.desc())
    )
    reports = list(result.scalars().all())
    vitals = extract_health_vitals_from_reports(reports)
    return ResponseEnvelope(data={"vitals": vitals, "has_data": len(vitals) > 0})


@router.get("")
async def list_reports(patient: Patient = Depends(get_patient_profile), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Report).where(Report.patient_id == patient.id).order_by(Report.created_at.desc())
    )
    return ResponseEnvelope(data=[_report_to_list_item(r) for r in result.scalars().all()])


@router.get("/{report_id}")
async def get_report(
    report_id: UUID, patient: Patient = Depends(get_patient_profile), db: AsyncSession = Depends(get_db)
):
    report = await db.get(Report, report_id)
    if not report or report.patient_id != patient.id:
        from fastapi import HTTPException
        raise HTTPException(status_code=404)
    analysis = report.analysis_json or {}
    return ResponseEnvelope(
        data={
            "id": str(report.id),
            "filename": _report_filename(report),
            "created_at": report.created_at.isoformat() if report.created_at else None,
            "analysis": analysis,
            "ocr_text": report.ocr_text,
        }
    )
