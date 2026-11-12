"""HTTP upload API. Run: uvicorn invoice_extractor.api:app   Docs/upload form: http://127.0.0.1:8000/docs"""
import hmac
import os
from typing import Literal

from fastapi import FastAPI, File, Header, HTTPException, UploadFile

from invoice_extractor.extract import extract_document
from invoice_extractor.intake import MAX_BYTES, RejectedFile
from invoice_extractor.llm import LLMUnavailable
from invoice_extractor.privacy import fingerprint, setup_logging

API_KEY_ENV = "INVOICE_API_KEY"
HTTP_STATUS = {"FILE_TOO_LARGE": 413, "UNSUPPORTED_TYPE": 415, "NOT_A_PDF": 415}

app = FastAPI(title="Invoice extractor")
log = setup_logging()


def require_api_key(given):
    expected = os.environ.get(API_KEY_ENV, "")
    # Fails closed: with no key configured on the server, every request is refused.
    if not expected or not given or not hmac.compare_digest(given.encode(), expected.encode()):
        raise HTTPException(401, "Missing or invalid API key.")


@app.post("/extract")
def extract(file: UploadFile = File(...), method: Literal["llm", "regex"] = "llm",
            x_api_key: str | None = Header(default=None)):
    require_api_key(x_api_key)
    data = file.file.read(MAX_BYTES + 1)  # never read more than one byte past the limit
    try:
        result = extract_document(data, file.filename or "", method)
    except RejectedFile as err:
        log.info("document=%s status=REJECTED reasons=%s", fingerprint(data), err.code)
        raise HTTPException(HTTP_STATUS.get(err.code, 422), {"error": err.code, "message": str(err)})
    except LLMUnavailable as err:
        log.error("%s", err)
        raise HTTPException(503, "The extraction model is unavailable; try again later or use method=regex.")
    log.info("document=%s status=%s reasons=%s", fingerprint(data), result["status"], result["review_reasons"])
    return result
