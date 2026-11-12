import numpy as np

from fraud_risk.clean import clean_tables
from fraud_risk.features import LABEL, build_features
from fraud_risk.privacy import minimize
from fraud_risk.train import TRAIN_START, evaluate, select_model, time_split


def test_time_split_is_ordered_and_does_not_overlap(raw_tables, key):
    features = build_features(minimize(clean_tables(raw_tables)[0], key))
    train, val, test = time_split(features)

    assert len(train) and len(val) and len(test)
    assert train["timestamp"].min() >= TRAIN_START  # January is warm-up history only
    assert train["timestamp"].max() < val["timestamp"].min()
    assert val["timestamp"].max() < test["timestamp"].min()
    assert not set(train["transaction_id"]) & set(test["transaction_id"])


def test_select_model_prefers_simpler_when_gain_is_small():
    assert select_model({"rules": 0.30, "logreg": 0.60, "hgb": 0.61}) == "logreg"
    assert select_model({"rules": 0.30, "logreg": 0.60, "hgb": 0.70}) == "hgb"
    assert select_model({"rules": 0.59, "logreg": 0.60, "hgb": 0.60}) == "rules"


def test_always_legit_scores_high_accuracy_but_catches_no_fraud(raw_tables, key):
    features = build_features(minimize(clean_tables(raw_tables)[0], key))
    _, _, test = time_split(features)

    result = evaluate(test, np.zeros(len(test)), capacity=0)

    assert test[LABEL].sum() > 0
    assert result["accuracy_at_capacity"] > 0.95
    assert result["recall_at_capacity"] == 0
