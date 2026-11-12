"""Split the approved documents into sections, embed them locally, and write the search index.

Each document starts with a header block naming the roles allowed to read it and who approved it.
A document is quarantined (not indexed) when it is not approved, hides text from readers, or
contains instructions aimed at the AI assistant.
"""
import argparse
import json
import logging
import re
import unicodedata
from datetime import date
from pathlib import Path

import numpy as np
from markdown_it import MarkdownIt

from kb_chatbot import CASE_DIR, ollama

log = logging.getLogger("kb_chatbot")
# Text a human reader of the document never sees must not reach the model (hidden prompt injection).
# Closed comments are removed (the demo document has one); anything else hidden quarantines the document.
HIDDEN = re.compile(r"<!--.*?-->", re.DOTALL)
COMMONMARK = MarkdownIt("commonmark")
# Header values flow into chunk text, so they must be plain text.
PLAIN_HEADER = re.compile(r"[\w .,&()'/-]+")
# Visible text that talks to the AI instead of to employees (English and Indonesian).
# shortcut: a phrase list is easy to paraphrase around; document approval is the main control.
AI_INSTRUCTION = re.compile("|".join([
    r"\b(ignore|disregard|forget|override)\b.{0,30}\b(instructions?|rules|prompts?|guidelines)\b",
    r"\b(system|developer|hidden)\s+(prompt|note|message|instructions?)\b",
    r"\b(note|message|instructions?)\s+(to|for)\s+(the\s+)?(ai|assistant|chatbot|model|llm)\b",
    r"\b(you are now|act as|pretend to be)\b",
    r"\baccess controls?\s+(are|is)\s+(disabled|off|bypassed|turned off)\b",
    r"\b(user|requester) is (authori[sz]ed|an? admin)",
    r"\babaikan\b.{0,30}\b(instruksi|aturan|perintah)\b",
    r"\b(catatan|pesan|instruksi)\s+untuk\s+(ai|asisten|chatbot|model)\b",
    r"\bkontrol akses\s+(dimatikan|dinonaktifkan)\b",
]), re.IGNORECASE)


def approval_problems(meta):
    """Only documents an owner has approved may be indexed."""
    try:
        approved_on = date.fromisoformat(meta.get("approved_on", ""))
    except ValueError:
        return ["no valid approval (approved_by and approved_on are required)"]
    if not meta.get("approved_by") or approved_on > date.today():
        return ["no valid approval (approved_by and approved_on are required)"]
    return []


class UnsafeDocument(ValueError):
    pass


def tokens(items):
    for t in items:
        yield t
        yield from tokens(t.children or [])


def hidden_content(text, body):
    """Reasons the document may contain text a reader would not see, judged the way a CommonMark renderer reads it."""
    problems = set()
    # Format (zero-width, bidi, tag characters), control, private-use and unassigned characters are
    # invisible or ambiguous; only newline, tab and carriage return are allowed.
    if any(unicodedata.category(ch) in ("Cf", "Cc", "Co", "Cn") and ch not in "\n\t\r" for ch in text):
        problems.add("invisible or non-printable characters")
    env = {}
    for t in tokens(COMMONMARK.parse(body, env)):
        if t.type in ("html_block", "html_inline"):
            problems.add("raw HTML")
        elif t.type == "image":
            problems.add("image (alt text is not shown)")
        elif t.type == "link_open" and t.attrGet("title"):
            problems.add("link title (shown only on hover)")
    if env.get("references"):
        problems.add("link reference definition")
    return sorted(problems)


def read_doc(path):
    text = path.read_text(encoding="utf-8")
    _, header, body = text.split("---", 2)
    meta = {k.strip(): v.strip() for k, v in (line.split(":", 1) for line in header.strip().splitlines())}
    if hidden := HIDDEN.findall(body):
        log.warning("document=%s had %d hidden comment(s); removed before indexing, ask the owner to review",
                    path.stem, len(hidden))
    body = HIDDEN.sub("", body)
    problems = approval_problems(meta) + hidden_content(text, body)
    problems += [f"non-plain header value '{key}'" for key, value in meta.items() if not PLAIN_HEADER.fullmatch(value)]
    if AI_INSTRUCTION.search(body):
        problems.append("text that gives instructions to the AI assistant")
    if problems:
        raise UnsafeDocument(f"document={path.stem} contains {', '.join(problems)}")
    meta["allowed_roles"] = [role.strip() for role in meta["allowed_roles"].split(",")]
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
