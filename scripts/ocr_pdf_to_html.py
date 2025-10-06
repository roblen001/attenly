# Assumes you already ran Doctr and have:
#   docs   = DocumentFile.from_pdf("dictionary.pdf", scale=4.17)
#   result = model(docs)
#   export = result.export()

from pathlib import Path

OUT_DIR = Path("ocr_html_overlay_noimg")
OUT_DIR.mkdir(exist_ok=True)

TEXT_VISIBLE = True          # True: show text; False: hidden/selectable text layer
UNIFORM_FONT_SIZE = 14       # single font size everywhere

def esc(s: str) -> str:
    return (s.replace("&","&amp;").replace("<","&lt;")
             .replace(">","&gt;").replace('"',"&quot;"))

pages_html = []
maxW = 0

for p_idx, p in enumerate(export["pages"]):
    # Page pixel size (exactly what Doctr used)
    W, H = p["dimensions"]
    maxW = max(maxW, W)

    # Word-level, absolute-positioned spans (no rounding!)
    spans = []
    for block in p.get("blocks", []):
        for line in block.get("lines", []):
            for word in line.get("words", []):
                (x0, y0), (x1, y1) = word["geometry"]  # normalized [0,1]
                left   = x0 * W
                top    = y0 * H
                width  = max(1.0, (x1 - x0) * W)
                height = max(1.0, (y1 - y0) * H)
                text   = esc(word["value"])

                if TEXT_VISIBLE:
                    # Keep text inside its box; uniform font size across page(s)
                    spans.append(
                        f'<span class="w v" style="left:{left}px;top:{top}px;'
                        f'width:{width}px;height:{height}px;'
                        f'font-size:{UNIFORM_FONT_SIZE}px;line-height:{height}px;">{text}</span>'
                    )
                else:
                    # Hidden but selectable “searchable” layer
                    spans.append(
                        f'<span class="w inv" style="left:{left}px;top:{top}px;'
                        f'width:{width}px;height:{height}px;">{text}</span>'
                    )

    page_html = f'''
<div class="page" style="width:{W}px;height:{H}px;">
  {''.join(spans)}
</div>'''
    pages_html.append(page_html)

html = f"""<!doctype html>
<html>
<head>
<meta charset="utf-8" />
<title>OCR Overlay (no background image)</title>
<style>
  html,body {{ background:#f4f6f8; margin:0; padding:0; }}
  .sheet {{ width:100%; max-width:{maxW}px; margin:0 auto; }}
  .page {{
    position: relative;
    background:#fff;         /* white page instead of the scan */
    box-shadow: 0 0 1px rgba(0,0,0,.2);
    margin: 24px auto;
    overflow: hidden;
  }}
  .w {{
    position:absolute;
    white-space:nowrap;      /* keep a single word on one line */
    overflow:hidden;
    transform: translateZ(0);/* reduce subpixel layout jitter */
    /* tip: avoid web fonts; system fonts reduce kerning surprises */
  }}
  .w.inv {{
    color: transparent;
    text-shadow: none;
    -webkit-text-stroke: 0;
  }}
  .w.v {{ color:#111; }}
  @media print {{
    body {{ background:#fff; }}
    .page {{ margin:0; box-shadow:none; }}
    @page {{ margin: 0; }}
  }}
</style>
</head>
<body>
<div class="sheet">
{''.join(pages_html)}
</div>
</body>
</html>"""

out_file = OUT_DIR / "overlay_no_image.html"
out_file.write_text(html, encoding="utf-8")
print("Wrote:", out_file.resolve())
