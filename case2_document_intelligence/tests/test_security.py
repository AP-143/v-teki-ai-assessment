"""Privacy and security tests. Each one checks that something unsafe does NOT happen."""
import json
import logging

import pytest

from invoice_extractor import extract
from invoice_extractor.extract import extract_document, extract_regex
from invoice_extractor.intake import MAX_BYTES, RejectedFile, read_text_safely
from invoice_extractor.privacy import redact


@pytest.mark.parametrize("name, code", [
    ("corrupt.pdf", "CORRUPT_PDF"),
    ("fake_executable.pdf", "NOT_A_PDF"),
    ("empty.pdf", "EMPTY_FILE"),
    ("invoice.txt", "UNSUPPORTED_TYPE"),
])
def test_unsafe_files_are_rejected_before_parsing(data_dir, name, code):
    path = data_dir / "bad_files" / name
    with pytest.raises(RejectedFile) as err:
        read_text_safely(path.read_bytes(), name)
    assert err.value.code == code


def test_oversized_file_is_rejected():
    with pytest.raises(RejectedFile) as err:
        read_text_safely(b"%PDF-" + bytes(MAX_BYTES), "big.pdf")
    assert err.value.code == "FILE_TOO_LARGE"


def test_scanned_pdf_goes_to_review_instead_of_guessing(data_dir):
    path = data_dir / "bad_files" / "scanned_no_text.pdf"
    result = extract_document(path.read_bytes(), path.name)
    assert result["status"] == "NEEDS_REVIEW"
    assert result["review_reasons"] == ["NO_TEXT_LAYER"]
    assert set(result["fields"].values()) == {None}


def test_redaction_removes_contact_and_bank_data_but_keeps_invoice_fields(data_dir):
    path = data_dir / "invoices" / "invoice_003.pdf"
    text = read_text_safely(path.read_bytes(), path.name)
    redacted = redact(text)

    assert "@vendor.example" not in redacted
    assert "+62812" not in redacted
    assert "[ACCOUNT_NUMBER]" in redacted
    assert extract_regex(redacted)[0] == extract_regex(text)[0]  # nothing the extractor needs was removed


def test_cli_logs_contain_no_document_content_and_bad_files_do_not_crash(data_dir, capsys, caplog):
    files = [data_dir / "invoices" / "invoice_003.pdf", data_dir / "bad_files" / "fake_executable.pdf"]
    with caplog.at_level(logging.INFO, logger="invoice_extractor"), pytest.raises(SystemExit) as exit_info:
        extract.main(["--method", "regex", *[str(f) for f in files]])

    results = json.loads(capsys.readouterr().out)
    assert exit_info.value.code == 2
    assert [r["status"] for r in results] == ["NEEDS_REVIEW", "REJECTED"]
    truth = json.loads((data_dir / "expected.json").read_text())["invoice_003.pdf"]["fields"]
    for secret in ["@vendor.example", truth["vendor_name"], truth["invoice_number"], "invoice_003"]:
        assert secret not in caplog.text
    assert "document=" in caplog.text  # logs identify documents by content hash only
