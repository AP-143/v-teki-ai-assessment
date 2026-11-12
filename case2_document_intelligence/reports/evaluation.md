# Evaluation: regex vs local LLM

30 synthetic invoices (layouts A and B: 20, layout C: 10). Regex was written from A and B only.
Fields are compared after normalization (ISO dates, integer rupiah). A field that is absent on the invoice and returned as null counts as correct.

## Summary

| metric | regex | llm |
|---|---|---|
| documents | 30 | 30 |
| field accuracy | 0.679 | 0.95 |
| missing field rate | 0.332 | 0.03 |
| wrong values | 0 | 5 |
| missing values | 77 | 7 |
| invented values | 0 | 0 |
| documents fully correct | 20 | 24 |
| auto accepted | 13 | 16 |
| needs review | 17 | 14 |
| auto accepted with errors | 0 | 0 |
| review catch rate | 1.0 | 1.0 |
| latency median s | 0.002 | 3.918 |
| latency p95 s | 0.003 | 4.176 |
| avg prompt tokens | 0 | 389 |
| avg output tokens | 0 | 142 |
| local cost idr per doc | 0.0 | 0.16 |
| api cost usd per doc if external | 0.0 | 0.000143 |

## Accuracy by layout

| layout | regex | llm |
|---|---|---|
| A | 1.0 | 0.9 |
| B | 1.0 | 0.988 |
| C | 0.037 | 0.963 |

## Accuracy by field

| field | regex | llm |
|---|---|---|
| invoice_number | 0.667 | 0.967 |
| invoice_date | 0.667 | 0.967 |
| due_date | 0.733 | 0.967 |
| vendor_name | 0.667 | 0.967 |
| vendor_tax_id | 0.7 | 0.9 |
| subtotal | 0.667 | 0.967 |
| tax_amount | 0.667 | 0.967 |
| total_amount | 0.667 | 0.9 |

## Documents with errors: regex (10)

| file | layout | field errors | status | first review reasons |
|---|---|---|---|---|
| invoice_002.pdf | C | invoice_number missing; invoice_date missing; due_date missing; vendor_name missing; vendor_tax_id missing; subtotal missing; tax_amount missing; total_amount missing | NEEDS_REVIEW | MISSING_INVOICE_NUMBER, MISSING_INVOICE_DATE, MISSING_DUE_DATE |
| invoice_005.pdf | C | invoice_number missing; invoice_date missing; vendor_name missing; vendor_tax_id missing; subtotal missing; tax_amount missing; total_amount missing | NEEDS_REVIEW | MISSING_INVOICE_NUMBER, MISSING_INVOICE_DATE, MISSING_DUE_DATE |
| invoice_008.pdf | C | invoice_number missing; invoice_date missing; due_date missing; vendor_name missing; vendor_tax_id missing; subtotal missing; tax_amount missing; total_amount missing | NEEDS_REVIEW | MISSING_INVOICE_NUMBER, MISSING_INVOICE_DATE, MISSING_DUE_DATE |
| invoice_011.pdf | C | invoice_number missing; invoice_date missing; due_date missing; vendor_name missing; vendor_tax_id missing; subtotal missing; tax_amount missing; total_amount missing | NEEDS_REVIEW | MISSING_INVOICE_NUMBER, MISSING_INVOICE_DATE, MISSING_DUE_DATE |
| invoice_014.pdf | C | invoice_number missing; invoice_date missing; due_date missing; vendor_name missing; vendor_tax_id missing; subtotal missing; tax_amount missing; total_amount missing | NEEDS_REVIEW | MISSING_INVOICE_NUMBER, MISSING_INVOICE_DATE, MISSING_DUE_DATE |
| invoice_017.pdf | C | invoice_number missing; invoice_date missing; due_date missing; vendor_name missing; subtotal missing; tax_amount missing; total_amount missing | NEEDS_REVIEW | MISSING_INVOICE_NUMBER, MISSING_INVOICE_DATE, MISSING_DUE_DATE |
| invoice_020.pdf | C | invoice_number missing; invoice_date missing; due_date missing; vendor_name missing; vendor_tax_id missing; subtotal missing; tax_amount missing; total_amount missing | NEEDS_REVIEW | MISSING_INVOICE_NUMBER, MISSING_INVOICE_DATE, MISSING_DUE_DATE |
| invoice_023.pdf | C | invoice_number missing; invoice_date missing; due_date missing; vendor_name missing; vendor_tax_id missing; subtotal missing; tax_amount missing; total_amount missing | NEEDS_REVIEW | MISSING_INVOICE_NUMBER, MISSING_INVOICE_DATE, MISSING_DUE_DATE |
| invoice_026.pdf | C | invoice_number missing; invoice_date missing; due_date missing; vendor_name missing; vendor_tax_id missing; subtotal missing; tax_amount missing; total_amount missing | NEEDS_REVIEW | MISSING_INVOICE_NUMBER, MISSING_INVOICE_DATE, MISSING_DUE_DATE |
| invoice_029.pdf | C | invoice_number missing; invoice_date missing; vendor_name missing; vendor_tax_id missing; subtotal missing; tax_amount missing; total_amount missing | NEEDS_REVIEW | MISSING_INVOICE_NUMBER, MISSING_INVOICE_DATE, MISSING_DUE_DATE |

