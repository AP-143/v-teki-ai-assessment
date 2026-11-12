"""Privacy controls: data minimization, pseudonymization, and PII-safe logging."""
import hashlib
import hmac
import logging
import os
import re

from fraud_risk.features import LABEL

# Exactly the columns scoring needs (data minimization); input files must provide them.
REQUIRED_COLUMNS = {
    "customers": ["customer_id", "signup_date"],
    "transactions": ["transaction_id", "customer_id", "timestamp", "amount", "merchant_category", "device_id"],
    "login_events": ["customer_id", "timestamp", "success"],
}
KEY_ENV = "FRAUD_PSEUDONYM_KEY"
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE = re.compile(r"(?:\+62|62|0)8\d{7,11}")


def get_key():
    key = os.environ.get(KEY_ENV, "")
    if len(key) < 16:
        raise RuntimeError(f"Set {KEY_ENV} to a secret of at least 16 characters (see .env.example).")
    return key.encode()


def pseudonymize(value, key, prefix):
    """Keyed hash: stable for joins, but not reversible without the key holder's lookup."""
    return prefix + hmac.new(key, value.encode(), hashlib.sha256).hexdigest()[:16]


def minimize(tables, key):
    """Keep only the columns the model needs and replace customer/device IDs with pseudonyms.

    Names, emails, phones, city and the blocked flag never reach feature building.
    """
    out = {}
    for name, columns in REQUIRED_COLUMNS.items():
        df = tables[name]
        df = df[columns + ([LABEL] if LABEL in df else [])].copy()
        ids = {c: pseudonymize(c, key, "P_") for c in df["customer_id"].unique()}
        df["customer_id"] = df["customer_id"].map(ids)
        if "device_id" in df:
            devices = {d: d if d == "UNKNOWN" else pseudonymize(d, key, "D_") for d in df["device_id"].unique()}
            df["device_id"] = df["device_id"].map(devices)
        out[name] = df
    return out


def redact(text):
    return PHONE.sub("[PHONE]", EMAIL.sub("[EMAIL]", text))


class RedactPII(logging.Filter):
    def filter(self, record):
        record.msg, record.args = redact(record.getMessage()), None
        return True


def setup_logging():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    log = logging.getLogger("fraud_risk")
    if not any(isinstance(f, RedactPII) for f in log.filters):
        log.addFilter(RedactPII())
    return log
