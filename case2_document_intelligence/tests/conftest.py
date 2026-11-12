import pytest

from invoice_extractor.generate_invoices import generate


@pytest.fixture(scope="session")
def data_dir(tmp_path_factory):
    """Synthetic invoices + expected values + bad files, generated once per test run."""
    path = tmp_path_factory.mktemp("data")
    generate(path, n=9)
    return path
