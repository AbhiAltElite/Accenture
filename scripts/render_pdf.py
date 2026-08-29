"""Render a Markdown document to the PDF the submission portal accepts.

The README is written once, in Markdown, and lives in the repository where it is
read and reviewed. The portal wants a PDF. Rendering one from the other keeps a
single source: a separately maintained PDF drifts from the repository within a
day, and the drift is invisible until someone reads both.

Deliberately plain. LibreOffice does the conversion, and its CSS support is
partial, so the stylesheet below sticks to what it renders reliably: type
sizes, weights, table borders, and page margins. Anything more ambitious
renders differently in the PDF than in the browser, which is worse than plain.

    make readme-pdf
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import markdown

# Only what LibreOffice's HTML importer actually honours. Flexbox, custom
# properties and web fonts are silently dropped, so they are not used.
STYLE = """
@page { size: A4; margin: 18mm 16mm; }
/* The background is set explicitly. A document that declares an ink colour and
   inherits its paper renders as dark-on-dark for anyone whose viewer defaults
   to a dark theme, which is most of them. */
html, body { background: #ffffff; }
body { font-family: Calibri, Arial, sans-serif; font-size: 10.5pt;
       line-height: 1.45; color: #1a1a1a; }
h1 { font-size: 24pt; margin: 0 0 4pt 0; color: #111; }
h2 { font-size: 15pt; margin: 20pt 0 6pt 0; color: #111;
     border-bottom: 1px solid #bbb; padding-bottom: 3pt; }
h3 { font-size: 12pt; margin: 14pt 0 4pt 0; }
p, li { font-size: 10.5pt; }
table { border-collapse: collapse; width: 100%; margin: 8pt 0; font-size: 9.5pt; }
th { text-align: left; border-bottom: 1.2pt solid #444; padding: 4pt 6pt 4pt 0;
     font-weight: bold; }
td { border-bottom: 0.5pt solid #ccc; padding: 4pt 6pt 4pt 0; vertical-align: top; }
code { font-family: Consolas, "Courier New", monospace; font-size: 9pt;
       background: #f2f2f2; }
pre { font-family: Consolas, "Courier New", monospace; font-size: 8.5pt;
      background: #f6f6f6; padding: 8pt; line-height: 1.3; }
blockquote { margin: 8pt 0 8pt 12pt; color: #444; font-style: italic; }
hr { border: none; border-top: 0.5pt solid #ccc; margin: 14pt 0; }
"""

# `tables` and `fenced_code` are the two the document actually relies on;
# `toc` resolves the anchors the table of contents links to.
EXTENSIONS = ["tables", "fenced_code", "toc", "sane_lists"]

# LibreOffice, wrapped because a bare `soffice` can pick up a running instance
# and return without converting anything.
SOFFICE = shutil.which("soffice") or "/Applications/LibreOffice.app/Contents/MacOS/soffice"


def render(source: Path, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    html_path = out_dir / f"{source.stem}.html"

    body = markdown.markdown(source.read_text(encoding="utf-8"), extensions=EXTENSIONS)
    html_path.write_text(
        f"<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{source.stem}</title><style>{STYLE}</style></head>"
        f"<body>{body}</body></html>",
        encoding="utf-8",
    )

    if not Path(SOFFICE).exists() and shutil.which("soffice") is None:
        raise SystemExit(
            "LibreOffice not found. Install it, or convert "
            f"{html_path} to PDF by any other means."
        )

    subprocess.run(
        [SOFFICE, "--headless", "--convert-to", "pdf", "--outdir",
         str(out_dir), str(html_path)],
        check=True, capture_output=True, timeout=180,
    )
    pdf = out_dir / f"{source.stem}.pdf"
    if not pdf.exists():
        raise SystemExit(f"conversion produced no {pdf}")
    return pdf


def main() -> int:
    source = Path(sys.argv[1] if len(sys.argv) > 1 else "README.md")
    out_dir = Path(sys.argv[2] if len(sys.argv) > 2 else "dist")
    if not source.exists():
        print(f"no such file: {source}")
        return 2

    pdf = render(source, out_dir)
    size_mb = pdf.stat().st_size / 1_000_000
    print(f"{pdf}  {size_mb:.2f} MB")
    # The portal rejects anything larger, and finding that out at upload time
    # is the wrong moment.
    if size_mb > 20:
        print("OVER THE 20 MB PORTAL LIMIT")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
