"""Generate synthetic invoice PDFs, their expected field values, and unsafe test files.

Three layouts: A (English table), B (English letter), C (Indonesian labels).
The regex extractor is written only for A and B; C plays the "new vendor format".
"""
import argparse
import json
import random
from datetime import date, timedelta
from pathlib import Path

from fpdf import FPDF

from invoice_extractor import CASE_DIR

BUYER = "PT Contoh Pembeli"
VENDORS = ["PT Sinar Abadi", "CV Maju Bersama", "PT Teknologi Nusantara", "PT Logistik Prima",
           "CV Kreasi Mandiri", "PT Data Cemerlang"]
ITEMS = [("Laptop maintenance", 750_000), ("Cloud hosting (monthly)", 2_400_000), ("Office chairs", 1_150_000),
         ("Network cabling", 325_000), ("Software license", 4_800_000), ("Printer toner", 280_000)]
MONTHS_ID = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]


def make_invoice(rng, i):
    """Return (layout, line items, expected fields, confidential extras) for invoice number i."""
    issued = date(2026, 7, 1) + timedelta(days=rng.randint(0, 120))
    items = [(name, rng.randint(1, 5), price) for name, price in rng.sample(ITEMS, rng.randint(1, 4))]
    subtotal = sum(qty * price for _, qty, price in items)
    tax = round(subtotal * 0.11)
    fields = {
        "invoice_number": f"INV-2026-{1000 + i}",
        "invoice_date": issued.isoformat(),
        "due_date": (issued + timedelta(days=rng.choice([14, 30, 45]))).isoformat(),
        "vendor_name": rng.choice(VENDORS),
        "vendor_tax_id": f"{rng.randint(0, 99):02d}.{rng.randint(0, 999):03d}.{rng.randint(0, 999):03d}."
                         f"{rng.randint(0, 9)}-{rng.randint(0, 999):03d}.000",
        "subtotal": subtotal,
        "tax_amount": tax,
        "total_amount": subtotal + tax,
    }
    # Planted problems real invoices have.
    if i % 7 == 3:
        fields["vendor_tax_id"] = None  # vendor left out the tax ID
    if i % 8 == 5:
        fields["due_date"] = None  # no payment terms printed
    if i % 11 == 6:
        fields["total_amount"] += 50_000  # vendor's arithmetic error; must be sent to review
    confidential = {"bank_account": str(rng.randint(10**9, 10**10 - 1)),
                    "phone": f"+62812{rng.randint(10**7, 10**8 - 1)}",
                    "email": f"finance{i}@vendor.example"}
    return "ABC"[i % 3], items, fields, confidential


def fmt_date(iso, layout):
    d = date.fromisoformat(iso)
    return {"A": iso, "B": d.strftime("%d/%m/%Y"), "C": f"{d.day} {MONTHS_ID[d.month - 1]} {d.year}"}[layout]


def fmt_money(n, layout):
    dotted = f"{n:,}".replace(",", ".")
    return {"A": f"Rp {n:,}", "B": f"IDR {dotted},00", "C": f"Rp{dotted}"}[layout]


