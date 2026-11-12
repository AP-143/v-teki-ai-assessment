"""LLM extractor tests. Ollama is replaced by a fake, so these run on any machine."""
import io
import json
import urllib.error

import pytest

from invoice_extractor import llm
from invoice_extractor.extract import extract_document
from invoice_extractor.intake import read_text_safely
from invoice_extractor.llm import LLMUnavailable


@pytest.fixture
def invoice(data_dir):
    path = data_dir / "invoices" / "invoice_002.pdf"  # layout C, the format regex was not written for
    truth = json.loads((data_dir / "expected.json").read_text())["invoice_002.pdf"]
    return path, read_text_safely(path.read_bytes(), path.name), truth


def fake_ollama(monkeypatch, answer, sent=None):
    def post_json(url, body):
        if sent is not None:
            sent.append(body)
        return {"response": answer if isinstance(answer, str) else json.dumps(answer),
                "prompt_eval_count": 300, "eval_count": 120}
    monkeypatch.setattr(llm, "post_json", post_json)


def copied_from_text(text):
    """What a well-behaved model returns for invoice_002: values copied verbatim."""
    lines = dict(line.split(": ", 1) for line in text.splitlines() if ": " in line)
    return {"invoice_number": lines["No. Faktur"], "invoice_date": lines["Tgl"], "due_date": lines.get("Jatuh Tempo"),
            "vendor_name": lines["Penjual"], "vendor_tax_id": lines.get("NPWP Penjual"), "subtotal": lines["Jumlah"],
            "tax_amount": lines["PPN 11%"], "total_amount": lines["Total Tagihan"]}


def test_llm_answer_is_normalized_and_validated(monkeypatch, invoice):
    path, text, truth = invoice
    fake_ollama(monkeypatch, copied_from_text(text))

    result = extract_document(path.read_bytes(), path.name, method="llm")

    assert result["method"] == "llm"
    assert result["fields"]["total_amount"] == truth["fields"]["total_amount"]
    assert result["fields"]["invoice_date"] == truth["fields"]["invoice_date"]
    assert result["usage"] == {"prompt_tokens": 300, "output_tokens": 120}


def test_prompt_sent_to_llm_is_redacted(monkeypatch, invoice):
    path, text, truth = invoice
    sent = []
    fake_ollama(monkeypatch, copied_from_text(text), sent)

    extract_document(path.read_bytes(), path.name, method="llm")

    prompt = sent[0]["prompt"]
    assert "@vendor.example" not in prompt and "+62812" not in prompt
    assert "[ACCOUNT_NUMBER]" in prompt
    assert truth["fields"]["invoice_number"] in prompt  # the fields we need are still there


def test_invented_value_from_llm_is_sent_to_review(monkeypatch, invoice):
    path, text, _ = invoice
    fake_ollama(monkeypatch, {**copied_from_text(text), "vendor_name": "PT Hallucinated Vendor"})

    result = extract_document(path.read_bytes(), path.name, method="llm")

    assert result["status"] == "NEEDS_REVIEW"
    assert "NOT_FOUND_IN_DOCUMENT_VENDOR_NAME" in result["review_reasons"]


def test_unparseable_llm_output_is_sent_to_review(monkeypatch, invoice):
    path, _, _ = invoice
    fake_ollama(monkeypatch, "Sure! Here are the fields: ...")

    result = extract_document(path.read_bytes(), path.name, method="llm")

    assert result["status"] == "NEEDS_REVIEW"
    assert result["review_reasons"][0] == "EXTRACTOR_FAILED"
    assert set(result["fields"].values()) == {None}


def test_model_failure_on_one_document_goes_to_review_instead_of_crashing(monkeypatch, invoice):
    path, _, _ = invoice

    def repetition_loop(url, body):  # what Ollama returned for invoice_003 in the real evaluation
        raise urllib.error.HTTPError(url, 500, "error", {}, io.BytesIO(b'{"error":"token repeat limit reached"}'))
    monkeypatch.setattr(llm, "post_json", repetition_loop)

    result = extract_document(path.read_bytes(), path.name, method="llm")

    assert result["status"] == "NEEDS_REVIEW"
    assert result["review_reasons"][0] == "EXTRACTOR_FAILED"
    assert "token repeat limit" in result["extractor_error"]


def test_external_llm_endpoint_is_refused_without_approval(monkeypatch, invoice):
    path, _, _ = invoice
    monkeypatch.setenv("OLLAMA_URL", "https://cheap-llm.example.com")
    monkeypatch.delenv("ALLOW_EXTERNAL_LLM", raising=False)
    monkeypatch.setattr(llm, "post_json", lambda url, body: pytest.fail("invoice text must not be sent"))

    with pytest.raises(LLMUnavailable, match="Refusing to send"):
        extract_document(path.read_bytes(), path.name, method="llm")


def test_unreachable_ollama_raises_a_clear_error(monkeypatch, invoice):
    path, _, _ = invoice

    def down(url, body):
        raise urllib.error.URLError("connection refused")
    monkeypatch.setattr(llm, "post_json", down)

    with pytest.raises(LLMUnavailable, match="ollama serve"):
        extract_document(path.read_bytes(), path.name, method="llm")
