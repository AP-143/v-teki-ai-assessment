"""Evaluate extraction methods against the labelled invoices and write reports/.

Writes evaluation.md (tables), evaluation.json (all numbers) and outputs/<method>/*.json (actual outputs).
"""
import argparse
import json
import math
import statistics
import time
from collections import Counter
from pathlib import Path

from invoice_extractor import CASE_DIR, FIELDS
from invoice_extractor.extract import extract_document
from invoice_extractor.intake import RejectedFile
from invoice_extractor.llm import LLMUnavailable
from invoice_extractor.privacy import setup_logging

# Cost assumptions (not measured bills): laptop GPU power draw and an Indonesian electricity tariff,
# plus an example small-model API price to show what external processing would cost per document.
POWER_WATTS = 100
IDR_PER_KWH = 1_500
API_USD_PER_M_INPUT, API_USD_PER_M_OUTPUT = 0.15, 0.60


def compare(predicted, expected):
    """Per-field outcome: correct, wrong, missing (not extracted) or invented (extracted but not on the invoice)."""
    outcomes = {}
    for f in FIELDS:
        p, e = predicted.get(f), expected.get(f)
        outcomes[f] = "correct" if p == e else "missing" if p is None else "invented" if e is None else "wrong"
    return outcomes


def run_method(method, data_dir, expected):
    rows = []
    for name, truth in expected.items():
        data = (data_dir / "invoices" / name).read_bytes()
        start = time.perf_counter()
        result = extract_document(data, name, method)
        seconds = time.perf_counter() - start
        rows.append({"file": name, "layout": truth["layout"], "seconds": seconds, "result": result,
                     "outcomes": compare(result["fields"], truth["fields"]),
                     "present": sum(v is not None for v in truth["fields"].values())})
    return rows


def p95(values):
    return sorted(values)[math.ceil(0.95 * len(values)) - 1]


def summarize(rows):
    counts = Counter(o for r in rows for o in r["outcomes"].values())
    has_error = [any(o != "correct" for o in r["outcomes"].values()) for r in rows]
    review = [r["result"]["status"] == "NEEDS_REVIEW" for r in rows]
    seconds = [r["seconds"] for r in rows]
    prompt_tokens = [r["result"].get("usage", {}).get("prompt_tokens") or 0 for r in rows]
    output_tokens = [r["result"].get("usage", {}).get("output_tokens") or 0 for r in rows]

    def accuracy(selected):
        outcomes = [o for r in rows for f, o in r["outcomes"].items() if selected(r, f)]
        return round(outcomes.count("correct") / len(outcomes), 3)

    median_s = statistics.median(seconds)
    return {
        "documents": len(rows),
        "field_accuracy": accuracy(lambda r, f: True),
        "missing_field_rate": round(counts["missing"] / sum(r["present"] for r in rows), 3),
        "wrong_values": counts["wrong"],
        "missing_values": counts["missing"],
        "invented_values": counts["invented"],
        "documents_fully_correct": has_error.count(False),
        "auto_accepted": review.count(False),
        "needs_review": review.count(True),
        "auto_accepted_with_errors": sum(e and not rv for e, rv in zip(has_error, review)),
        "review_catch_rate": round(sum(e and rv for e, rv in zip(has_error, review)) / max(sum(has_error), 1), 3),
        "latency_median_s": round(median_s, 3),
        "latency_p95_s": round(p95(seconds), 3),
        "avg_prompt_tokens": round(statistics.mean(prompt_tokens)),
        "avg_output_tokens": round(statistics.mean(output_tokens)),
        "local_cost_idr_per_doc": round(median_s / 3600 * POWER_WATTS / 1000 * IDR_PER_KWH, 2),
        "api_cost_usd_per_doc_if_external": round((statistics.mean(prompt_tokens) * API_USD_PER_M_INPUT
                                                   + statistics.mean(output_tokens) * API_USD_PER_M_OUTPUT) / 1e6, 6),
        "accuracy_by_layout": {lay: accuracy(lambda r, f, lay=lay: r["layout"] == lay) for lay in "ABC"},
        "accuracy_by_field": {fld: accuracy(lambda r, f, fld=fld: f == fld) for fld in FIELDS},
    }


def bad_file_outcomes(data_dir):
    outcomes = {}
    for path in sorted((data_dir / "bad_files").iterdir()):
        try:
            result = extract_document(path.read_bytes(), path.name)
            outcomes[path.name] = f"{result['status']} ({', '.join(result['review_reasons'])})"
        except RejectedFile as err:
            outcomes[path.name] = f"REJECTED ({err.code})"
    return outcomes


