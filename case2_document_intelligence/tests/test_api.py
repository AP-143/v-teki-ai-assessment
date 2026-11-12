import urllib.error

import pytest
from fastapi.testclient import TestClient

from invoice_extractor import llm
from invoice_extractor.api import API_KEY_ENV, app
from invoice_extractor.intake import MAX_BYTES

KEY = "test-api-key"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv(API_KEY_ENV, KEY)
    return TestClient(app)


def upload(client, name, data, key=KEY, method="regex"):
    headers = {"X-API-Key": key} if key else {}
    return client.post(f"/extract?method={method}", files={"file": (name, data, "application/pdf")}, headers=headers)


def test_valid_invoice_returns_structured_json(client, data_dir):
    response = upload(client, "invoice_001.pdf", (data_dir / "invoices" / "invoice_001.pdf").read_bytes())
    assert response.status_code == 200
    assert response.json()["fields"]["invoice_number"] == "INV-2026-1001"


@pytest.mark.parametrize("key", [None, "wrong-key"])
def test_request_without_valid_api_key_is_refused(client, data_dir, key):
    response = upload(client, "invoice_001.pdf", (data_dir / "invoices" / "invoice_001.pdf").read_bytes(), key=key)
    assert response.status_code == 401


def test_api_refuses_everything_when_no_key_is_configured(monkeypatch, data_dir):
    monkeypatch.delenv(API_KEY_ENV, raising=False)
    response = upload(TestClient(app), "invoice_001.pdf", (data_dir / "invoices" / "invoice_001.pdf").read_bytes())
    assert response.status_code == 401


@pytest.mark.parametrize("name, data, status, code", [
    ("invoice.pdf", b"MZ\x90\x00" + bytes(200), 415, "NOT_A_PDF"),
    ("big.pdf", b"%PDF-" + bytes(MAX_BYTES + 10), 413, "FILE_TOO_LARGE"),
    ("../../etc/passwd.pdf", b"%PDF-1.4 broken", 422, "CORRUPT_PDF"),
])
def test_unsafe_uploads_get_a_4xx_not_a_crash(client, name, data, status, code):
    response = upload(client, name, data)
    assert response.status_code == status
    assert response.json()["detail"]["error"] == code


def test_llm_down_returns_503(client, data_dir, monkeypatch):
    def down(url, body):
        raise urllib.error.URLError("connection refused")
    monkeypatch.setattr(llm, "post_json", down)

    response = upload(client, "invoice_001.pdf", (data_dir / "invoices" / "invoice_001.pdf").read_bytes(), method="llm")
    assert response.status_code == 503
