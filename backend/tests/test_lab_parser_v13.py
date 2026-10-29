"""V1.3 laboratory parser regression tests (synthetic text only)."""

from __future__ import annotations

from app.intelligence.lab_parser import classify_document_text, parse_lab_ocr_text


def test_wrapped_reference_range_never_treats_high_as_value() -> None:
    """Mandatory regression: 'Glucose 112 H 70 -\\n99' → value 112, range 70-99."""
    text = "Lab Report\nGlucose 112 H 70 -\n99\nCollected 2026-01-15\n"
    rows = parse_lab_ocr_text(text)
    glucose = next(row for row in rows if row.test_name_raw.lower() == "glucose")
    assert glucose.value_raw == "112"
    assert glucose.value_numeric == 112
    assert glucose.abnormal_flag_raw.upper() == "H"
    assert glucose.abnormal_flag == "high"
    assert glucose.reference_range_raw.replace(" ", "") in {"70-99", "70–99"}
    assert "99" not in glucose.value_raw
    assert glucose.source_text.startswith("Glucose")


def test_standard_lab_table_rows() -> None:
    text = """
    Test                 Result     Flag     Reference Range
    Glucose              112        H        70–99 mg/dL
    Hemoglobin A1c       5.8        H        4.0–5.6 %
    Hemoglobin           13.6                12.0–15.5 g/dL
    Total Cholesterol    205        H        <200 mg/dL
    """
    rows = parse_lab_ocr_text(text)
    by_name = {row.test_name_raw.lower(): row for row in rows}
    assert by_name["glucose"].value_numeric == 112
    assert by_name["hemoglobin a1c"].value_raw == "5.8"
    assert by_name["hemoglobin"].value_raw == "13.6"
    assert "cholesterol" in " ".join(by_name)
    chol = next(v for k, v in by_name.items() if "cholesterol" in k)
    assert chol.value_raw == "205"
    assert chol.require_review is False or chol.confidence >= 0.55


def test_classification_marks_lab_reports() -> None:
    text = "Lab Report\nGlucose 118 mg/dL (70-99)\nHbA1c 5.6 % (4.0-5.6)\n"
    result = classify_document_text(text)
    assert result["category"] == "laboratory_report"
    assert result["auto_extract_lab"] is True


def test_fake_extraction_adapter_uses_lab_parser() -> None:
    from app.intelligence.extraction_port import FakeExtractionAdapter
    from app.intelligence.ocr_port import OcrPageRegion, OcrResult

    ocr = OcrResult(
        full_text="Glucose 112 H 70 -\n99\n",
        regions=[
            OcrPageRegion(page=1, text="Glucose 112 H 70 -", y=0.1),
            OcrPageRegion(page=1, text="99", y=0.15),
        ],
    )
    fields = FakeExtractionAdapter().extract_fields(ocr=ocr)
    glucose = next(f for f in fields if f.name.lower() == "glucose")
    assert glucose.value == "112"
    assert glucose.extras
    assert glucose.extras.get("reference_range_raw", "").replace(" ", "").startswith("70-99")
