import pytest

from app.services.report_service import (
    SUPPORTED_FORMATS_LABEL,
    _heuristic_analysis,
    extract_text_from_plain,
    extract_text_from_pdf,
    validate_report_file,
)


SAMPLE_OCR = """Sample Blood Test Report
Patient Name: Manisha
Hemoglobin (Hb) 13.2 g/dL 12.0 - 15.5 g/dL
WBC Count 7,200 /uL 4,000 - 11,000 /uL
Summary: All sample values shown are within typical reference ranges."""


def test_heuristic_analysis_normal_report():
    result = _heuristic_analysis(SAMPLE_OCR)
    assert result["abnormal"] == []
    assert "within" in result["summary"].lower()


def test_heuristic_analysis_low_hemoglobin():
    ocr = "Hemoglobin: 10.2 g/dL (Ref: 12.0-16.0) - LOW"
    result = _heuristic_analysis(ocr)
    assert any(item["test"].lower().startswith("hemoglobin") for item in result["abnormal"])
    assert result["abnormal"][0]["flag"] == "LOW"


def test_extract_text_from_csv():
    data = b"Test,Result,Range\nHemoglobin,13.2,12-15\n"
    text = extract_text_from_plain(data, ".csv")
    assert "Hemoglobin" in text
    assert "13.2" in text


def test_validate_rejects_legacy_doc():
    with pytest.raises(ValueError, match="Legacy .doc"):
        validate_report_file("report.doc", "application/msword", b"data")


def test_validate_accepts_docx():
    ext, mime = validate_report_file(
        "report.docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        b"PK\x03\x04",
    )
    assert ext == ".docx"
    assert mime.startswith("application/")


def test_supported_formats_label_present():
    assert "PDF" in SUPPORTED_FORMATS_LABEL
    assert "image" in SUPPORTED_FORMATS_LABEL.lower()


@pytest.mark.skipif(
    not __import__("pathlib").Path(__file__).resolve().parents[2].joinpath(
        "reports/Manisha_Blood_Test_Report_Sample(1).pdf"
    ).is_file(),
    reason="sample PDF not in workspace",
)
def test_extract_text_from_sample_pdf():
    pdf_path = (
        __import__("pathlib").Path(__file__).resolve().parents[2]
        / "reports"
        / "Manisha_Blood_Test_Report_Sample(1).pdf"
    )
    data = pdf_path.read_bytes()
    text = extract_text_from_pdf(data)
    assert "Hemoglobin" in text
    assert "13.2" in text
