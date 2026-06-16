from app.services.lab_catalog_service import (
    investigation_matches_catalog_item,
    match_investigations_to_catalog,
)

CATALOG = [
    {
        "test_code": "cbc",
        "test_name": "CBC",
        "keywords": ["cbc", "complete blood", "blood count"],
    },
    {
        "test_code": "hba1c",
        "test_name": "HbA1c",
        "keywords": ["hba1c", "a1c"],
    },
]


def test_match_cbc_from_investigation_text():
    matched = match_investigations_to_catalog(["Complete blood count recommended"], CATALOG)
    assert len(matched) == 1
    assert matched[0]["test_code"] == "cbc"


def test_match_diabetes_hba1c():
    matched = match_investigations_to_catalog(["Check HbA1c for glycemic control"], CATALOG)
    assert any(m["test_code"] == "hba1c" for m in matched)


def test_no_match_returns_empty():
    matched = match_investigations_to_catalog(["Chest X-ray"], CATALOG)
    assert matched == []


def test_investigation_matches_by_name():
    assert investigation_matches_catalog_item("Order CBC today", CATALOG[0])
