"""Train and compare fraud-risk models on a time-based split, then save the selected one."""
import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, average_precision_score, confusion_matrix, precision_recall_fscore_support
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from fraud_risk import CASE_DIR
from fraud_risk.clean import clean_tables, load_tables, write_quality_report
from fraud_risk.features import FEATURES, LABEL, build_features, rule_flags
from fraud_risk.privacy import get_key, minimize, setup_logging

# January is history only: 30-day averages and "new device" need a warm-up period.
TRAIN_START, VAL_START, TEST_START, END = map(pd.Timestamp, ["2026-02-01", "2026-05-01", "2026-06-01", "2026-07-01"])
DAILY_CAPACITY = 10  # assumed analyst reviews per day
MIN_GAIN = 0.02  # a more complex model must beat a simpler one by this much validation PR-AUC


class RuleBaseline:
    """Score = share of analyst rules triggered. Needs no training."""

    def fit(self, X, y=None):
        return self

    def predict_proba(self, X):
        score = rule_flags(X).mean(axis=1).to_numpy()
        return np.column_stack([1 - score, score])


def candidates():
    """Ordered from simplest to most complex; select_model relies on this order."""
    return {
        "rules": RuleBaseline(),
        "logreg": make_pipeline(StandardScaler(), LogisticRegression(class_weight="balanced", max_iter=1000)),
        "hgb": HistGradientBoostingClassifier(random_state=42),
    }


def select_model(val_pr_auc):
    """Pick the simplest model within MIN_GAIN of the best validation PR-AUC."""
    best = max(val_pr_auc.values())
    return next(name for name, score in val_pr_auc.items() if score >= best - MIN_GAIN)


def time_split(features):
    t = features["timestamp"]
    return (features[(t >= TRAIN_START) & (t < VAL_START)],
            features[(t >= VAL_START) & (t < TEST_START)],
            features[(t >= TEST_START) & (t < END)])


def daily_rank(timestamps, scores):
    """Rank transactions by score within each calendar day (1 = review first)."""
    s = pd.Series(scores, index=timestamps.index)
    return s.groupby(timestamps.dt.date).rank(ascending=False, method="first").astype(int)


def evaluate(part, scores, capacity=DAILY_CAPACITY):
    """Threshold-free PR-AUC plus metrics for flagging the top `capacity` transactions per day."""
    y = part[LABEL].to_numpy()
    flagged = (daily_rank(part["timestamp"], scores) <= capacity).to_numpy()
    tn, fp, fn, tp = confusion_matrix(y, flagged, labels=[0, 1]).ravel()
    precision, recall, f1, _ = precision_recall_fscore_support(y, flagged, average="binary", zero_division=0)
    return {"pr_auc": round(average_precision_score(y, scores), 4),
            "precision_at_capacity": round(precision, 4), "recall_at_capacity": round(recall, 4),
            "f1_at_capacity": round(f1, 4), "accuracy_at_capacity": round(accuracy_score(y, flagged), 4),
            "tp": int(tp), "fp": int(fp), "fn": int(fn), "tn": int(tn)}


def evaluate_all(models, part, split):
    # "always_legit" flags nothing: it shows why accuracy alone is misleading.
    rows = [{"split": split, "model": "always_legit", **evaluate(part, np.zeros(len(part)), capacity=0)}]
    rows += [{"split": split, "model": name, **evaluate(part, m.predict_proba(part[FEATURES])[:, 1])}
             for name, m in models.items()]
    return rows


def write_metrics(rows, summary, reports_dir):
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "metrics.json").write_text(json.dumps({**summary, "results": rows}, indent=2), encoding="utf-8")
    columns = ["split", "model", "pr_auc", "precision_at_capacity", "recall_at_capacity", "f1_at_capacity",
               "accuracy_at_capacity", "tp", "fp", "fn", "tn"]
    lines = ["# Model results", "",
             f"Selected model: **{summary['selected_model']}** (version `{summary['model_version']}`), chosen on "
             f"validation PR-AUC; a more complex model must win by at least {MIN_GAIN}.", "",
             f"`*_at_capacity` = flag the top {DAILY_CAPACITY} transactions per day for analyst review.", "",
             "| Split | Rows | Fraud cases | Fraud rate |", "|---|---:|---:|---:|"]
    lines += [f"| {s['name']} ({s['from']} to {s['to']}) | {s['rows']} | {s['fraud_cases']} | {s['fraud_rate']:.2%} |"
              for s in summary["splits"]]
    lines += ["", "| " + " | ".join(columns) + " |", "|" + "---|" * len(columns)]
    lines += ["| " + " | ".join(str(r[c]) for c in columns) + " |" for r in rows]
    (reports_dir / "metrics.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Train, compare and save the fraud-risk model.")
    parser.add_argument("--data-dir", type=Path, default=CASE_DIR / "data" / "raw")
    parser.add_argument("--model-out", type=Path, default=CASE_DIR / "models" / "model.joblib")
    parser.add_argument("--reports-dir", type=Path, default=CASE_DIR / "reports")
    args = parser.parse_args(argv)
    log = setup_logging()

    try:
        key = get_key()
        tables, quality = clean_tables(load_tables(args.data_dir))
    except (OSError, ValueError, RuntimeError) as err:
        log.error("%s", err)
        raise SystemExit(2)
    write_quality_report(quality, args.reports_dir / "data_quality.md")

    train, val, test = time_split(build_features(minimize(tables, key)))
    models = candidates()
    for model in models.values():
        model.fit(train[FEATURES], train[LABEL])

    val_rows = evaluate_all(models, val, "validation")
    chosen = select_model({r["model"]: r["pr_auc"] for r in val_rows if r["model"] in models})
    test_rows = evaluate_all(models, test, "test")  # test is scored only after the choice is made

    version = f"{chosen}-v1"
    args.model_out.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": models[chosen], "version": version, "features": FEATURES}, args.model_out)
    splits = [{"name": name, "from": str(part["timestamp"].min().date()), "to": str(part["timestamp"].max().date()),
               "rows": len(part), "fraud_cases": int(part[LABEL].sum()), "fraud_rate": float(part[LABEL].mean())}
              for name, part in [("train", train), ("validation", val), ("test", test)]]
    write_metrics(val_rows + test_rows, {"selected_model": chosen, "model_version": version,
                                         "daily_capacity": DAILY_CAPACITY, "splits": splits}, args.reports_dir)
    log.info("Selected %s (version %s); results in %s", chosen, version, args.reports_dir / "metrics.md")


if __name__ == "__main__":
    main()
