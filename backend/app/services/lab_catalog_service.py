"""Lab test catalog — DB-backed orderable tests and AI investigation matching."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import LabTestCatalog

DEFAULT_LAB_TESTS = [
    {
        "test_code": "cbc",
        "test_name": "CBC",
        "keywords": ["cbc", "complete blood", "blood count", "hemogram"],
        "category": "hematology",
        "sort_order": 1,
    },
    {
        "test_code": "hba1c",
        "test_name": "HbA1c",
        "keywords": ["hba1c", "a1c", "glycated", "glycosylated"],
        "category": "metabolic",
        "sort_order": 2,
    },
    {
        "test_code": "lft",
        "test_name": "LFT",
        "keywords": ["lft", "liver", "liver function", "alt", "ast"],
        "category": "biochemistry",
        "sort_order": 3,
    },
    {
        "test_code": "kft",
        "test_name": "KFT",
        "keywords": ["kft", "kidney", "renal", "creatinine", "urea"],
        "category": "biochemistry",
        "sort_order": 4,
    },
    {
        "test_code": "thyroid",
        "test_name": "Thyroid",
        "keywords": ["thyroid", "tsh", "t3", "t4"],
        "category": "endocrine",
        "sort_order": 5,
    },
    {
        "test_code": "vitamin_d",
        "test_name": "Vitamin D",
        "keywords": ["vitamin d", "vit d", "25-oh", "25 hydroxy"],
        "category": "vitamins",
        "sort_order": 6,
    },
]


def _serialize_catalog_row(row: LabTestCatalog) -> dict:
    return {
        "test_code": row.test_code,
        "test_name": row.test_name,
        "keywords": row.keywords or [],
        "category": row.category,
        "description": row.description,
        "sort_order": row.sort_order,
    }


async def list_active_lab_catalog(db: AsyncSession) -> list[dict]:
    result = await db.execute(
        select(LabTestCatalog)
        .where(LabTestCatalog.is_active.is_(True))
        .order_by(LabTestCatalog.sort_order, LabTestCatalog.test_name)
    )
    rows = result.scalars().all()
    if rows:
        return [_serialize_catalog_row(r) for r in rows]
    return [dict(t, keywords=t["keywords"]) for t in DEFAULT_LAB_TESTS]


def investigation_matches_catalog_item(investigation: str, item: dict) -> bool:
    text = investigation.lower().strip()
    if not text:
        return False
    name = (item.get("test_name") or "").lower()
    code = (item.get("test_code") or "").lower()
    if name and (name in text or text in name):
        return True
    if code and code in text:
        return True
    for keyword in item.get("keywords") or []:
        kw = str(keyword).lower().strip()
        if kw and kw in text:
            return True
    return False


def match_investigations_to_catalog(
    investigations: list[str],
    catalog: list[dict],
) -> list[dict]:
    """Return catalog entries matched by AI investigation strings (deduped, catalog order)."""
    matched_codes: set[str] = set()
    ordered: list[dict] = []
    for inv in investigations:
        for item in catalog:
            code = item["test_code"]
            if code in matched_codes:
                continue
            if investigation_matches_catalog_item(inv, item):
                matched_codes.add(code)
                ordered.append(item)
    return ordered


def catalog_codes_from_investigations(
    investigations: list[str],
    catalog: list[dict],
) -> set[str]:
    return {item["test_code"] for item in match_investigations_to_catalog(investigations, catalog)}


async def resolve_lab_orders(
    db: AsyncSession,
    lab_orders: list,
) -> list[dict]:
    """Normalize lab order test names from catalog when code is known."""
    catalog = await list_active_lab_catalog(db)
    by_code = {c["test_code"]: c for c in catalog}
    resolved = []
    for lab in lab_orders:
        code = lab.test_code if hasattr(lab, "test_code") else lab.get("test_code")
        name = lab.test_name if hasattr(lab, "test_name") else lab.get("test_name")
        notes = lab.notes if hasattr(lab, "notes") else lab.get("notes")
        if code in by_code:
            name = by_code[code]["test_name"]
        resolved.append({"test_code": code, "test_name": name, "notes": notes})
    return resolved
