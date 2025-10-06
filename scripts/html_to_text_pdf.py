# pip install weasyprint==62.3  # or latest
# Linux needs: libpango, libharfbuzz, libffi, cairo (WeasyPrint docs list packages)
# Do this at the VERY TOP of your app, before importing libraries that use GLib/Pango/Cairo
import os
import sys, os
if sys.platform == "win32":
    os.add_dll_directory(r"C:\msys64\ucrt64\bin")
os.environ["PATH"] = r"C:\msys64\ucrt64\bin" + os.pathsep + os.environ.get("PATH","")
from weasyprint import HTML, CSS

# Check if the variable exists and print it
if "PATH" in os.environ:
    print("PATH exists:", os.environ["PATH"])
else:
    print("PATH does not exist.")
from weasyprint import HTML, CSS
from pathlib import Path
import re

html_path = Path("ocr_html_uniform/layout_uniform.html")
pdf_path  = Path("ocr_html_uniform/layout_uniform.pdf")

html = html_path.read_text(encoding="utf-8")

# --- Ensure print CSS is page-accurate ---
# Your HTML has <div class="page" style="width:{W}px;height:{H}px"> per page.
# We’ll generate @page rules per page so print size matches pixel size exactly.
px_to_in = 1/96  # Browsers treat 1in = 96px

page_divs = re.findall(r'<div class="page"[^>]*style="[^"]*width:([0-9.]+)px;[^"]*height:([0-9.]+)px;?', html)
page_css = []
for i, (w_px, h_px) in enumerate(page_divs, start=1):
    w_in = float(w_px)*px_to_in
    h_in = float(h_px)*px_to_in
    page_css.append(f"@page page{i} {{ size: {w_in:.4f}in {h_in:.4f}in; margin: 0; }}")

# Tag each page with a unique page name:
def tag_pages(m, counter=[0]):
    counter[0] += 1
    i = counter[0]
    # add page-break and link this element to @page page{i}
    styled = m.group(0).replace('class="page"', f'class="page" style="page: page{i}; page-break-after: always;"', 1)
    return styled

html_tagged = re.sub(r'<div class="page"([^>]*)>', tag_pages, html, flags=re.IGNORECASE)

# Base print CSS: remove margins, avoid shadows in print, keep absolute positions
base_css = """
@media print {
  html, body { background:#fff !important; margin:0 !important; padding:0 !important; }
  .page { margin: 0 !important; box-shadow: none !important; }
}
/* Ensure spans render as live text, not images */
.page span { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
"""

css = CSS(string=base_css + "\n" + "\n".join(page_css))
HTML(string=html_tagged, base_url=str(html_path.parent.resolve())).write_pdf(str(pdf_path), stylesheets=[css])

print("Wrote:", pdf_path.resolve())
