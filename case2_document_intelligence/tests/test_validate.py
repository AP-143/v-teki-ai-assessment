import pytest

from invoice_extractor.extract import extract_document
from invoice_extractor.validate import normalize_amount, normalize_date, validate

DOC = """INVOICE
PT Sinar Abadi
Invoice No: INV-2026-1003
Invoice Date: 2026-09-13
Due Date: 2026-10-28
Tax ID (NPWP): 01.234.567.8-901.000
Subtotal: Rp 1,000,000
Tax (PPN 11%): Rp 110,000
Total: Rp 1,110,000"""

GOOD = {
    "invoice_number": "INV-2026-1003", "invoice_date": "2026-09-13", "due_date": "2026-10-28",
    "vendor_name": "PT Sinar Abadi", "vendor_tax_id": "01.234.567.8-901.000",
    "subtotal": "Rp 1,000,000", "tax_amount": "Rp 110,000", "total_amount": "Rp 1,110,000",
}


@pytest.mark.parametrize("raw, expected", [
    ("2026-10-15", "2026-10-15"),
    ("15/10/2026", "2026-10-15"),
    ("15 Okt 2026", "2026-10-15"),
    ("15 October 2026", "2026-10-15"),
    ("7 Agu 2026", "2026-08-07"),
    ("31/02/2026", None),  # no such day
    ("next Tuesday", None),
])
def test_normalize_date(raw, expected):
    assert normalize_date(raw) == expected


@pytest.mark.parametrize("raw, expected", [
    ("Rp 12,120,000", 12_120_000),
    ("IDR 4.075.000,00", 4_075_000),
    ("Rp2.400.000", 2_400_000),
    ("Rp 1,150", 1_150),
    ("n/a", None),
])
def test_normalize_amount(raw, expected):
    assert normalize_amount(raw) == expected


def test_complete_consistent_invoice_is_auto_accepted():
    result = validate(GOOD, DOC)
    assert result["status"] == "AUTO_ACCEPTED", result["review_reasons"]
    assert result["fields"]["total_amount"] == 1_110_000


def test_missing_field_is_null_and_sent_to_review():
    result = validate({**GOOD, "due_date": None}, DOC)
    assert result["fields"]["due_date"] is None
    assert result["status"] == "NEEDS_REVIEW"
    assert "MISSING_DUE_DATE" in result["review_reasons"]


def test_value_not_in_document_is_flagged_as_invented():
    result = validate({**GOOD, "vendor_name": "PT Invented Vendor"}, DOC)
    assert "NOT_FOUND_IN_DOCUMENT_VENDOR_NAME" in result["review_reasons"]


def test_arithmetic_and_date_rules():
    result = validate({**GOOD, "total_amount": "Rp 1,000,000", "due_date": "2026-09-13", "invoice_date": "2026-10-28"},
                      DOC + "\nTotal: Rp 1,000,000")
    assert "TOTAL_MISMATCH" in result["review_reasons"]
    assert "DUE_DATE_BEFORE_INVOICE_DATE" in result["review_reasons"]


def test_planted_problems_in_generated_invoices_reach_review(data_dir):
    # invoice_003: no tax ID printed; invoice_006: vendor's total is off by Rp 50,000 (both layout A)
    for name, reason in [("invoice_003.pdf", "MISSING_VENDOR_TAX_ID"), ("invoice_006.pdf", "TOTAL_MISMATCH")]:
        path = data_dir / "invoices" / name
        assert reason in extract_document(path.read_bytes(), name)["review_reasons"]
