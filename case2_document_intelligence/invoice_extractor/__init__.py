"""Invoice field extraction prototype (V-TEKI assessment, Case 2)."""
from pathlib import Path

CASE_DIR = Path(__file__).resolve().parents[1]
FIELDS = [
    "invoice_number",
    "invoice_date",
    "due_date",
    "vendor_name",
    "vendor_tax_id",
    "subtotal",
    "tax_amount",
    "total_amount",
]
