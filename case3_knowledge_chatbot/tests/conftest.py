import re
import zlib

import numpy as np
import pytest

from kb_chatbot import CASE_DIR, ollama
from kb_chatbot.ingest import build_index
from kb_chatbot.retrieve import load_index


def fake_embed(texts):
    """Bag-of-words hashing vectors: deterministic and offline, good enough to test the plumbing."""
    vectors = np.zeros((len(texts), 512), dtype=np.float32)
    for i, text in enumerate(texts):
        for word in re.findall(r"[a-z0-9]+", text.lower()):
            vectors[i, zlib.crc32(word.encode()) % 512] += 1
    return vectors / np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-9)


@pytest.fixture(autouse=True)
def offline_embeddings(monkeypatch):
    monkeypatch.setattr(ollama, "embed", fake_embed)


@pytest.fixture
def index(tmp_path):
    build_index(CASE_DIR / "data" / "docs", tmp_path / "index")
    return load_index(tmp_path / "index")
