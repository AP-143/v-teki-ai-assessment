"""Generate a synthetic fraud dataset with three related tables.

customers      one row per customer (contains synthetic PII)
transactions   payments with a confirmed-fraud label from analyst review
login_events   successful and failed logins
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from fraud_risk import CASE_DIR
from fraud_risk.features import HIGH_RISK_MERCHANTS, LABEL
from fraud_risk.privacy import setup_logging

START = pd.Timestamp("2026-01-01")
END = pd.Timestamp("2026-07-01")  # exclusive
SAFE_MERCHANTS = ["grocery", "restaurant", "transport", "electronics", "fashion", "utilities"]
RISKY_MERCHANTS = sorted(HIGH_RISK_MERCHANTS)
MERCHANTS = SAFE_MERCHANTS + RISKY_MERCHANTS
MERCHANT_P = [0.95 / len(SAFE_MERCHANTS)] * len(SAFE_MERCHANTS) + [0.05 / len(RISKY_MERCHANTS)] * len(RISKY_MERCHANTS)
FIRST_NAMES = ["Andi", "Budi", "Citra", "Dewi", "Eko", "Fitri", "Gilang", "Hana", "Indra", "Joko", "Kartika", "Lina"]
LAST_NAMES = ["Saputra", "Wijaya", "Lestari", "Pratama", "Hidayat", "Santoso", "Kusuma", "Nugroho"]
CITIES = ["Jakarta", "Bandung", "Surabaya", "Medan", "Makassar", "Yogyakarta"]
# Normal activity by hour of day: quiet at night, busy at lunch and in the evening.
HOUR_P = np.array([1, 1, 1, 1, 1, 2, 4, 6, 7, 7, 7, 8, 9, 8, 7, 7, 7, 8, 9, 9, 8, 6, 4, 2], float)
HOUR_P /= HOUR_P.sum()


def home_device(i):
    return f"DV{i:05d}A"


def new_device(rng):
    return f"DVX{rng.integers(10**9):09d}"


def random_times(rng, n):
    days = rng.integers(0, (END - START).days, n)
    hours = rng.choice(24, n, p=HOUR_P)
    seconds = rng.integers(0, 3600, n)
    return START + pd.to_timedelta(days, "D") + pd.to_timedelta(hours, "h") + pd.to_timedelta(seconds, "s")


def make_customers(rng, n):
    num = np.arange(1, n + 1)
    return pd.DataFrame({
        "customer_id": [f"C{i:05d}" for i in num],
        "full_name": [f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}" for _ in num],
        "email": [f"user{i}@example.com" for i in num],
        "phone": [f"+62812{i:07d}" for i in num],
        "city": rng.choice(CITIES, n),
        "signup_date": (START - pd.to_timedelta(rng.integers(30, 1000, n), "D")),
        "is_blocked": False,
        "blocked_at": pd.NaT,
    })


def make_normal_activity(rng, customers):
    """Everyday payments, each preceded by a login; returns frames and each customer's typical spend."""
    tx, logins = [], []
    base_amount = rng.lognormal(11.5, 0.7, len(customers))  # typical spend, ~100k IDR
    for i, cust in enumerate(customers["customer_id"]):
        n = rng.poisson(22)
        if n == 0:
            continue
        times = random_times(rng, n)
        amounts = base_amount[i] * rng.lognormal(0, 0.5, n)
        big = rng.random(n) < 0.02  # occasional legitimate big purchase
        amounts[big] *= rng.uniform(3, 8, big.sum())
        devices = np.where(rng.random(n) < 0.93, home_device(i), f"DV{i:05d}B").astype(object)
        new_phone = rng.random(n) < 0.03  # customer legitimately switches phone
        devices[new_phone] = [new_device(rng) for _ in range(new_phone.sum())]
        tx.append(pd.DataFrame({
            "customer_id": cust, "timestamp": times, "amount": amounts,
            "merchant_category": rng.choice(MERCHANTS, n, p=MERCHANT_P), "device_id": devices, LABEL: 0,
        }))
        login_times = times - pd.to_timedelta(rng.integers(1, 20, n), "min")
        logins.append(pd.DataFrame({"customer_id": cust, "timestamp": login_times, "device_id": devices, "success": 1}))
        typo = rng.random(n) < 0.05  # mistyped password, then success
        logins.append(pd.DataFrame({
            "customer_id": cust, "timestamp": login_times[typo] - pd.Timedelta(minutes=1),
            "device_id": devices[typo], "success": 0,
        }))
    return tx, logins, base_amount


