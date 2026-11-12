import json

from invoice_extractor.extract import extract_document


def extract(path):
    return extract_document(path.read_bytes(), path.name)


def test_regex_reads_invoice_number_and_vendor_from_known_layouts(data_dir):
    expected = json.loads((data_dir / "expected.json").read_text())
    for name, truth in expected.items():
        if truth["layout"] == "C":
            continue  # unseen layout: regex is not expected to work there
        fields = extract(data_dir / "invoices" / name)["fields"]
        assert fields["invoice_number"] == truth["fields"]["invoice_number"], name
        assert fields["vendor_name"] == truth["fields"]["vendor_name"], name
