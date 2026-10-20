"""Build the PDF next to each Markdown document: python docs/build_pdf.py docs/*.md

Needs `pip install -r docs/requirements.txt` and Google Chrome/Chromium (CHROME_BIN to override the path).
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import markdown

REPO_URL = "https://github.com/amineyoussefi-cpu/Bzz/tree/main/"
CSS = """
@page { size: A4; margin: 16mm 15mm; }
body { font-family: -apple-system, "Helvetica Neue", Arial, sans-serif; font-size: 10.5pt; line-height: 1.45; color: #222; }
h1 { font-size: 22pt; border-bottom: 3px solid #d89a2b; padding-bottom: 4px; }
h2 { font-size: 16pt; color: #5a3d12; border-bottom: 1px solid #ddd; padding-bottom: 2px; break-before: page; }
h2:first-of-type { break-before: auto; }
h3, h2 { break-after: avoid; }
h3 { font-size: 12.5pt; color: #5a3d12; clear: both; margin-top: 18px; }
table { border-collapse: collapse; width: 100%; margin: 8px 0; font-size: 9.5pt; }
tr, img { break-inside: avoid; }
table + h3 { break-before: page; }
th, td { border: 1px solid #ccc; padding: 4px 6px; vertical-align: middle; }
th { background: #f6f1e4; }
img[align=right] { float: right; margin: 0 0 8px 12px; }
img { max-width: 100%; }
pre { background: #f6f6f6; padding: 8px; border-radius: 4px; white-space: pre; overflow: hidden; break-inside: avoid; }
code { font-size: 9pt; }
pre code { font-size: 7.6pt; }
a { color: #8a5a12; }
hr { display: none; }
"""


def chrome() -> str:
    for c in [os.environ.get("CHROME_BIN"), "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
              shutil.which("google-chrome"), shutil.which("chromium"), shutil.which("chromium-browser")]:
        if c and Path(c).exists():
            return c
    sys.exit("Chrome/Chromium not found; set CHROME_BIN")


def build(md: Path, browser: str) -> Path:
    text = md.read_text()
    text = re.sub(r"\]\(\.\./([^)]+)\)", rf"]({REPO_URL}\1)", text)  # repo-relative links -> GitHub
    body = markdown.markdown(text, extensions=["tables", "fenced_code", "md_in_html"])
    title = re.search(r"^# (.+)$", text, re.M)
    html = (f'<!doctype html><html lang="fr"><head><meta charset="utf-8"><base href="{md.parent.resolve().as_uri()}/">'
            f'<title>{title.group(1) if title else md.stem}</title><style>{CSS}</style></head><body>{body}</body></html>')
    pdf = md.with_suffix(".pdf").resolve()
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as f:
        f.write(html)
    try:
        subprocess.run([browser, "--headless", "--disable-gpu", "--allow-file-access-from-files", "--no-pdf-header-footer",
                        f"--print-to-pdf={pdf}", Path(f.name).as_uri()], check=True, capture_output=True, timeout=120)
    finally:
        os.unlink(f.name)
    return pdf


if __name__ == "__main__":
    browser = chrome()
    for arg in sys.argv[1:]:
        print(build(Path(arg), browser))
