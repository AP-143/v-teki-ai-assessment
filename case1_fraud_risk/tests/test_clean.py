import pytest

from fraud_risk.clean import clean_tables, normalize_customer_id


@pytest.mark.parametrize("raw, expected", [
    ("C00012", "C00012"),
    ("c-12", "C00012"),
    (" 12 ", "C00012"),
    ("CUST_12", "C00012"),
    ("C00012 ", "C00012"),
    ("abc", None),
    (None, None),
])
def test_normalize_customer_id(raw, expected):
    assert normalize_customer_id(raw) == expected


def test_clean_removes_duplicates_and_unusable_rows(raw_tables):
    raw_tx = raw_tables["transactions"]
    assert raw_tx["transaction_id"].duplicated().any(), "fixture should contain duplicate events"

    tables, report = clean_tables(raw_tables)
    tx = tables["transactions"]

    assert tx["transaction_id"].is_unique
    assert tx["timestamp"].notna().all()
    assert tx["device_id"].notna().all()
    assert tx["customer_id"].str.fullmatch(r"C\d{5}").all()
    assert report["transactions: duplicate events (removed)"] == raw_tx["transaction_id"].duplicated().sum()


def test_some_blocked_accounts_are_not_fraud(raw_tables):
    _, report = clean_tables(raw_tables)
    assert report["customers: blocked WITHOUT confirmed fraud (why is_blocked is not a label)"] > 0
