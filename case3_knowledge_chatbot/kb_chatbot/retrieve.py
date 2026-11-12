"""Role-based semantic search over the section index.

Access is enforced here, before scoring: sections a role may not read are never
scored, returned, or shown to the language model.
"""
import json

import numpy as np

from kb_chatbot import ollama


def load_index(index_dir):
    if not (index_dir / "vectors.npy").exists():
        raise FileNotFoundError(f"No index in {index_dir}; run `python -m kb_chatbot.ingest` first.")
    return json.loads((index_dir / "chunks.json").read_text(encoding="utf-8")), np.load(index_dir / "vectors.npy")


def role_of(user, users_path):
    """The role comes from the user directory (standing in for company login), never from the question."""
    role = json.loads(users_path.read_text(encoding="utf-8")).get(user)
    if role is None:
        raise PermissionError(f"Unknown user {user!r}.")
    return role


def search(question, role, index, k=3):
    """Top-k (chunk, cosine score) pairs the role may read, best first."""
    chunks, vectors = index
    allowed = np.flatnonzero([role in c["allowed_roles"] for c in chunks])
    scores = vectors[allowed] @ ollama.embed([question])[0]
    return [(chunks[i], float(s)) for i, s in sorted(zip(allowed, scores), key=lambda p: -p[1])[:k]]
