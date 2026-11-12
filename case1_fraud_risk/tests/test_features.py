import pandas as pd

from fraud_risk.clean import clean_tables
from fraud_risk.features import FEATURES, NO_HISTORY_MINUTES, build_features
from fraud_risk.privacy import minimize


def ts(text):
    return pd.Timestamp(f"2026-03-10 {text}")


def test_history_features_on_a_hand_checked_example():
    tables = {
        "customers": pd.DataFrame({"customer_id": ["P_a"], "signup_date": [pd.Timestamp("2026-03-01")]}),
        "transactions": pd.DataFrame({
            "transaction_id": ["T1", "T2", "T3"],
            "customer_id": ["P_a"] * 3,
            "timestamp": [ts("10:00"), ts("10:30"), ts("12:00")],
            "amount": [100, 300, 1000],
            "merchant_category": ["grocery", "grocery", "crypto"],
            "device_id": ["D_1", "D_1", "D_2"],
        }),
        "login_events": pd.DataFrame({
            "customer_id": ["P_a"] * 2,
            "timestamp": [ts("09:50"), ts("10:45")],
            "success": [0, 0],
        }),
    }
    f = build_features(tables).set_index("transaction_id")

    assert f["txn_count_1h"].tolist() == [0, 1, 0]
    assert f["txn_count_24h"].tolist() == [0, 1, 2]
    assert f["amount_to_avg_30d"].tolist() == [1.0, 3.0, 5.0]  # 300/100, 1000/avg(100, 300)
    assert f["minutes_since_last_txn"].tolist() == [NO_HISTORY_MINUTES, 30, 90]
    assert f["is_new_device"].tolist() == [1, 0, 1]
    assert f["failed_logins_24h"].tolist() == [1, 1, 2]  # 10:45 failure counts only for 12:00
    assert f["is_high_risk_merchant"].tolist() == [0, 0, 1]
    assert f["account_age_days"].round(2).tolist() == [9.42, 9.44, 9.5]


def test_features_ignore_events_after_the_transaction(raw_tables, key):
    """Point-in-time check: deleting everything after the cutoff must not change earlier rows."""
    tables = minimize(clean_tables(raw_tables)[0], key)
    cutoff = pd.Timestamp("2026-04-01")
    past_only = {name: df[df["timestamp"] < cutoff] if "timestamp" in df else df for name, df in tables.items()}

    full = build_features(tables)
    truncated = build_features(past_only)

    columns = ["transaction_id", *FEATURES]
    expected = full.loc[full["timestamp"] < cutoff, columns].sort_values("transaction_id", ignore_index=True)
    actual = truncated[columns].sort_values("transaction_id", ignore_index=True)
    assert len(actual) > 1000
    pd.testing.assert_frame_equal(actual, expected)
