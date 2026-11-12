"""Per-transaction features and the analyst-readable rules built on them.

Point-in-time rule: every history feature only looks at events strictly before the
transaction time, so adding later data can never change an earlier row.
"""
import numpy as np
import pandas as pd

LABEL = "is_confirmed_fraud"
HIGH_RISK_MERCHANTS = {"game_voucher", "crypto", "gift_card"}
FEATURES = [
    "amount",
    "amount_to_avg_30d",
    "txn_count_1h",
    "txn_count_24h",
    "minutes_since_last_txn",
    "is_new_device",
    "failed_logins_24h",
    "is_night",
    "account_age_days",
    "is_high_risk_merchant",
]
NO_HISTORY_MINUTES = 30 * 24 * 60  # value used when the customer has no earlier transaction
HOUR, DAY = np.timedelta64(1, "h"), np.timedelta64(1, "D")

# Each rule is a check an analyst understands; together they are the rule baseline
# and the source of reason codes in the review queue.
REASON_RULES = {
    "HIGH_AMOUNT_VS_HISTORY": lambda f: f["amount_to_avg_30d"] > 3,
    "NEW_DEVICE": lambda f: f["is_new_device"] == 1,
    "FAILED_LOGINS_BEFORE_TXN": lambda f: f["failed_logins_24h"] >= 2,
    "HIGH_VELOCITY": lambda f: f["txn_count_1h"] >= 2,
    "NIGHT_TIME": lambda f: f["is_night"] == 1,
    "HIGH_RISK_MERCHANT": lambda f: f["is_high_risk_merchant"] == 1,
}


def count_before(times, event_times, window):
    """For each t in times: how many event_times fall in [t - window, t)."""
    return np.searchsorted(event_times, times, "left") - np.searchsorted(event_times, times - window, "left")


def customer_history(g, failed_login_times):
    """History features for one customer's transactions, sorted by time."""
    t = g["timestamp"].to_numpy()
    amount = g["amount"].to_numpy(float)
    n_before = np.searchsorted(t, t, "left")  # transactions strictly earlier
    start_30d = np.searchsorted(t, t - 30 * DAY, "left")
    n_30d = n_before - start_30d
    cum = np.concatenate([[0.0], np.cumsum(amount)])
    avg_30d = (cum[n_before] - cum[start_30d]) / np.maximum(n_30d, 1)
    minutes_since = (t - t[np.maximum(n_before - 1, 0)]) / np.timedelta64(1, "m")

    seen, is_new = set(), []
    for device in g["device_id"]:
        is_new.append(int(device == "UNKNOWN" or device not in seen))
        seen.add(device)

    return pd.DataFrame({
        "amount_to_avg_30d": np.divide(amount, avg_30d, out=np.ones_like(amount), where=n_30d > 0),
        "txn_count_1h": count_before(t, t, HOUR),
        "txn_count_24h": count_before(t, t, DAY),
        "minutes_since_last_txn": np.where(n_before > 0, np.minimum(minutes_since, NO_HISTORY_MINUTES), NO_HISTORY_MINUTES),
        "is_new_device": is_new,
        "failed_logins_24h": count_before(t, failed_login_times, DAY),
    }, index=g.index)


def build_features(tables):
    tx = tables["transactions"].sort_values(["customer_id", "timestamp", "transaction_id"], ignore_index=True)
    logins = tables["login_events"]
    failed = logins[logins["success"] == 0].groupby("customer_id")["timestamp"].agg(lambda s: np.sort(s.to_numpy()))
    no_failures = np.array([], dtype=tx["timestamp"].to_numpy().dtype)
    signup = tables["customers"].set_index("customer_id")["signup_date"]

    history = pd.concat(customer_history(g, failed.get(customer, no_failures))
                        for customer, g in tx.groupby("customer_id", sort=False))
    out = tx[["transaction_id", "customer_id", "timestamp", "amount"]].join(history)
    out["is_night"] = (tx["timestamp"].dt.hour < 5).astype(int)
    out["account_age_days"] = (tx["timestamp"] - tx["customer_id"].map(signup)).dt.total_seconds() / 86400
    out["is_high_risk_merchant"] = tx["merchant_category"].isin(HIGH_RISK_MERCHANTS).astype(int)
    if LABEL in tx:
        out[LABEL] = tx[LABEL]
    return out[["transaction_id", "customer_id", "timestamp", *FEATURES] + ([LABEL] if LABEL in tx else [])]


def rule_flags(features):
    return pd.DataFrame({code: rule(features) for code, rule in REASON_RULES.items()})


def reason_codes(features):
    flags = rule_flags(features)
    return flags.apply(lambda row: ";".join(row.index[row]) or "NO_RULE_TRIGGERED", axis=1)
