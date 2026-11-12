"""Privacy and security tests. Each one checks that something unsafe does NOT happen."""
import logging

import pandas as pd
import pytest

from fraud_risk import predict
from fraud_risk.clean import clean_tables
from fraud_risk.privacy import KEY_ENV, minimize, pseudonymize, setup_logging

PII_COLUMNS = ["full_name", "email", "phone", "city", "is_blocked", "blocked_at"]


def test_minimize_drops_pii_and_blocked_flag(raw_tables, key):
    tables, _ = clean_tables(raw_tables)
    minimized = minimize(tables, key)

    for df in minimized.values():
        assert not set(PII_COLUMNS) & set(df.columns)
        assert df["customer_id"].str.startswith("P_").all()


def test_review_queue_file_contains_no_raw_identifiers(data_dir, model_path, raw_tables, tmp_path):
    out = tmp_path / "queue.csv"
    predict.main(["--data-dir", str(data_dir), "--model", str(model_path), "--out", str(out)])

    text = out.read_text(encoding="utf-8")
    customers = raw_tables["customers"]
    assert not set(PII_COLUMNS) & set(pd.read_csv(out).columns)
    for column in ["email", "phone", "customer_id"]:
        assert not any(value in text for value in customers[column]), f"raw {column} leaked into output"


def test_logs_mask_email_and_phone(caplog):
    log = setup_logging()
    with caplog.at_level(logging.INFO, logger="fraud_risk"):
        log.info("Customer contact %s %s", "user12@example.com", "+6281200000012")

    assert "user12@example.com" not in caplog.text
    assert "+6281200000012" not in caplog.text
    assert "[EMAIL]" in caplog.text and "[PHONE]" in caplog.text


def test_input_missing_required_column_is_rejected(data_dir, model_path, tmp_path, caplog):
    tx = pd.read_csv(data_dir / "transactions.csv")
    tx.drop(columns="amount").to_csv(data_dir / "transactions.csv", index=False)

    with pytest.raises(SystemExit) as exit_info:
        predict.main(["--data-dir", str(data_dir), "--model", str(model_path), "--out", str(tmp_path / "queue.csv")])

    assert exit_info.value.code == 2
    assert "missing required columns: ['amount']" in caplog.text
    assert not (tmp_path / "queue.csv").exists()


def test_missing_pseudonym_key_stops_the_run(data_dir, model_path, tmp_path, monkeypatch, caplog):
    monkeypatch.delenv(KEY_ENV)

    with pytest.raises(SystemExit):
        predict.main(["--data-dir", str(data_dir), "--model", str(model_path), "--out", str(tmp_path / "queue.csv")])

    assert KEY_ENV in caplog.text
    assert not (tmp_path / "queue.csv").exists()


def test_pseudonym_depends_on_secret_key():
    assert pseudonymize("C00012", b"key-one-0123456789", "P_") != pseudonymize("C00012", b"key-two-0123456789", "P_")
    assert pseudonymize("C00012", b"key-one-0123456789", "P_") == pseudonymize("C00012", b"key-one-0123456789", "P_")
