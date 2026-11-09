"""Generate publication-quality REPORT.pdf from REPORT.md and verify exact page count <= 2."""

from __future__ import annotations

import subprocess
from pathlib import Path
import mistune
from pypdf import PdfReader


def render_report_pdf(md_path: Path = Path("REPORT.md"), pdf_path: Path = Path("REPORT.pdf")) -> int:
    md_content = md_path.read_text(encoding="utf-8")

    # Render Markdown to HTML using mistune
    html_body = mistune.html(md_content)

    html_doc = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
@page {{
    size: A4 portrait;
    margin: 0.5cm 0.7cm;
}}
body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    font-size: 7.2pt;
    line-height: 1.14;
    color: #111;
    margin: 0;
    padding: 0;
}}
h1 {{
    font-size: 8.6pt;
    font-weight: 700;
    margin: 4px 0 1px 0;
    padding-bottom: 1px;
    border-bottom: 1px solid #1a365d;
    color: #0b1f3a;
    break-after: avoid;
}}
h2 {{
    font-size: 8.0pt;
    font-weight: 600;
    margin: 3px 0 1px 0;
    color: #0b1f3a;
    break-after: avoid;
}}
h3 {{
    font-size: 7.6pt;
    font-weight: 600;
    margin: 2px 0 1px 0;
    color: #222;
    break-after: avoid;
}}
p {{
    margin: 1.5px 0;
    text-align: justify;
}}
ul, ol {{
    margin: 1.5px 0;
    padding-left: 12px;
}}
li {{
    margin: 0.5px 0;
}}
blockquote {{
    margin: 1.5px 0;
    padding: 1px 6px;
    background-color: #f7fafc;
    border-left: 2.5px solid #2b6cb0;
    font-size: 6.8pt;
    color: #2d3748;
}}
table {{
    width: 100%;
    border-collapse: collapse;
    margin: 2px 0;
    font-size: 6.4pt;
    break-inside: avoid;
}}
th, td {{
    border: 0.5px solid #cbd5e0;
    padding: 1.2px 3px;
    text-align: left;
    vertical-align: top;
}}
th {{
    background-color: #edf2f7;
    font-weight: 600;
    color: #1a202c;
}}
code {{
    font-family: "JetBrains Mono", Consolas, monospace;
    font-size: 6.6pt;
    background-color: #edf2f7;
    padding: 0.5px 2px;
    border-radius: 2px;
}}
pre {{
    font-family: "JetBrains Mono", Consolas, monospace;
    font-size: 6.4pt;
    background-color: #f7fafc;
    border: 0.5px solid #e2e8f0;
    padding: 2px 4px;
    margin: 1.5px 0;
    border-radius: 2px;
    break-inside: avoid;
}}
hr {{
    border: 0;
    border-top: 0.5px solid #e2e8f0;
    margin: 2px 0;
}}
</style>
</head>
<body>
{html_body}
</body>
</html>
"""
    temp_html = Path("results/temp_report.html")
    temp_html.parent.mkdir(parents=True, exist_ok=True)
    temp_html.write_text(html_doc, encoding="utf-8")

    edge_bin = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
    cmd = [
        edge_bin,
        "--headless",
        "--disable-gpu",
        f"--print-to-pdf={pdf_path.resolve()}",
        f"file:///{temp_html.resolve().as_posix()}",
    ]
    subprocess.run(cmd, check=True)

    # Check page count
    reader = PdfReader(pdf_path)
    page_count = len(reader.pages)
    print(f"Generated {pdf_path}: {page_count} pages.")
    return page_count


if __name__ == "__main__":
    count = render_report_pdf()
    if count > 2:
        print(f"WARNING: Page count is {count} (exceeds 2-page limit). Needs compression.")
    else:
        print(f"SUCCESS: Page count is {count} <= 2. Perfect submission length!")
