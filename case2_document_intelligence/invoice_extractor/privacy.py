"""Privacy controls: redact confidential values before any model sees them, and keep logs content-free."""
import hashlib
import logging
import re

EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE = re.compile(r"(?:\+62|\b62|\b0)8\d{7,11}\b")
# Bank accounts are long plain digit runs; amounts, dates, tax IDs and invoice numbers all contain separators.
ACCOUNT_NUMBER = re.compile(r"\b\d{10,16}\b")


def redact(text):
    """Remove values none of the extracted fields need: emails, phone numbers, bank accounts."""
    text = EMAIL.sub("[EMAIL]", text)
    text = PHONE.sub("[PHONE]", text)
    return ACCOUNT_NUMBER.sub("[ACCOUNT_NUMBER]", text)


def fingerprint(data):
    """Short content hash: lets logs refer to a document without revealing its name or content."""
    return hashlib.sha256(data).hexdigest()[:12]


class RedactPII(logging.Filter):
    def filter(self, record):
        record.msg, record.args = redact(record.getMessage()), None
        return True


def setup_logging():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    log = logging.getLogger("invoice_extractor")
    if not any(isinstance(f, RedactPII) for f in log.filters):
        log.addFilter(RedactPII())
    return log
