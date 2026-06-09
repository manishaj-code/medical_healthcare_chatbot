import re
from typing import Any

from app.models import Report

_VITAL_ORDER = ("blood_pressure", "heart_rate", "glucose", "hemoglobin")

_SPECS: dict[str, dict[str, Any]] = {
    "blood_pressure": {
        "label": "Blood Pressure",
        "unit": "mmHg",
        "icon": "monitor_heart",
        "icon_variant": "teal",
        "bar_class": "",
        "default_status": "Optimal",
        "aliases": ("blood pressure", "bp", "systolic", "diastolic"),
    },
    "heart_rate": {
        "label": "Heart Rate",
        "unit": "BPM",
        "icon": "favorite",
        "icon_variant": "rose",
        "bar_class": "bar-rose",
        "default_status": "Stable",
        "aliases": ("heart rate", "pulse", "hr", "bpm"),
    },
    "glucose": {
        "label": "Glucose Level",
        "unit": "mg/dL",
        "icon": "opacity",
        "icon_variant": "cyan",
        "bar_class": "bar-cyan",
        "default_status": "Normal",
        "aliases": ("glucose", "blood sugar", "fasting glucose", "random glucose"),
    },
    "hemoglobin": {
        "label": "Hemoglobin",
        "unit": "g/dL",
        "icon": "bloodtype",
        "icon_variant": "teal",
        "bar_class": "",
        "default_status": "Normal",
        "aliases": ("hemoglobin", "hgb", "hb"),
    },
}

_OCR_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "blood_pressure",
        re.compile(
            r"blood\s*pressure[:\s]+(\d{2,3})\s*/\s*(\d{2,3})",
            re.I,
        ),
    ),
    (
        "blood_pressure",
        re.compile(r"\bbp[:\s]+(\d{2,3})\s*/\s*(\d{2,3})\b", re.I),
    ),
    (
        "heart_rate",
        re.compile(r"(?:heart\s*rate|pulse|hr)[:\s]+(\d{2,3})\s*(?:bpm)?", re.I),
    ),
    (
        "heart_rate",
        re.compile(r"\b(\d{2,3})\s*bpm\b", re.I),
    ),
    (
        "glucose",
        re.compile(
            r"(?:glucose|blood\s*sugar|fasting\s*glucose)[:\s]+(\d{2,3}(?:\.\d+)?)",
            re.I,
        ),
    ),
    (
        "hemoglobin",
        re.compile(r"hemoglobin[:\s]+(\d{1,2}(?:\.\d+)?)", re.I),
    ),
]


def _normalize_key(test_name: str) -> str | None:
    name = test_name.strip().lower()
    for key, spec in _SPECS.items():
        if any(alias in name for alias in spec["aliases"]):
            return key
    return None


def _status_for(flag: str | None, default: str) -> str:
    f = (flag or "").upper()
    if f == "HIGH":
        return "Elevated"
    if f == "LOW":
        return "Low"
    if f in ("NORMAL", "OPTIMAL", "STABLE"):
        return default
    return default


def _bar_percent(flag: str | None) -> int:
    f = (flag or "").upper()
    if f == "HIGH":
        return 88
    if f == "LOW":
        return 42
    return 72


def _build_vital(
    key: str,
    *,
    value: str,
    value_secondary: str | None = None,
    flag: str | None = None,
    source_report_id: str | None = None,
    source_filename: str | None = None,
) -> dict:
    spec = _SPECS[key]
    display = f"{value}/{value_secondary}" if value_secondary else value
    status = _status_for(flag, spec["default_status"])
    return {
        "key": key,
        "label": spec["label"],
        "value": value,
        "value_secondary": value_secondary,
        "display": display,
        "unit": spec["unit"],
        "status": status,
        "flag": (flag or "NORMAL").upper(),
        "bar_percent": _bar_percent(flag),
        "icon": spec["icon"],
        "icon_variant": spec["icon_variant"],
        "bar_class": spec["bar_class"],
        "source_report_id": source_report_id,
        "source_filename": source_filename,
    }


def _from_abnormal(abnormal: list[dict], report: Report, found: dict[str, dict]) -> None:
    meta = (report.analysis_json or {}).get("_meta") or {}
    filename = meta.get("filename") or "Medical report.pdf"
    report_id = str(report.id)

    for item in abnormal:
        test = str(item.get("test") or "")
        key = _normalize_key(test)
        if not key or key in found:
            continue
        raw = str(item.get("value") or "").strip()
        if not raw:
            continue
        flag = item.get("flag")
        if key == "blood_pressure" and "/" in raw:
            parts = raw.split("/", 1)
            found[key] = _build_vital(
                key,
                value=parts[0].strip(),
                value_secondary=parts[1].strip(),
                flag=flag,
                source_report_id=report_id,
                source_filename=filename,
            )
        else:
            found[key] = _build_vital(
                key,
                value=raw,
                flag=flag,
                source_report_id=report_id,
                source_filename=filename,
            )


def _from_ocr(ocr_text: str, report: Report, found: dict[str, dict]) -> None:
    meta = (report.analysis_json or {}).get("_meta") or {}
    filename = meta.get("filename") or "Medical report.pdf"
    report_id = str(report.id)
    text = ocr_text or ""

    for key, pattern in _OCR_PATTERNS:
        if key in found:
            continue
        match = pattern.search(text)
        if not match:
            continue
        if key == "blood_pressure":
            found[key] = _build_vital(
                key,
                value=match.group(1),
                value_secondary=match.group(2),
                source_report_id=report_id,
                source_filename=filename,
            )
        else:
            found[key] = _build_vital(
                key,
                value=match.group(1),
                source_report_id=report_id,
                source_filename=filename,
            )


def _from_stored_vitals(stored: dict, report: Report, found: dict[str, dict]) -> None:
    meta = (report.analysis_json or {}).get("_meta") or {}
    filename = meta.get("filename") or "Medical report.pdf"
    report_id = str(report.id)

    for key, payload in stored.items():
        if key not in _SPECS or key in found:
            continue
        if isinstance(payload, dict):
            value = str(payload.get("value") or "").strip()
            if not value:
                continue
            found[key] = _build_vital(
                key,
                value=value,
                value_secondary=(str(payload.get("value_secondary")).strip() if payload.get("value_secondary") else None),
                flag=payload.get("flag"),
                source_report_id=report_id,
                source_filename=filename,
            )


def extract_vitals_from_report(report: Report) -> list[dict]:
    analysis = report.analysis_json or {}
    found: dict[str, dict] = {}

    stored = analysis.get("vitals")
    if isinstance(stored, dict):
        _from_stored_vitals(stored, report, found)

    abnormal = analysis.get("abnormal")
    if isinstance(abnormal, list):
        _from_abnormal(abnormal, report, found)

    if report.ocr_text:
        _from_ocr(report.ocr_text, report, found)

    return [found[key] for key in _VITAL_ORDER if key in found]


def extract_health_vitals_from_reports(reports: list[Report]) -> list[dict]:
    """Newest reports first — first match per vital wins."""
    merged: dict[str, dict] = {}
    for report in sorted(
        reports,
        key=lambda r: r.created_at.isoformat() if r.created_at else "",
        reverse=True,
    ):
        for vital in extract_vitals_from_report(report):
            merged.setdefault(vital["key"], vital)
    return [merged[key] for key in _VITAL_ORDER if key in merged]
