import json

from invoice_extractor import evaluate
from invoice_extractor.evaluate import compare


def test_compare_labels_each_kind_of_outcome():
    expected = {"invoice_number": "INV-1", "due_date": None, "vendor_tax_id": None, "subtotal": 100, "total_amount": 111}
    predicted = {"invoice_number": "INV-1", "due_date": "2026-01-01", "vendor_tax_id": None, "subtotal": 999,
                 "total_amount": None}
    outcomes = compare(predicted, expected)

    assert outcomes["invoice_number"] == "correct"
    assert outcomes["vendor_tax_id"] == "correct"  # absent and returned as null
    assert outcomes["due_date"] == "invented"
    assert outcomes["subtotal"] == "wrong"
    assert outcomes["total_amount"] == "missing"


def test_regex_evaluation_writes_reports(data_dir, tmp_path):
    evaluate.main(["--data-dir", str(data_dir), "--reports-dir", str(tmp_path), "--methods", "regex"])

    summary = json.loads((tmp_path / "evaluation.json").read_text())["regex"]
    assert summary["documents"] == 9
    assert summary["accuracy_by_layout"]["A"] == 1.0
    assert summary["auto_accepted_with_errors"] == 0  # every wrong extraction was routed to review
    assert (tmp_path / "outputs" / "regex" / "invoice_001.json").exists()
    assert "Unsafe and unsupported files" in (tmp_path / "evaluation.md").read_text()
