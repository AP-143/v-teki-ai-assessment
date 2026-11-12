"""Extract invoice fields from PDF files and print JSON.

Extractors return the raw text they found for each field (or None); validate.py
normalizes it and decides whether a human must review the result.
"""
import argparse
import json
import re
from pathlib import Path

from invoice_extractor import FIELDS
from invoice_extractor.intake import RejectedFile, read_text_safely
from invoice_extractor.llm import LLMUnavailable, build_prompt, extract_llm
from invoice_extractor.privacy import fingerprint, setup_logging
from invoice_extractor.validate import validate

# Written from layouts A and B only; layout C is the unseen "new vendor format".
PATTERNS = {
    "invoice_number": [r"Invoice No:\s*(\S+)", r"reference\s+(\S+)"],
    "invoice_date": [r"Invoice Date:\s*(\S+)", r"issued on\s+([\d/]+)"],
    "due_date": [r"Due Date:\s*(\S+)", r"due by\s+([\d/]+)"],
    "vendor_name": [r"^((?:PT|CV) .+)$"],
    "vendor_tax_id": [r"NPWP\)?:?\s*(\d{2}\.\d{3}\.\d{3}\.\d-\d{3}\.\d{3})"],
    "subtotal": [r"Subtotal:\s*(Rp [\d,]+)", r"before tax:\s*(IDR [\d.,]+)"],
    "tax_amount": [r"Tax \(PPN 11%\):\s*(Rp [\d,]+)", r"VAT 11%:\s*(IDR [\d.,]+)"],
    "total_amount": [r"^Total:\s*(Rp [\d,]+)", r"Amount due:\s*(IDR [\d.,]+)"],
}


def extract_regex(text):
    """Return (raw fields, meta); regex has no token usage and cannot fail."""
    found = {}
    for field in FIELDS:
        matches = (re.search(p, text, re.MULTILINE) for p in PATTERNS[field])
        match = next((m for m in matches if m), None)
        found[field] = match.group(1).strip() if match else None
    return found, {}


EXTRACTORS = {"regex": extract_regex, "llm": extract_llm}


def extract_document(data, filename, method="regex"):
    """Full pipeline for one file's bytes. Raises RejectedFile for unsafe input, LLMUnavailable if the model is down."""
    text = read_text_safely(data, filename)
    if not text.strip():  # scanned image: never guess, a human reads it
        return {"method": method, "status": "NEEDS_REVIEW", "review_reasons": ["NO_TEXT_LAYER"],
                "fields": dict.fromkeys(FIELDS)}
    raw, meta = EXTRACTORS[method](text)
    result = {"method": method, **validate(raw, text)}
    if meta.get("error"):
        result["status"] = "NEEDS_REVIEW"
        result["review_reasons"].insert(0, "EXTRACTOR_FAILED")
        result["extractor_error"] = meta["error"]
    usage = {k: v for k, v in meta.items() if k != "error"}
    return {**result, **({"usage": usage} if usage else {})}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Extract invoice fields to JSON.")
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--method", choices=sorted(EXTRACTORS), default="llm")
    parser.add_argument("--show-prompt", action="store_true",
                        help="print exactly what would be sent to the LLM, then exit without sending it")
    args = parser.parse_args(argv)
    log = setup_logging()

    results, rejected = [], 0
    for path in args.files:
        data = path.read_bytes()
        try:
            if args.show_prompt:
                print(f"===== {path.name}\n{build_prompt(read_text_safely(data, path.name))}")
                continue
            result = {"file": path.name, **extract_document(data, path.name, args.method)}
        except LLMUnavailable as err:
            log.error("%s", err)
            raise SystemExit(2)
        except RejectedFile as err:
            rejected += 1
            result = {"file": path.name, "status": "REJECTED", "error": err.code, "message": str(err)}
        log.info("document=%s status=%s reasons=%s", fingerprint(data), result["status"],
                 result.get("review_reasons") or result.get("error"))
        results.append(result)
    if not args.show_prompt:
        print(json.dumps(results, indent=2))
    if rejected:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
