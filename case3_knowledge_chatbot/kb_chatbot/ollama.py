"""Minimal client for a local Ollama server.

Document text and questions go only to this machine by default: other endpoints are
refused unless ALLOW_EXTERNAL_LLM=true is set after the transfer has been approved.
"""
import json
import os
import urllib.error
import urllib.request
from urllib.parse import urlparse

import numpy as np

DEFAULT_URL = "http://localhost:11434"
EMBED_MODEL = "bge-m3"
CHAT_MODEL = "qwen3:4b-instruct"
TIMEOUT_SECONDS = 120


class LLMUnavailable(RuntimeError):
    pass


def endpoint():
    url = os.environ.get("OLLAMA_URL", DEFAULT_URL)
    if urlparse(url).hostname not in {"localhost", "127.0.0.1"} and os.environ.get("ALLOW_EXTERNAL_LLM") != "true":
        raise LLMUnavailable(f"Refusing to send company documents to external endpoint {url}; set "
                             "ALLOW_EXTERNAL_LLM=true only after the transfer is approved.")
    return url


def post_json(path, body):
    """POST to Ollama. Raises LLMUnavailable if the server or model is missing; other HTTP errors propagate."""
    url = endpoint() + path
    request = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return json.load(response)
    except urllib.error.HTTPError as err:
        if err.code == 404:
            raise LLMUnavailable(f"Model {body.get('model')} not found; run `ollama pull {body.get('model')}`.") from err
        raise
    except (urllib.error.URLError, TimeoutError, ConnectionError) as err:
        raise LLMUnavailable(f"Ollama is not reachable at {url} ({err}). Start it with `ollama serve`.") from err


def generate(prompt, schema):
    """Return (parsed JSON reply or None if the model failed on this prompt, token usage)."""
    body = {"model": os.environ.get("OLLAMA_MODEL", CHAT_MODEL), "prompt": prompt, "format": schema,
            "stream": False, "think": False, "options": {"temperature": 0}}
    try:
        reply = post_json("/api/generate", body)
    except urllib.error.HTTPError:  # e.g. a repetition loop on this prompt
        return None, {}
    usage = {"prompt_tokens": reply.get("prompt_eval_count"), "output_tokens": reply.get("eval_count")}
    try:
        return json.loads(reply["response"]), usage
    except (KeyError, TypeError, json.JSONDecodeError):
        return None, usage


def embed(texts):
    """Unit-length embedding vectors, one row per text, so a dot product is the cosine similarity."""
    data = post_json("/api/embed", {"model": os.environ.get("OLLAMA_EMBED_MODEL", EMBED_MODEL), "input": texts})
    vectors = np.array(data["embeddings"], dtype=np.float32)
    return vectors / np.linalg.norm(vectors, axis=1, keepdims=True)
