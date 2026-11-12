"""Score transactions and write a daily analyst review queue.

The output is a list of cases to review, never a fraud verdict: every row starts
as PENDING_REVIEW and only an analyst decides the outcome.
"""
import argparse
from pathlib import Path

import joblib
import pandas as pd

from fraud_risk import CASE_DIR
from fraud_risk.clean import clean_tables, load_tables
from fraud_risk.features import LABEL, build_features, reason_codes
from fraud_risk.privacy import get_key, minimize, setup_logging
from fraud_risk.train import daily_rank


def score(tables, bundle, start, end, capacity):
    """bundle = {"model", "version", "features"} as saved by train.py."""
    features = build_features(tables)
    part = features[(features["timestamp"] >= start) & (features["timestamp"] < end)]
    scores = bundle["model"].predict_proba(part[bundle["features"]])[:, 1]
    queue = pd.DataFrame({
        "review_date": part["timestamp"].dt.date,
        "daily_rank": daily_rank(part["timestamp"], scores),
        "transaction_id": part["transaction_id"],
        "customer_ref": part["customer_id"],
        "transaction_time": part["timestamp"],
        "amount": part["amount"],
        "risk_score": scores.round(4),
        "reason_codes": reason_codes(part),
        "model_version": bundle["version"],
        "review_status": "PENDING_REVIEW",
    })
    return queue[queue["daily_rank"] <= capacity].sort_values(["review_date", "daily_rank"], ignore_index=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Write the daily fraud review queue.")
    parser.add_argument("--data-dir", type=Path, default=CASE_DIR / "data" / "raw")
    parser.add_argument("--model", type=Path, default=CASE_DIR / "models" / "model.joblib")
    parser.add_argument("--start", default="2026-06-01")
    parser.add_argument("--end", default="2026-07-01", help="exclusive")
    parser.add_argument("--capacity", type=int, default=10, help="analyst reviews per day")
    parser.add_argument("--out", type=Path, default=CASE_DIR / "reports" / "review_queue.csv")
    args = parser.parse_args(argv)
    log = setup_logging()

    try:
        key = get_key()
        if not args.model.is_file():
            raise FileNotFoundError(f"Model file {args.model} not found; run `python -m fraud_risk.train` first.")
        bundle = joblib.load(args.model)  # joblib uses pickle: only load model files this project produced
        tables, _ = clean_tables(load_tables(args.data_dir))
    except (OSError, ValueError, RuntimeError) as err:
        log.error("%s", err)
        raise SystemExit(2)
    tables["transactions"] = tables["transactions"].drop(columns=LABEL, errors="ignore")  # scoring never needs labels
    queue = score(minimize(tables, key), bundle, pd.Timestamp(args.start), pd.Timestamp(args.end), args.capacity)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    queue.to_csv(args.out, index=False)
    log.info("Wrote %d transactions for analyst review to %s", len(queue), args.out)


if __name__ == "__main__":
    main()
