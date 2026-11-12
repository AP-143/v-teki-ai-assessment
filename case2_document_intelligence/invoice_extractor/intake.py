"""Safe intake: decide whether an uploaded file may be parsed, then read its text.

Checks run on the file's bytes, never on its name alone, and nothing is written to disk.
"""
import io

from pypdf import PdfReader

MAX_BYTES = 5 * 1024 * 1024
MAX_PAGES = 5


class RejectedFile(ValueError):
    """The file is unsafe or unsupported; `code` is a stable, machine-readable reason."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def read_text_safely(data, filename):
    """Return the PDF's text layer ('' for a scanned PDF) or raise RejectedFile."""
    if not filename.lower().endswith(".pdf"):
        raise RejectedFile("UNSUPPORTED_TYPE", "Only .pdf files are accepted.")
    if not data:
        raise RejectedFile("EMPTY_FILE", "The file is empty.")
    if len(data) > MAX_BYTES:
        raise RejectedFile("FILE_TOO_LARGE", f"Files larger than {MAX_BYTES // 1024 // 1024} MB are not accepted.")
    if not data.startswith(b"%PDF-"):
        raise RejectedFile("NOT_A_PDF", "The file content is not a PDF, whatever its extension says.")
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise RejectedFile("ENCRYPTED_PDF", "Password-protected PDFs are not accepted.")
        if len(reader.pages) > MAX_PAGES:
            raise RejectedFile("TOO_MANY_PAGES", f"Invoices longer than {MAX_PAGES} pages are not accepted.")
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except RejectedFile:
        raise
    except Exception as err:  # pypdf raises many different types on malformed input
        raise RejectedFile("CORRUPT_PDF", "The PDF could not be parsed.") from err
