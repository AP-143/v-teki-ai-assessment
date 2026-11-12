"""Split the approved documents into sections, embed them locally, and write the search index.

Each document starts with a header block naming the roles allowed to read it. A document is
indexed only if:
- its exact content was approved in the approvals registry (data/approvals.json), and
- it hides nothing from a human reader and gives no instructions to the AI assistant.
Otherwise it is quarantined (not indexed). Only the text a reader actually sees is indexed.
"""
import argparse
import hashlib
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
APPROVALS = CASE_DIR / "data" / "approvals.json"
# Closed HTML comments are removed with a warning (the demo document has one); anything else hidden quarantines.
HIDDEN = re.compile(r"<!--.*?-->", re.DOTALL)
COMMONMARK = MarkdownIt("commonmark")
# Header values flow into chunk text, so they must be plain text.
PLAIN_HEADER = re.compile(r"[\w .,&()'/-]+")
# Visible text that talks to the AI instead of to employees (English and Indonesian).
# shortcut: a phrase list is easy to paraphrase around; content-hash approval is the main control.
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


class UnsafeDocument(ValueError):
    pass


def sha256(path):
    # read_text normalizes line endings, so a git checkout with CRLF endings keeps the same hash.
    return hashlib.sha256(path.read_text(encoding="utf-8").encode("utf-8")).hexdigest()


def load_approvals(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def approve(doc_path, approver, approvals_path=APPROVALS):
    """Record that `approver` approved this exact file content. Any later edit voids the approval."""
    approvals = load_approvals(approvals_path)
    approvals[doc_path.name] = {"approved_by": approver, "approved_on": date.today().isoformat(),
                                "sha256": sha256(doc_path)}
    approvals_path.write_text(json.dumps(approvals, indent=2) + "\n", encoding="utf-8")


def approval_problem(path, approvals):
    entry = approvals.get(path.name)
    if not entry:
        return "no approval"
    if entry.get("sha256") != sha256(path):
        return "content changed after approval"
    try:
        valid_date = date.fromisoformat(entry.get("approved_on", "")) <= date.today()
    except ValueError:
        valid_date = False
    if not entry.get("approved_by") or not valid_date:
        return "an incomplete approval record"
    return None


def tokens(items):
    for t in items:
        yield t
        yield from tokens(t.children or [])


def render(body):
    """What a reader sees: headings and text, with character references and escapes decoded.
    Link targets, code-block info strings and any markup never reach the index."""
    env, lines, heading = {}, [], ""
    parsed = COMMONMARK.parse(body, env)
    for t in parsed:
        if t.type == "heading_open":
            heading = "#" * int(t.tag[1:]) + " "
        elif t.type == "inline":
            lines.append(heading + "".join(c.content if c.type in ("text", "code_inline")
                                           else " " if c.type in ("softbreak", "hardbreak") else ""
                                           for c in t.children))
            heading = ""
        elif t.type in ("fence", "code_block"):
            lines.append(t.content.rstrip("\n"))
    return "\n".join(lines), parsed, env


def invisible_characters(text):
    # Format (zero-width, bidi, tag characters), control, private-use and unassigned characters are
    # invisible or ambiguous; only newline, tab and carriage return are allowed.
    return any(unicodedata.category(ch) in ("Cf", "Cc", "Co", "Cn") and ch not in "\n\t\r" for ch in text)


def read_doc(path):
    """Return (header, visible text) or raise UnsafeDocument."""
    raw = path.read_text(encoding="utf-8")
    _, header, body = raw.split("---", 2)
    meta = {k.strip(): v.strip() for k, v in (line.split(":", 1) for line in header.strip().splitlines())}
    if hidden := HIDDEN.findall(body):
        log.warning("document=%s had %d hidden comment(s); removed before indexing, ask the owner to review",
                    path.stem, len(hidden))
    visible, parsed, env = render(HIDDEN.sub("", body))

    problems = set()
    if invisible_characters(raw) or invisible_characters(visible):  # the second catches &#8203; and similar
        problems.add("invisible or non-printable characters")
    for t in tokens(parsed):
        if t.type in ("html_block", "html_inline"):
            problems.add("raw HTML")
        elif t.type == "image":
            problems.add("image (alt text is not shown)")
        elif t.type == "link_open" and t.attrGet("title"):
            problems.add("link title (shown only on hover)")
    if env.get("references"):
        problems.add("link reference definition")
    problems |= {f"non-plain header value '{key}'" for key, value in meta.items() if not PLAIN_HEADER.fullmatch(value)}
    if AI_INSTRUCTION.search(visible + "\n" + "\n".join(meta.values())):
        problems.add("text that gives instructions to the AI assistant")
    if problems:
        raise UnsafeDocument(f"document={path.stem} contains {', '.join(sorted(problems))}")
    meta["allowed_roles"] = [role.strip() for role in meta["allowed_roles"].split(",")]
    return meta, visible


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


def build_index(docs_dir, index_dir, approvals_path=APPROVALS):
    approvals = load_approvals(approvals_path)
    chunks = []
    for path in sorted(Path(docs_dir).glob("*.md")):
        try:
            if problem := approval_problem(path, approvals):
                raise UnsafeDocument(f"document={path.stem} has {problem}")
            chunks += split_sections(*read_doc(path))
        except UnsafeDocument as err:
            log.error("%s; quarantined, not indexed. Ask the owner to review it.", err)
    vectors = ollama.embed([c["text"] for c in chunks])
    index_dir.mkdir(parents=True, exist_ok=True)
    (index_dir / "chunks.json").write_text(json.dumps(chunks, indent=2), encoding="utf-8")
    np.save(index_dir / "vectors.npy", vectors)
    return chunks


def main(argv=None):
    parser = argparse.ArgumentParser(description="Build the search index from data/docs, or approve a document.")
    parser.add_argument("--docs-dir", type=Path, default=CASE_DIR / "data" / "docs")
    parser.add_argument("--index-dir", type=Path, default=CASE_DIR / "index")
    parser.add_argument("--approvals", type=Path, default=APPROVALS)
    parser.add_argument("--approve", type=Path, metavar="DOC", help="record approval of this document's current content")
    parser.add_argument("--by", help="approver name, required with --approve")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if args.approve:
        if not args.by:
            parser.error("--approve needs --by")
        approve(args.approve, args.by, args.approvals)
        print(f"Approved {args.approve.name} by {args.by}")
        return
    chunks = build_index(args.docs_dir, args.index_dir, args.approvals)
    print(f"Indexed {len(chunks)} sections from {len({c['doc_id'] for c in chunks})} documents into {args.index_dir}")


if __name__ == "__main__":
    main()