def layout_lines(layout, items, f, c):
    """The text lines of one invoice; a missing field simply has no line."""
    d = lambda key: fmt_date(f[key], layout)
    m = lambda value: fmt_money(value, layout)
    if layout == "A":
        lines = ["INVOICE", f["vendor_name"], f"Invoice No: {f['invoice_number']}", f"Invoice Date: {d('invoice_date')}"]
        lines += [f"Due Date: {d('due_date')}"] if f["due_date"] else []
        lines += [f"Tax ID (NPWP): {f['vendor_tax_id']}"] if f["vendor_tax_id"] else []
        lines += [f"Bill To: {BUYER}", "Description | Qty | Unit Price | Amount"]
        lines += [f"{name} | {q} | {m(p)} | {m(q * p)}" for name, q, p in items]
        lines += [f"Subtotal: {m(f['subtotal'])}", f"Tax (PPN 11%): {m(f['tax_amount'])}", f"Total: {m(f['total_amount'])}",
                  f"Payment to bank account {c['bank_account']} | Contact: {c['phone']} | {c['email']}"]
    elif layout == "B":
        lines = [f["vendor_name"]] + ([f"NPWP {f['vendor_tax_id']}"] if f["vendor_tax_id"] else [])
        lines += [f"Jakarta, {d('invoice_date')}", f"To: {BUYER}", "Dear Finance Team,",
                  f"Please find our invoice with reference {f['invoice_number']} issued on {d('invoice_date')}."]
        lines += [f"Payment is due by {d('due_date')}."] if f["due_date"] else []
        lines += [f"- {q} x {name} @ {m(p)}" for name, q, p in items]
        lines += [f"Amount before tax: {m(f['subtotal'])}", f"VAT 11%: {m(f['tax_amount'])}",
                  f"Amount due: {m(f['total_amount'])}",
                  f"Kindly transfer to account {c['bank_account']}. Questions: {c['email']} / {c['phone']}."]
    else:
        lines = ["FAKTUR", f"Penjual: {f['vendor_name']}"]
        lines += [f"NPWP Penjual: {f['vendor_tax_id']}"] if f["vendor_tax_id"] else []
        lines += [f"No. Faktur: {f['invoice_number']}", f"Tgl: {d('invoice_date')}"]
        lines += [f"Jatuh Tempo: {d('due_date')}"] if f["due_date"] else []
        lines += [f"Pembeli: {BUYER}"] + [f"{name} ({q} x {m(p)})" for name, q, p in items]
        lines += [f"Jumlah: {m(f['subtotal'])}", f"PPN 11%: {m(f['tax_amount'])}", f"Total Tagihan: {m(f['total_amount'])}",
                  f"Rekening: {c['bank_account']} - Telp: {c['phone']} - Email: {c['email']}"]
    return lines


def write_pdf(lines, path):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=10)
    for line in lines:
        pdf.cell(0, 7, line, new_x="LMARGIN", new_y="NEXT")
    pdf.output(str(path))


def write_bad_files(out_dir, valid_pdf):
    """Files the intake step must reject or route to review."""
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "corrupt.pdf").write_bytes(valid_pdf.read_bytes()[:300])
    (out_dir / "fake_executable.pdf").write_bytes(b"MZ\x90\x00" + bytes(200))
    (out_dir / "empty.pdf").write_bytes(b"")
    (out_dir / "invoice.txt").write_text("Invoice No: INV-2026-9999", encoding="utf-8")
    scanned = FPDF()  # an image-like page: shapes only, no text layer
    scanned.add_page()
    scanned.rect(20, 20, 170, 60)
    scanned.output(str(out_dir / "scanned_no_text.pdf"))


def generate(data_dir, n=30, seed=7):
    rng = random.Random(seed)
    invoice_dir = data_dir / "invoices"
    invoice_dir.mkdir(parents=True, exist_ok=True)
    expected = {}
    for i in range(1, n + 1):
        layout, items, fields, confidential = make_invoice(rng, i)
        name = f"invoice_{i:03d}.pdf"
        write_pdf(layout_lines(layout, items, fields, confidential), invoice_dir / name)
        expected[name] = {"layout": layout, "fields": fields}
    (data_dir / "expected.json").write_text(json.dumps(expected, indent=2), encoding="utf-8")
    write_bad_files(data_dir / "bad_files", invoice_dir / "invoice_001.pdf")
    return expected


def main(argv=None):
    parser = argparse.ArgumentParser(description="Generate synthetic invoices and test files.")
    parser.add_argument("--out-dir", type=Path, default=CASE_DIR / "data")
    parser.add_argument("--count", type=int, default=30)
    args = parser.parse_args(argv)
    expected = generate(args.out_dir, args.count)
    print(f"Wrote {len(expected)} invoices, expected.json and bad_files/ to {args.out_dir}")


if __name__ == "__main__":
    main()