## Documents with errors: llm (6)

| file | layout | field errors | status | first review reasons |
|---|---|---|---|---|
| invoice_003.pdf | A | invoice_number missing; invoice_date missing; due_date missing; vendor_name missing; subtotal missing; tax_amount missing; total_amount missing | NEEDS_REVIEW | EXTRACTOR_FAILED, MISSING_INVOICE_NUMBER, MISSING_INVOICE_DATE |
| invoice_008.pdf | C | vendor_tax_id wrong (16.756.253.6-400.000 → 16.756.250.6-400.000) | NEEDS_REVIEW | NOT_FOUND_IN_DOCUMENT_VENDOR_TAX_ID |
| invoice_012.pdf | A | total_amount wrong (20146500 → 0) | NEEDS_REVIEW | NOT_FOUND_IN_DOCUMENT_TOTAL_AMOUNT, TOTAL_MISMATCH |
| invoice_022.pdf | B | total_amount wrong (27311550 → 27311050) | NEEDS_REVIEW | NOT_FOUND_IN_DOCUMENT_TOTAL_AMOUNT, TOTAL_MISMATCH |
| invoice_023.pdf | C | vendor_tax_id wrong (64.964.253.8-897.000 → 64.964.250.8-897.000) | NEEDS_REVIEW | NOT_FOUND_IN_DOCUMENT_VENDOR_TAX_ID |
| invoice_029.pdf | C | vendor_tax_id wrong (33.085.622.3-068.000 → 33.085.620.3-068.000) | NEEDS_REVIEW | MISSING_DUE_DATE, NOT_FOUND_IN_DOCUMENT_VENDOR_TAX_ID |

## Unsafe and unsupported files

| file | outcome |
|---|---|
| corrupt.pdf | REJECTED (CORRUPT_PDF) |
| empty.pdf | REJECTED (EMPTY_FILE) |
| fake_executable.pdf | REJECTED (NOT_A_PDF) |
| invoice.txt | REJECTED (UNSUPPORTED_TYPE) |
| scanned_no_text.pdf | NEEDS_REVIEW (NO_TEXT_LAYER) |

## Notes

- Latency measured on a laptop (RTX 3060 6 GB). LLM latency excludes the first call, which loads the model (4.2 s).
- Local cost assumes 100 W while processing and IDR 1,500/kWh.
- 'API cost if external' assumes US$0.15 per 1M input and US$0.6 per 1M output tokens (example small-model pricing, verify before use). No external API was called.
