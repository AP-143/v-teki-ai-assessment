import pandas as pd
import pytest

from fraud_risk import predict, train
from fraud_risk.clean import clean_tables
from fraud_risk.features import LABEL
from fraud_risk.predict import score
from fraud_risk.privacy import minimize


def test_review_queue_has_score_reasons_version_and_no_verdict(raw_tables, key, rules_bundle):
    tables, _ = clean_tables(raw_tables)
    tables["transactions"] = tables["transactions"].drop(columns=LABEL)
    queue = score(minimize(tables, key), rules_bundle,
                  pd.Timestamp("2026-06-01"), pd.Timestamp("2026-07-01"), capacity=10)

    assert len(queue) > 0
    assert queue.groupby("review_date").size().max() <= 10
    assert queue["risk_score"].between(0, 1).all()
    assert (queue["reason_codes"].str.len() > 0).all()
    assert (queue["model_version"] == "rules-v1").all()
    assert (queue["review_status"] == "PENDING_REVIEW").all()
    assert LABEL not in queue.columns


def test_train_then_predict_end_to_end(data_dir, tmp_path):
    model = tmp_path / "model.joblib"
    train.main(["--data-dir", str(data_dir), "--model-out", str(model), "--reports-dir", str(tmp_path / "reports")])
    out = tmp_path / "queue.csv"
    predict.main(["--data-dir", str(data_dir), "--model", str(model), "--out", str(out)])

    queue = pd.read_csv(out)
    assert (tmp_path / "reports" / "metrics.md").exists()
    assert queue["model_version"].iloc[0].endswith("-v1")
    assert (queue["review_status"] == "PENDING_REVIEW").all()


def test_missing_model_file_fails_with_a_clear_message(data_dir, tmp_path, caplog):
    with pytest.raises(SystemExit) as exit_info:
        predict.main(["--data-dir", str(data_dir), "--model", str(tmp_path / "nope.joblib"),
                      "--out", str(tmp_path / "queue.csv")])

    assert exit_info.value.code == 2
    assert "run `python -m fraud_risk.train` first" in caplog.text