def make_fraud_attacks(rng, customers, base_amount, n_victims):
    """Account takeovers (new device, failed logins) and scams (victim's own device)."""
    tx, logins, attack_end = [], [], {}
    for i in rng.choice(len(customers), n_victims, replace=False):
        cust = customers["customer_id"].iat[i]
        hour = rng.integers(0, 5) if rng.random() < 0.5 else rng.choice(24, p=HOUR_P)
        t0 = START + pd.Timedelta(days=int(rng.integers(20, 179)), hours=int(hour), minutes=int(rng.integers(60)))
        if rng.random() < 0.8:  # account takeover
            device, n_tx, spend, p_risky = new_device(rng), rng.integers(2, 7), (3, 10), 0.6
            fails = t0 - pd.to_timedelta(rng.integers(5, 60, rng.integers(2, 7)), "min")
            logins.append(pd.DataFrame({"customer_id": cust, "timestamp": fails, "device_id": device, "success": 0}))
        else:  # social-engineering scam: victim pays from their own phone
            device, n_tx, spend, p_risky = home_device(i), rng.integers(1, 3), (2, 6), 0.4
        logins.append(pd.DataFrame({"customer_id": [cust], "timestamp": [t0 - pd.Timedelta(minutes=2)],
                                    "device_id": [device], "success": [1]}))
        times = t0 + pd.to_timedelta(np.cumsum(rng.integers(2, 15, n_tx)), "min")
        risky = rng.random(n_tx) < p_risky
        tx.append(pd.DataFrame({
            "customer_id": cust, "timestamp": times, "amount": base_amount[i] * rng.uniform(*spend, n_tx),
            "merchant_category": np.where(risky, rng.choice(RISKY_MERCHANTS, n_tx), rng.choice(SAFE_MERCHANTS, n_tx)),
            "device_id": device, LABEL: 1,
        }))
        attack_end[cust] = times.max()
    return tx, logins, attack_end


def apply_blocking(rng, customers, attack_end):
    """Most fraud victims are blocked after the attack, but some accounts are blocked
    for unrelated reasons (KYC, disputes), so 'blocked' is not the same as 'fraud'."""
    for cust, end in attack_end.items():
        if rng.random() < 0.8:
            customers.loc[customers["customer_id"] == cust, "blocked_at"] = end + pd.Timedelta(days=int(rng.integers(1, 4)))
    others = ~customers["customer_id"].isin(list(attack_end)) & (rng.random(len(customers)) < 0.02)
    customers.loc[others, "blocked_at"] = random_times(rng, others.sum())
    customers["is_blocked"] = customers["blocked_at"].notna()


def drop_after_block(df, customers):
    blocked_at = df["customer_id"].map(customers.set_index("customer_id")["blocked_at"])
    return df[blocked_at.isna() | (df["timestamp"] < blocked_at)]


def messy_customer_id(rng, customer_id):
    num = int(customer_id[1:])
    formats = [f"c-{num}", f" {num} ", customer_id.lower(), f"CUST_{num}", f"{customer_id} "]
    return formats[rng.integers(len(formats))]


def add_data_quality_issues(rng, transactions, login_events):
    """Plant problems real source systems have; clean.py must handle every one of them."""
    for df in (transactions, login_events):
        messy = rng.random(len(df)) < 0.10
        df.loc[messy, "customer_id"] = [messy_customer_id(rng, c) for c in df.loc[messy, "customer_id"]]
    transactions.loc[rng.random(len(transactions)) < 0.02, "device_id"] = None
    transactions.loc[rng.random(len(transactions)) < 0.01, "timestamp"] = pd.NaT
    retries = transactions.iloc[rng.choice(len(transactions), len(transactions) // 50, replace=False)]
    return pd.concat([transactions, retries]).sort_values("transaction_id", kind="stable", ignore_index=True)


def generate(n_customers=2000, seed=42):
    rng = np.random.default_rng(seed)
    customers = make_customers(rng, n_customers)
    tx, logins, base_amount = make_normal_activity(rng, customers)
    fraud_tx, fraud_logins, attack_end = make_fraud_attacks(rng, customers, base_amount, round(n_customers * 0.075))
    apply_blocking(rng, customers, attack_end)

    transactions = drop_after_block(pd.concat(tx + fraud_tx), customers).sort_values("timestamp", ignore_index=True)
    transactions["amount"] = transactions["amount"].round(-2).astype(int)
    transactions.insert(0, "transaction_id", [f"T{i:07d}" for i in range(1, len(transactions) + 1)])
    login_events = drop_after_block(pd.concat(logins + fraud_logins), customers).sort_values("timestamp", ignore_index=True)
    login_events.insert(0, "login_id", [f"L{i:07d}" for i in range(1, len(login_events) + 1)])
    transactions = add_data_quality_issues(rng, transactions, login_events)
    return {"customers": customers, "transactions": transactions, "login_events": login_events}


def write_tables(tables, out_dir):
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        df.to_csv(out_dir / f"{name}.csv", index=False)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Generate the synthetic fraud dataset.")
    parser.add_argument("--customers", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out-dir", type=Path, default=CASE_DIR / "data" / "raw")
    args = parser.parse_args(argv)
    log = setup_logging()

    tables = generate(args.customers, args.seed)
    write_tables(tables, args.out_dir)
    tx = tables["transactions"]
    log.info("customers=%d transactions=%d login_events=%d fraud_rate=%.2f%%",
             len(tables["customers"]), len(tx), len(tables["login_events"]), 100 * tx[LABEL].mean())
    log.info("Wrote CSV files to %s", args.out_dir)


if __name__ == "__main__":
    main()
