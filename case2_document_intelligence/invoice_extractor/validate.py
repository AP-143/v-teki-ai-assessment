"""Normalize extracted values, check business rules, and decide whether a human must review.

There is no numeric confidence score: an extractor's self-reported confidence is not a
calibrated probability. Instead every result gets a status and the concrete reasons.
"""
import re
from datetime import date

from invoice_extractor import FIELDS

MONTHS = {m: i for i, names in enumerate(
    [("jan",), ("feb",), ("mar",), ("apr",), ("may", "mei"), ("jun",), ("jul",), ("aug", "agu"), ("sep",),
     ("oct", "okt"), ("nov",), ("dec", "des")], start=1) for m in names}
TAX_ID = re.compile(r"\d{2}\.\d{3}\.\d{3}\.\d-\d{3}\.\d{3}")
AMOUNT_FIELDS = {"subtotal", "tax_amount", "total_amount"}
DATE_FIELDS = {"invoice_date", "due_date"}
VAT_RATE = 0.11


def normalize_date(raw):
    """'2026-10-15', '15/10/2026', '15 Okt 2026', '15 Oct 2026' -> '2026-10-15'; None if not a date."""
    raw = raw.strip()
    try:
        if m := re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", raw):
            y, mo, d = map(int, m.groups())
        elif m := re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", raw):  # Indonesian order: day first
            d, mo, y = map(int, m.groups())
        elif m := re.fullmatch(r"(\d{1,2})\s+([A-Za-z]{3})[a-z]*\s+(\d{4})", raw):
            d, mo, y = int(m[1]), MONTHS[m[2].lower()], int(m[3])
        else:
            return None
        return date(y, mo, d).isoformat()
    except (KeyError, ValueError):
        return None


def normalize_amount(raw):
    """'Rp 12,120,000', 'IDR 4.075.000,00', 'Rp2.400.000' -> integer rupiah; None if no digits."""
    raw = re.sub(r"[.,]\d{2}$", "", raw.strip())  # drop cents; thousand groups always have 3 digits
    digits = re.sub(r"\D", "", raw)
    return int(digits) if digits else None


def normalize(field, raw):
    if field in DATE_FIELDS:
        return normalize_date(raw)
    if field in AMOUNT_FIELDS:
        return normalize_amount(raw)
    if field == "vendor_tax_id":
        return raw.strip() if TAX_ID.fullmatch(raw.strip()) else None
    return raw.strip() or None


def squash(text):
    return re.sub(r"\s+", " ", text).strip().lower()


def validate(raw_fields, source_text):
    """Return {"status", "review_reasons", "fields"} for one document's raw extraction."""
    fields, reasons = {}, []
    doc = squash(source_text)
    for field in FIELDS:
        raw = raw_fields.get(field)
        if raw is None or not str(raw).strip():
            fields[field] = None
            reasons.append(f"MISSING_{field.upper()}")
            continue
        raw = str(raw)
        if squash(raw) not in doc:  # an extractor must copy text, not invent it
            reasons.append(f"NOT_FOUND_IN_DOCUMENT_{field.upper()}")
        fields[field] = normalize(field, raw)
        if fields[field] is None:
            reasons.append(f"INVALID_{field.upper()}")

    subtotal, tax, total = fields["subtotal"], fields["tax_amount"], fields["total_amount"]
    if None not in (subtotal, tax, total):
        if subtotal + tax != total:
            reasons.append("TOTAL_MISMATCH")
        if abs(tax - subtotal * VAT_RATE) > 1:
            reasons.append("TAX_NOT_11_PERCENT")
    if fields["invoice_date"] and fields["due_date"] and fields["due_date"] < fields["invoice_date"]:
        reasons.append("DUE_DATE_BEFORE_INVOICE_DATE")

    return {"status": "NEEDS_REVIEW" if reasons else "AUTO_ACCEPTED", "review_reasons": reasons, "fields": fields}
