"""Split the approved documents into sections, embed them locally, and write the search index.

Each document starts with a header block naming the roles allowed to read it.
"""
import argparse
import json
import logging
import re
from pathlib import Path

import numpy as np

from kb_chatbot import CASE_DIR, ollama

log = logging.getLogger("kb_chatbot")
# Text a human reader of the document never sees must not reach the model (hidden prompt injection).
HIDDEN = re.compile(r"<!--.*?-->", re.DOTALL)
# Other ways to hide text from a reader. Removing them reliably needs a full Markdown renderer,
# so a document containing any of them is quarantined instead of cleaned.
UNSAFE = {
    "unterminated HTML comment": re.compile(r"<!--"),
    "raw HTML": re.compile(r"<[A-Za-z/!?][^>]*>"),
    "link reference definition": re.compile(r"^ {0,3}\[[^\]]+\]:", re.MULTILINE),
    "invisible or direction-changing characters": re.compile("[­​-‏‪-‮⁠-⁤﻿]"),
}


class UnsafeDocument(ValueError):
    pass


def read_doc(path):
    _, header, body = path.read_text(encoding="utf-8").split("---", 2)
    meta = {k.strip(): v.strip() for k, v in (line.split(":", 1) for line in header.strip().splitlines())}
    meta["allowed_roles"] = [role.strip() for role in meta["allowed_roles"].split(",")]
    if hidden := HIDDEN.findall(body):
        log.warning("document=%s had %d hidden comment(s); removed before indexing, ask the owner to review",
                    meta["doc_id"], len(hidden))
    body = HIDDEN.sub("", body)
    if problems := [name for name, pattern in UNSAFE.items() if pattern.search(body)]:
        raise UnsafeDocument(f"document={meta['doc_id']} contains {', '.join(problems)}")
    return meta, body


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def split_sections(meta, body):
    """One chunk per '## ' section; the chunk text repeats the title so it is searchable on its own."""
    chunks = []
    for part in re.split(r"^## ", body, flags=re.MULTILINE)[1:]:
        section, _, content = part.partition("\n")
        chunks.append({
            "chunk_id": f"{meta['doc_id']}#{slug(section)}",
            "doc_id": meta["doc_id"],
            "title": meta["title"],
            "section": section.strip(),
            "allowed_roles": meta["allowed_roles"],
            "text": f"{meta['title']} - {section.strip()}\n{content.strip()}",
        })
    return chunks


def build_index(docs_dir, index_dir):
    chunks = []
    for path in sorted(Path(docs_dir).glob("*.md")):
        try:
            chunks += split_sections(*read_doc(path))
        except UnsafeDocument as err:
            log.error("%s; quarantined, not indexed. Ask the owner to remove hidden content.", err)
    vectors = ollama.embed([c["text"] for c in chunks])
    index_dir.mkdir(parents=True, exist_ok=True)
    (index_dir / "chunks.json").write_text(json.dumps(chunks, indent=2), encoding="utf-8")
    np.save(index_dir / "vectors.npy", vectors)
    return chunks


def main(argv=None):
    parser = argparse.ArgumentParser(description="Build the search index from data/docs.")
    parser.add_argument("--docs-dir", type=Path, default=CASE_DIR / "data" / "docs")
    parser.add_argument("--index-dir", type=Path, default=CASE_DIR / "index")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    chunks = build_index(args.docs_dir, args.index_dir)
    print(f"Indexed {len(chunks)} sections from {len({c['doc_id'] for c in chunks})} documents into {args.index_dir}")


if __name__ == "__main__":
    main()