def table(header, rows):
    return ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)] + \
           ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]


def write_reports(summaries, all_rows, expected, bad_files, cold_start_s, reports_dir):
    for method, rows in all_rows.items():
        out_dir = reports_dir / "outputs" / method
        out_dir.mkdir(parents=True, exist_ok=True)
        for r in rows:
            (out_dir / r["file"].replace(".pdf", ".json")).write_text(json.dumps(r["result"], indent=2), encoding="utf-8")
    (reports_dir / "evaluation.json").write_text(json.dumps(summaries, indent=2), encoding="utf-8")

    methods = list(summaries)
    metric_rows = [[key.replace("_", " ")] + [summaries[m][key] for m in methods]
                   for key in summaries[methods[0]] if key not in ("accuracy_by_layout", "accuracy_by_field")]
    lines = ["# Evaluation: regex vs local LLM", "",
             f"{len(expected)} synthetic invoices (layouts A and B: 20, layout C: 10). Regex was written from A and B only.",
             "Fields are compared after normalization (ISO dates, integer rupiah). A field that is absent on the invoice "
             "and returned as null counts as correct.", "",
             "## Summary", ""] + table(["metric"] + methods, metric_rows)
    lines += ["", "## Accuracy by layout", ""] + table(
        ["layout"] + methods, [[lay] + [summaries[m]["accuracy_by_layout"][lay] for m in methods] for lay in "ABC"])
    lines += ["", "## Accuracy by field", ""] + table(
        ["field"] + methods, [[f] + [summaries[m]["accuracy_by_field"][f] for m in methods] for f in FIELDS])
    for method, rows in all_rows.items():
        errors = []
        for r in rows:
            wrong = [f"{f} {o}" + (f" ({expected[r['file']]['fields'][f]} → {r['result']['fields'][f]})" if o == "wrong" else "")
                     for f, o in r["outcomes"].items() if o != "correct"]
            if wrong:
                errors.append([r["file"], r["layout"], "; ".join(wrong), r["result"]["status"],
                               ", ".join(r["result"]["review_reasons"][:3])])
        lines += ["", f"## Documents with errors: {method} ({len(errors)})", ""]
        lines += table(["file", "layout", "field errors", "status", "first review reasons"], errors) if errors else ["None."]
    lines += ["", "## Unsafe and unsupported files", ""] + table(["file", "outcome"], list(bad_files.items()))
    lines += ["", "## Notes", "",
              f"- Latency measured on a laptop (RTX 3060 6 GB). LLM latency excludes the first call, which loads the "
              f"model ({cold_start_s:.1f} s)." if cold_start_s else "- Latency measured on a laptop.",
              f"- Local cost assumes {POWER_WATTS} W while processing and IDR {IDR_PER_KWH:,}/kWh.",
              f"- 'API cost if external' assumes US${API_USD_PER_M_INPUT} per 1M input and US${API_USD_PER_M_OUTPUT} per "
              "1M output tokens (example small-model pricing, verify before use). No external API was called."]
    (reports_dir / "evaluation.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Evaluate regex and LLM extraction on the labelled invoices.")
    parser.add_argument("--data-dir", type=Path, default=CASE_DIR / "data")
    parser.add_argument("--reports-dir", type=Path, default=CASE_DIR / "reports")
    parser.add_argument("--methods", nargs="+", choices=["regex", "llm"], default=["regex", "llm"])
    args = parser.parse_args(argv)
    log = setup_logging()
    expected = json.loads((args.data_dir / "expected.json").read_text(encoding="utf-8"))

    cold_start_s, all_rows = None, {}
    try:
        for method in args.methods:
            if method == "llm":  # load the model once so per-document latency is not dominated by startup
                first = args.data_dir / "invoices" / next(iter(expected))
                start = time.perf_counter()
                extract_document(first.read_bytes(), first.name, "llm")
                cold_start_s = time.perf_counter() - start
            log.info("Evaluating %s on %d invoices", method, len(expected))
            all_rows[method] = run_method(method, args.data_dir, expected)
    except LLMUnavailable as err:
        log.error("%s (or run with --methods regex)", err)
        raise SystemExit(2)

    summaries = {m: summarize(rows) for m, rows in all_rows.items()}
    write_reports(summaries, all_rows, expected, bad_file_outcomes(args.data_dir), cold_start_s, args.reports_dir)
    for m, s in summaries.items():
        log.info("%s: field accuracy %.3f, auto-accepted with errors %d", m, s["field_accuracy"], s["auto_accepted_with_errors"])


if __name__ == "__main__":
    main()
