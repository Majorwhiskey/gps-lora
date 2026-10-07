#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Render the project's Markdown documents to PDF.

    python3 docs/build_pdf.py            # all documents below
    python3 docs/build_pdf.py SECURITY   # one, by output name

Needs python3-markdown and Google Chrome or Chromium (headless printing).
Re-run after editing a document so the PDF does not go stale.
"""

import datetime
import html
import os
import re
import shutil
import subprocess
import sys
import tempfile

import markdown

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Output name -> source, relative to the repository root.
DOCUMENTS = {
    "SECURITY": "docs/SECURITY.md",
    "FIRMWARE": "firmware/README.md",
}

CSS = """
@page { size: A4; margin: 18mm 16mm 20mm 16mm;
        @bottom-right { content: counter(page) " / " counter(pages);
                        font: 8pt 'DejaVu Sans', sans-serif; color: #666; }
        @bottom-left { content: "@@TITLE@@";
                       font: 8pt 'DejaVu Sans', sans-serif; color: #666; } }
html { font: 9.5pt/1.45 'DejaVu Sans', 'Liberation Sans', sans-serif; color: #1a1a1a; }
body { margin: 0; }
h1 { font-size: 20pt; margin: 0 0 4pt;
     border-bottom: 2pt solid #1a1a1a; padding-bottom: 4pt; }
h2 { font-size: 13pt; margin: 16pt 0 6pt; border-bottom: 0.6pt solid #999;
     padding-bottom: 2pt; break-after: avoid; }
h3 { font-size: 11pt; margin: 12pt 0 4pt; break-after: avoid; }
p, ul, ol { margin: 4pt 0 6pt; }
li { margin: 1pt 0; }
a { color: #0b4f8a; text-decoration: none; }
code { font: 8.5pt 'DejaVu Sans Mono', 'Liberation Mono', monospace;
       background: #f2f2f2; padding: 0 2pt; border-radius: 2pt; word-break: break-all; }
pre { background: #f5f5f5; border: 0.5pt solid #ddd; border-radius: 3pt;
      padding: 6pt 8pt; white-space: pre-wrap; break-inside: avoid; }
pre code { background: none; padding: 0; font-size: 8pt; line-height: 1.3; }
table { border-collapse: collapse; width: 100%; margin: 6pt 0 8pt; font-size: 8.5pt;
        break-inside: auto; }
tr { break-inside: avoid; }
th, td { border: 0.5pt solid #bbb; padding: 3pt 5pt; text-align: left; vertical-align: top; }
th { background: #ececec; }
thead { display: table-header-group; }
blockquote { margin: 6pt 0; padding: 4pt 10pt; border-left: 3pt solid #c33; background: #fbf1f1; }
.source { font-size: 8pt; color: #666; margin: 0 0 12pt; }
"""


def find_chrome() -> str:
    for name in ("google-chrome", "chromium", "chromium-browser", "google-chrome-stable"):
        path = shutil.which(name)
        if path:
            return path
    sys.exit("Google Chrome or Chromium is needed to print PDFs")


def git_state(path: str) -> str:
    """Last commit touching the file, and whether it has uncommitted edits."""
    try:
        rev = subprocess.run(["git", "-C", ROOT, "log", "-1", "--format=%h", "--", path],
                             capture_output=True, text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "-C", ROOT, "status", "--porcelain", "--", path],
                               capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""
    if not rev:
        return "not yet committed"
    return f"commit {rev}" + (" + uncommitted changes" if dirty else "")


def render(name: str, source: str, chrome: str) -> str:
    with open(os.path.join(ROOT, source), encoding="utf-8") as f:
        text = f.read()
    body = markdown.markdown(text, extensions=["tables", "fenced_code", "toc", "sane_lists"])
    title = re.search(r"^# (.+)$", text, re.M)
    title = title.group(1) if title else name
    stamp = datetime.date.today().isoformat()
    state = git_state(source)
    origin = f"Source: {source}, {state}, generated {stamp}" if state else \
        f"Source: {source}, generated {stamp}"
    # The provenance line goes right under the title.
    body = re.sub(r"(</h1>)", rf'\1<p class="source">{html.escape(origin)}</p>', body, count=1)
    # Chrome supports @page margin boxes but not string-set, so the footer
    # title is written into the stylesheet as a CSS string.
    css = CSS.replace("@@TITLE@@", title.replace("\\", "").replace('"', "'"))
    page = (f"<!doctype html><html lang=en><head><meta charset=utf-8>"
            f"<title>{html.escape(title)}</title><style>{css}</style></head>"
            f"<body>{body}</body></html>")

    out = os.path.join(ROOT, "docs", f"{name}.pdf")
    with tempfile.TemporaryDirectory() as tmp:
        page_path = os.path.join(tmp, f"{name}.html")
        with open(page_path, "w", encoding="utf-8") as f:
            f.write(page)
        # Own throwaway profile: never touches the user's Chrome profile.
        subprocess.run([chrome, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                        f"--user-data-dir={os.path.join(tmp, 'profile')}",
                        f"--print-to-pdf={out}", "file://" + page_path],
                       check=True, capture_output=True, timeout=120)
    return out


def main() -> None:
    wanted = sys.argv[1:] or list(DOCUMENTS)
    unknown = [w for w in wanted if w not in DOCUMENTS]
    if unknown:
        sys.exit(f"unknown document(s) {unknown}; choose from {list(DOCUMENTS)}")
    chrome = find_chrome()
    for name in wanted:
        out = render(name, DOCUMENTS[name], chrome)
        print(f"{DOCUMENTS[name]} -> {os.path.relpath(out, ROOT)}")


if __name__ == "__main__":
    main()
