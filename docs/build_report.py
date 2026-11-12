"""Build docs/report.pdf from docs/report.md and docs/critical_thinking.md.

Run from anywhere with a Python that has markdown-it-py, for example:
    case3_knowledge_chatbot/.venv/Scripts/python docs/build_report.py
Needs Microsoft Edge or Google Chrome to print, and internet access for the Mermaid diagram library.
"""
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from markdown_it import MarkdownIt

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = "Akbar Jaya Pratama Putra"
DATE = "12 November 2026"
CONTENTS = ["Summary", "Case 1 - Fraud Risk Prediction", "Case 2 - Document Intelligence",
            "Case 3 - Enterprise Knowledge Chatbot", "Critical Thinking & Engineering Judgment", "AI tool use"]
BROWSERS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "msedge", "google-chrome", "chromium",
]
CSS = """
@page { size: A4; margin: 16mm 14mm; }
body { font-family: "Segoe UI", Arial, sans-serif; font-size: 9.5pt; line-height: 1.45; color: #1a1a1a; }
h1 { font-size: 18pt; color: #0b2545; border-bottom: 2px solid #0b2545; padding-bottom: 4px; }
h2 { font-size: 13pt; color: #0b2545; margin-top: 18px; }
h3 { font-size: 11pt; }
table { border-collapse: collapse; width: 100%; margin: 8px 0; font-size: 8.5pt; page-break-inside: auto; }
th, td { border: 1px solid #c8ced6; padding: 3px 6px; vertical-align: top; word-break: break-word; }
th { background: #eef2f7; text-align: left; }
tr { page-break-inside: avoid; }
code { font-family: Consolas, monospace; font-size: 8.5pt; background: #f3f4f6; padding: 0 2px; }
pre { background: #f3f4f6; padding: 6px 8px; white-space: pre-wrap; word-break: break-word; font-size: 8pt; }
pre.mermaid { background: none; text-align: center; page-break-inside: avoid; }
a { color: inherit; text-decoration: none; }
h1 { page-break-before: always; }
.cover { text-align: center; padding-top: 70mm; }
.cover h1 { border: none; font-size: 26pt; page-break-before: avoid; }
.cover .name { font-size: 15pt; margin-top: 30px; }
.cover ol { text-align: left; display: inline-block; margin-top: 30px; font-size: 11pt; }
"""


def to_html(markdown):
    body = MarkdownIt("default", {"html": True}).render(markdown)  # our own READMEs use <br> inside table cells
    # Let Mermaid draw the architecture diagrams instead of showing their source.
    return re.sub(r'<pre><code class="language-mermaid">(.*?)</code></pre>', r'<pre class="mermaid">\1</pre>',
                  body, flags=re.DOTALL)


def build_html():
    contents = "".join(f"<li>{title}</li>" for title in CONTENTS)
    report = (ROOT / "docs" / "report.md").read_text(encoding="utf-8")
    cases, ai_use = report.split("\n# AI tool use", 1)  # the AI disclosure closes the report
    thinking = (ROOT / "docs" / "critical_thinking.md").read_text(encoding="utf-8")
    pages = to_html(cases) + to_html(thinking) + to_html("# AI tool use" + ai_use)
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>AI Solution Engineer Assessment</title>
<style>{CSS}</style>
<script src="https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.min.js"
 integrity="sha384-rbtjAdnIQE/aQJGEgXrVUlMibdfTSa4PQju4HDhN3sR2PmaKFzhEafuePsl9H/9I" crossorigin="anonymous"></script>
<script>mermaid.initialize({{startOnLoad: true, theme: "neutral"}});</script></head><body>
<section class="cover"><h1>AI Solution Engineer<br>Technical Assessment</h1>
<p class="name">{CANDIDATE}</p><p>V-TEKI &middot; {DATE}</p><ol>{contents}</ol></section>
{pages}</body></html>"""


def main():
    browser = next((b for b in BROWSERS if Path(b).exists() or shutil.which(b)), None)
    if browser is None:
        raise SystemExit("Install Microsoft Edge or Google Chrome to print the PDF.")
    out = ROOT / "docs" / "report.pdf"
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "report.html"
        page.write_text(build_html(), encoding="utf-8")
        subprocess.run([browser, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                        f"--user-data-dir={Path(tmp) / 'profile'}", "--virtual-time-budget=20000",
                        f"--print-to-pdf={out}", page.as_uri()], check=True, timeout=180, capture_output=True)
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
