"""
pdf_to_markdown_tables.py

Minimal, standalone PDF -> Markdown converter focused on tables.
- Keeps the exact table formatting logic (vertical '|' insertion + dashed rows).
- Prints Markdown to stdout (no files written).
- No confidence, elements, or extra heuristics.

Usage:
    python pdf_to_markdown_tables.py /path/to/file.pdf
"""

import argparse
import logging
import os
import re
import statistics
from typing import List, Tuple, Dict, Any, Iterable

import fitz  # PyMuPDF

# ------------------------------- Config ------------------------------------

# Layout & detection
Y_TOL = 1.0
SUPERSCRIPT_Y_TOL = 1.0
MIN_SPACE_COLS = 1

# Vertical-rule detection
VERT_TOL = 1.0
VERT_MIN_LEN = 6.0
Y_JOIN_TOL = 2.0
MIN_V_OVERLAP_FRAC = 0.45
CHAR_COL_TOL = 2
ONLY_INSIDE_TEXT = False
SHIFT_IF_OCCUPIED = True

# Horizontal-rule detection
H_TOL = 1.0
H_MIN_LEN = 3.0
X_JOIN_TOL = 3.0
LINE_ATTACH_TOL = 6
H_Y_MERGE_TOL = 1
H_MIN_ABS_CHARS = 8
DRAW_CHAR = "-"

# Clean-up
H_SEG_ALREADY_RATIO = 0.30
HLINE_ROW_DASH_RATIO = 0.65
PRUNE_NEAR_Y_TOL = 0.4
PRUNE_X_OVERLAP_RATIO = 0.9

# Misc
ALLOW_CHARS_PATTERN = r"[A-Za-z0-9]"
COLLAPSE_EOL_RUNS = False

logger = logging.getLogger("pdf_to_markdown_tables")


# ------------------------------- Helpers -----------------------------------

VerticalRule = Tuple[float, float, float]    # (x_mid, y0, y1)
HorizontalRule = Tuple[float, float, float]  # (y_mid, x0, x1)


def _is_likely_superscript(text: str) -> bool:
    text = text.strip()
    if len(text) > 6:
        return False
    for pattern in (r'^\d+(st|nd|rd|th)$', r'^\d+/\d+(st|nd|rd|th)$', r'^\d+$'):
        if re.match(pattern, text, re.IGNORECASE):
            return True
    return False


def _should_use_superscript_tolerance(word_text: str, prev_word_text: str = "") -> bool:
    return _is_likely_superscript(word_text)


def _cluster_cols(cols: List[int], tol: int) -> List[int]:
    cols = sorted(cols)
    if not cols:
        return []
    groups = [[cols[0]]]
    for c in cols[1:]:
        if c - groups[-1][-1] <= tol:
            groups[-1].append(c)
        else:
            groups.append([c])
    return [int(round(statistics.median(g))) for g in groups]


def _has_bar_near(buf: List[str], col: int, radius: int = 1) -> bool:
    for k in range(col - radius, col + radius + 1):
        if 0 <= k < len(buf) and buf[k] == "|":
            return True
    return False


def _nearest_space_slot(buf: List[str], col: int) -> int:
    n = len(buf)
    if col < n and buf[col] == " ":
        return col
    left = col
    while left > 0 and buf[left - 1] != " ":
        left -= 1
    right = col
    while right < n and (right < len(buf) and buf[right] != " "):
        right += 1
    return left if col - left <= right - col else right


def _insert_bar(buf: List[str], col: int) -> None:
    if col >= len(buf):
        buf.extend(" " * (col - len(buf) + 1))
    if buf[col] == "|":
        return
    if buf[col] == " ":
        buf[col] = "|"
        return
    if not SHIFT_IF_OCCUPIED:
        buf[col] = "|"
        return
    safe_col = _nearest_space_slot(buf, col)
    if safe_col >= len(buf):
        buf.extend(" " * (safe_col - len(buf) + 1))
    if buf[safe_col] == " ":
        buf[safe_col] = "|"
    else:
        buf[safe_col:safe_col] = ["|"]


def _segment_is_blank(buf: List[str], start: int, end: int) -> bool:
    seg = "".join(buf[start: end + 1])
    return not seg or not re.search(ALLOW_CHARS_PATTERN, seg)


def _segment_has_enough_dash(buf: List[str], start: int, end: int) -> bool:
    seg = buf[start: end + 1]
    return bool(seg) and seg.count(DRAW_CHAR) / len(seg) >= H_SEG_ALREADY_RATIO


def _draw_hline(buf: List[str], start_col: int, end_col: int) -> None:
    if end_col >= len(buf):
        buf.extend(" " * (end_col - len(buf) + 1))
    for c in range(max(0, start_col), end_col + 1):
        if buf[c] == " ":
            buf[c] = DRAW_CHAR


def _is_full_hline_row(s: str) -> bool:
    stripped = s.strip()
    return bool(stripped) and stripped.count(DRAW_CHAR) / max(1, len(stripped)) >= HLINE_ROW_DASH_RATIO


def _squash_dupe_h(lines: List[str]) -> List[str]:
    cleaned = []
    prev_dash = False
    for ln in lines:
        curr_dash = _is_full_hline_row(ln)
        if curr_dash and prev_dash:
            continue
        cleaned.append(ln)
        prev_dash = curr_dash
    return cleaned


def _blank_runs(buf: List[str], start: int, end: int) -> Iterable[Tuple[int, int]]:
    seg = "".join(buf[start: end + 1])
    for m in re.finditer(r" +", seg):
        yield start + m.start(), start + m.end() - 1


def _validate_segment_safety(lines_out: List[dict], target_idx: int, start_col: int, end_col: int) -> bool:
    if target_idx < 0 or target_idx >= len(lines_out):
        return False
    target_buf = lines_out[target_idx]["buf"]
    if end_col >= len(target_buf):
        target_buf.extend(" " * (end_col - len(target_buf) + 1))
    if not _segment_is_blank(target_buf, start_col, end_col):
        return False
    for check_idx in [target_idx - 1, target_idx + 1]:
        if 0 <= check_idx < len(lines_out):
            check_buf = lines_out[check_idx]["buf"]
            if end_col >= len(check_buf):
                check_buf.extend(" " * (end_col - len(check_buf) + 1))
            if not _segment_is_blank(check_buf, start_col, end_col):
                return False
    return True


def _insert_empty_line(lines_out: list, y_mid: float, where: int) -> int:
    max_len = max((len(l["buf"]) for l in lines_out), default=0)
    new_line = {"y0": y_mid - 0.1, "y1": y_mid + 0.1, "buf": [" "] * max_len}
    lines_out.insert(where, new_line)
    return where


# ---------------------------- Page processing --------------------------------

def _group_words_into_rows(words: list) -> List[List[Tuple[float, float, str, float, float]]]:
    lines_raw: List[List[Tuple[float, float, str, float, float]]] = []
    cur: List[Tuple[float, float, str, float, float]] = []
    last_y = None
    prev_text = ""

    for x0, y0, x1, y1, text, *_ in words:
        y_tolerance = Y_TOL
        if _should_use_superscript_tolerance(text.strip(), prev_text):
            y_tolerance = SUPERSCRIPT_Y_TOL

        if last_y is None or abs(y0 - last_y) <= y_tolerance:
            cur.append((x0, x1, text, y0, y1))
            last_y = y0 if last_y is None else (last_y + y0) / 2.0
        else:
            lines_raw.append(cur)
            cur = [(x0, x1, text, y0, y1)]
            last_y = y0
        prev_text = text.strip()

    if cur:
        lines_raw.append(cur)
    return lines_raw


def _collect_vertical_rules(page: fitz.Page) -> List[VerticalRule]:
    raw: List[VerticalRule] = []
    for d in page.get_drawings():
        for item in d["items"]:
            cmd = item[0]
            if cmd == "l":
                _, p1, p2, *_ = item
                x0, y0 = p1
                x1, y1 = p2
                if abs(x0 - x1) <= VERT_TOL and abs(y1 - y0) >= VERT_MIN_LEN:
                    raw.append(((x0 + x1) / 2.0, min(y0, y1), max(y0, y1)))
            elif cmd == "re":
                _, (x0, y0, x1, y1), *_ = item
                if abs(y1 - y0) >= VERT_MIN_LEN:
                    raw.append((x0, min(y0, y1), max(y0, y1)))
                    raw.append((x1, min(y0, y1), max(y0, y1)))
            elif cmd == "qu":
                _, quad, *_ = item
                pts = list(zip(quad[0::2], quad[1::2]))
                for (xa, ya), (xb, yb) in zip(pts, pts[1:] + pts[:1]):
                    if abs(xa - xb) <= VERT_TOL and abs(yb - ya) >= VERT_MIN_LEN:
                        raw.append(((xa + xb) / 2.0, min(ya, yb), max(ya, yb)))

    raw.sort(key=lambda s: (round(s[0], 2), s[1]))
    out: List[VerticalRule] = []
    i = 0
    while i < len(raw):
        x = round(raw[i][0], 2)
        group: List[VerticalRule] = []
        while i < len(raw) and round(raw[i][0], 2) == x:
            group.append(raw[i])
            i += 1
        group.sort(key=lambda s: s[1])

        cur_y0, cur_y1 = group[0][1], group[0][2]
        for _, y0, y1 in group[1:]:
            if y0 - cur_y1 <= Y_JOIN_TOL:
                cur_y1 = max(cur_y1, y1)
            else:
                out.append((x, cur_y0, cur_y1))
                cur_y0, cur_y1 = y0, y1
        out.append((x, cur_y0, cur_y1))
    return out


def _collect_horizontal_rules(page: fitz.Page) -> List[HorizontalRule]:
    raw: List[HorizontalRule] = []
    for d in page.get_drawings():
        for item in d["items"]:
            cmd = item[0]
            if cmd == "l":
                _, p1, p2, *_ = item
                x0, y0 = p1
                x1, y1 = p2
                if abs(y0 - y1) <= H_TOL and abs(x1 - x0) >= H_MIN_LEN:
                    raw.append(((y0 + y1) / 2.0, min(x0, x1), max(x0, x1)))
            elif cmd == "re":
                _, (x0, y0, x1, y1), *_ = item
                if abs(x1 - x0) >= H_MIN_LEN:
                    raw.append((y0, min(x0, x1), max(x0, x1)))
                    raw.append((y1, min(x0, x1), max(x0, x1)))
            elif cmd == "qu":
                _, quad, *_ = item
                pts = list(zip(quad[0::2], quad[1::2]))
                for (xa, ya), (xb, yb) in zip(pts, pts[1:] + pts[:1]):
                    if abs(ya - yb) <= H_TOL and abs(xb - xa) >= H_MIN_LEN:
                        raw.append(((ya + yb) / 2.0, min(xa, xb), max(xa, xb)))
    return raw


def _merge_h_rules(h_rules: List[HorizontalRule]) -> List[HorizontalRule]:
    if not h_rules:
        return []
    h_rules.sort(key=lambda r: (round(r[0], 2), r[1]))
    out: List[HorizontalRule] = []
    i = 0
    while i < len(h_rules):
        y = h_rules[i][0]
        group: List[HorizontalRule] = []
        while i < len(h_rules) and abs(h_rules[i][0] - y) <= H_Y_MERGE_TOL:
            group.append(h_rules[i])
            i += 1
        group.sort(key=lambda r: r[1])

        cur_x0, cur_x1 = group[0][1], group[0][2]
        for _, x0, x1 in group[1:]:
            if x0 - cur_x1 <= X_JOIN_TOL:
                cur_x1 = max(cur_x1, x1)
            else:
                out.append((y, cur_x0, cur_x1))
                cur_x0, cur_x1 = x0, x1
        out.append((y, cur_x0, cur_x1))
    return out


def _prune_near_duplicate_h(h_rules: List[HorizontalRule]) -> List[HorizontalRule]:
    if not h_rules:
        return []
    pruned: List[HorizontalRule] = []
    for y, x0, x1 in sorted(h_rules, key=lambda r: (r[0], r[1])):
        if pruned:
            py, px0, px1 = pruned[-1]
            overlap = max(0.0, min(x1, px1) - max(x0, px0))
            if (abs(y - py) < PRUNE_NEAR_Y_TOL and
                    overlap / max(1e-6, (x1 - x0)) > PRUNE_X_OVERLAP_RATIO):
                continue
        pruned.append((y, x0, x1))
    return pruned


def _pass_one_vertical_rules(lines_raw: list, v_rules: list, all_min_x: float, char_w: float) -> List[Dict[str, Any]]:
    lines_out: List[Dict[str, Any]] = []
    for line_words in lines_raw:
        line_words.sort(key=lambda t: t[0])
        line_y0 = min(w[3] for w in line_words)
        line_y1 = max(w[4] for w in line_words)

        buf: List[str] = []
        cursor_col = 0
        prev_x1 = None

        for x0, x1, text, *_ in line_words:
            start_col = int(round((x0 - all_min_x) / char_w))
            gap_cols = start_col - cursor_col if prev_x1 is not None else start_col
            if gap_cols <= 0 and prev_x1 is not None and x0 > prev_x1 + 0.1:
                gap_cols = MIN_SPACE_COLS
            if gap_cols > 0:
                buf.extend(" " * gap_cols)
                cursor_col += gap_cols

            for i, ch in enumerate(text):
                col = cursor_col + i
                if col >= len(buf):
                    buf.extend(" " * (col - len(buf) + 1))
                buf[col] = ch
            cursor_col += len(text)
            prev_x1 = x1

        candidate_cols: List[int] = []
        line_h = max(1e-6, line_y1 - line_y0)
        for x_mid, y0, y1 in v_rules:
            overlap = min(y1, line_y1) - max(y0, line_y0)
            if overlap >= MIN_V_OVERLAP_FRAC * line_h:
                c = int(round((x_mid - all_min_x) / char_w))
                if c >= 0:
                    candidate_cols.append(c)

        if candidate_cols:
            candidate_cols = _cluster_cols(candidate_cols, CHAR_COL_TOL)
            if ONLY_INSIDE_TEXT:
                last_char = len("".join(buf).rstrip()) - 1
                candidate_cols = [c for c in candidate_cols if 0 < c < last_char]
            for c in candidate_cols:
                if not _has_bar_near(buf, c, 1):
                    _insert_bar(buf, c)

        lines_out.append({"y0": line_y0, "y1": line_y1, "buf": buf})
    return lines_out


def _ensure_blank_slot(lines_out: List[dict], mids: List[float], idx: int, start_col: int, end_col: int, y_mid: float) -> int:
    def _row_is_blank(buf: List[str]) -> bool:
        if end_col >= len(buf):
            buf.extend(" " * (end_col - len(buf) + 1))
        return _segment_is_blank(buf, start_col, end_col)

    if _row_is_blank(lines_out[idx]["buf"]):
        return idx
    if idx + 1 < len(lines_out) and _row_is_blank(lines_out[idx + 1]["buf"]):
        return idx + 1
    if idx - 1 >= 0 and _row_is_blank(lines_out[idx - 1]["buf"]):
        return idx - 1

    max_len = max(len(l["buf"]) for l in lines_out)
    new_line = {"y0": y_mid - 0.1, "y1": y_mid + 0.1, "buf": [" "] * max_len}
    lines_out.insert(idx + 1, new_line)
    mids.insert(idx + 1, y_mid)
    return idx + 1


def _pass_two_horizontal_rules(lines_out: list, h_rules: list, all_min_x: float, char_w: float):
    mids = [0.5 * (l["y0"] + l["y1"]) for l in lines_out]

    for y_mid, x0, x1 in h_rules:
        start_col = int(round((x0 - all_min_x) / char_w))
        end_col = int(round((x1 - all_min_x) / char_w))
        if end_col <= start_col:
            continue

        if mids:
            diffs = [abs(y_mid - m) for m in mids]
            nearest = min(range(len(mids)), key=lambda i: diffs[i])
            if diffs[nearest] <= LINE_ATTACH_TOL:
                idx = nearest
            else:
                idx = _insert_empty_line(lines_out, y_mid, nearest if y_mid < mids[nearest] else nearest + 1)
                mids.insert(idx, y_mid)
        else:
            idx = _insert_empty_line(lines_out, y_mid, 0)
            mids = [y_mid]

        if end_col >= len(lines_out[idx]["buf"]):
            lines_out[idx]["buf"].extend(" " * (end_col - len(lines_out[idx]["buf"]) + 1))

        buf_for_split = lines_out[idx]["buf"]
        bar_pos = [i for i in range(start_col, end_col + 1) if buf_for_split[i] == "|"]
        cuts = [start_col] + bar_pos + [end_col + 1]

        for s, e in zip(cuts[:-1], cuts[1:]):
            s, e = s, e - 1
            if s > e:
                continue
            width = e - s + 1

            slot = _ensure_blank_slot(lines_out, mids, idx, s, e, y_mid)
            if not _validate_segment_safety(lines_out, slot, s, e):
                continue

            tgt = lines_out[slot]["buf"]
            if e >= len(tgt):
                tgt.extend(" " * (e - len(tgt) + 1))

            if width < H_MIN_ABS_CHARS and not _segment_is_blank(tgt, s, e):
                continue

            drawn_any = False
            for ss, ee in _blank_runs(tgt, s, e):
                if not _segment_has_enough_dash(tgt, ss, ee):
                    _draw_hline(tgt, ss, ee)
                    drawn_any = True

    # no explicit return (in-place)


def _page_to_lines(page: fitz.Page) -> List[str]:
    words = page.get_text("words")
    if not words:
        return []

    words.sort(key=lambda w: (round(w[1], 1), w[0]))
    widths = [(w[2] - w[0]) / max(len(w[4]), 1) for w in words if w[4].strip()]
    char_w = statistics.median(widths) if widths else 4.0
    all_min_x = min(w[0] for w in words)

    lines_raw = _group_words_into_rows(words)
    v_rules = _collect_vertical_rules(page)
    h_rules = _prune_near_duplicate_h(_merge_h_rules(_collect_horizontal_rules(page)))

    lines_out = _pass_one_vertical_rules(lines_raw, v_rules, all_min_x, char_w)
    _pass_two_horizontal_rules(lines_out, h_rules, all_min_x, char_w)

    out_lines = ["".join(l["buf"]).rstrip() for l in lines_out]
    if COLLAPSE_EOL_RUNS:
        out_lines = [re.sub(r"\|{2,}$", "|", ln) for ln in out_lines]
    return _squash_dupe_h(out_lines)


# ---------------------------- Table block formatting ------------------------

def _is_table_line(ln: str) -> bool:
    stripped = ln.rstrip()
    return ('|' in stripped) or (stripped and set(stripped) == {'-'})


def _add_horizontal_lines_from_string(table_string: str) -> List[str]:
    # keeps original exact logic: pad to uniform width + insert dashed rows
    lines = table_string.splitlines(keepends=True)
    candidate_widths = [len(l.rstrip("\n")) for l in lines if '|' in l]
    max_width = max(candidate_widths) if candidate_widths else max(len(l.rstrip("\n")) for l in lines)
    dashed_row = '-' * max_width

    processed: List[str] = []
    for l in lines:
        stripped = l.rstrip("\n")
        if '|' not in l or stripped == '':
            processed.append(dashed_row)
        else:
            processed.append(stripped.ljust(max_width))
    return ['\n'] + processed + ['\n']


def _replace_tables_in_lines(lines: List[str]) -> List[str]:
    out: List[str] = []
    i = 0
    N = len(lines)
    while i < N:
        if _is_table_line(lines[i]):
            table_block: List[str] = []
            while i < N and (_is_table_line(lines[i]) or lines[i].strip() == ""):
                table_block.append(lines[i])
                i += 1
            table_str = "\n" + "\n".join(table_block) + "\n"
            out.extend(_add_horizontal_lines_from_string(table_str))
        else:
            out.append(lines[i])
            i += 1
    return out




def extract_pdf_content(pdf_path: str) -> Dict[str, Any]:
    """Extract PDF content with structured data and metadata for pipeline integration"""
    doc = fitz.open(pdf_path)
    result = {
        "pages": [],
        "full_markdown": "",
        "metadata": {
            "total_pages": len(doc),
            "title": doc.metadata.get("title", ""),
            "author": doc.metadata.get("author", ""),
            "subject": doc.metadata.get("subject", ""),
            "creator": doc.metadata.get("creator", "")
        }
    }
    
    all_lines: List[str] = []
    
    for page_num in range(len(doc)):
        page = doc[page_num]
        page_lines = _page_to_lines(page)
        
        # Apply table formatting exactly like reference script
        page_md_lines = _replace_tables_in_lines(page_lines)
        page_markdown = "\n".join(line.rstrip("\n") for line in page_md_lines)
        
        # Create page content structure using formatted lines
        page_content = {
            "page_number": page_num + 1,
            "lines": page_md_lines,  # Use formatted lines with proper table structure
            "markdown": page_markdown,
            "tables": _identify_table_blocks(page_md_lines),  # Identify tables from formatted lines
            "paragraphs": _identify_paragraph_blocks(page_md_lines)  # Identify paragraphs from formatted lines
        }
        result["pages"].append(page_content)
        
        # Add page break markers for full content
        all_lines.extend([f"\n--- PAGE {page_num + 1} ---\n"])
        all_lines.extend(page_md_lines)
    
    result["full_markdown"] = "\n".join(line.rstrip("\n") for line in all_lines)
    doc.close()
    return result


def pdf_to_structured_data(pdf_bytes: bytes, filename: str) -> Dict[str, Any]:
    """Main entry point for pipeline - accepts bytes, returns structured data"""
    import tempfile
    import os
    
    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
        tmp_file.write(pdf_bytes)
        tmp_path = tmp_file.name
    
    try:
        return extract_pdf_content(tmp_path)
    finally:
        os.unlink(tmp_path)


def _identify_table_blocks(lines: List[str]) -> List[Dict[str, Any]]:
    """Identify table boundaries in the markdown lines"""
    tables = []
    in_table = False
    table_start = None
    
    for i, line in enumerate(lines):
        if _is_table_line(line):
            if not in_table:
                in_table = True
                table_start = i
        else:
            if in_table:
                tables.append({
                    "start_line": table_start,
                    "end_line": i - 1,
                    "content": "\n".join(lines[table_start:i]),
                    "type": "table"
                })
                in_table = False
    
    # Handle table that goes to end of page
    if in_table and table_start is not None:
        tables.append({
            "start_line": table_start,
            "end_line": len(lines) - 1,
            "content": "\n".join(lines[table_start:]),
            "type": "table"
        })
    
    return tables


def _identify_paragraph_blocks(lines: List[str]) -> List[Dict[str, Any]]:
    """Identify paragraph boundaries for chunking"""
    paragraphs = []
    current_para = []
    start_line = 0
    
    for i, line in enumerate(lines):
        if line.strip() == "":
            if current_para:
                paragraphs.append({
                    "start_line": start_line,
                    "end_line": i - 1,
                    "content": "\n".join(current_para),
                    "type": "paragraph"
                })
                current_para = []
            start_line = i + 1
        else:
            current_para.append(line)
    
    # Handle final paragraph
    if current_para:
        paragraphs.append({
            "start_line": start_line,
            "end_line": len(lines) - 1,
            "content": "\n".join(current_para),
            "type": "paragraph"
        })
    
    return paragraphs


class PDFProcessor:
    """Enhanced PDF processor for pipeline integration with token counting"""
    
    def __init__(self):
        try:
            import tiktoken
            self.encoder = tiktoken.get_encoding("cl100k_base")  # GPT-4 encoding
        except ImportError:
            # Fallback token estimation if tiktoken not available
            self.encoder = None
    
    def process_pdf(self, pdf_bytes: bytes, filename: str) -> Dict[str, Any]:
        """Process PDF and return structured data with chunking metadata"""
        
        # Extract content with page information (now includes proper table formatting)
        pdf_data = pdf_to_structured_data(pdf_bytes, filename)
        
        # Add token counts and enhance metadata
        for page in pdf_data["pages"]:
            page["token_count"] = self._count_tokens(page["markdown"])
            
            # Add token counts to blocks
            for table in page["tables"]:
                table["token_count"] = self._count_tokens(table["content"])
            for paragraph in page["paragraphs"]:
                paragraph["token_count"] = self._count_tokens(paragraph["content"])
        
        # Add overall statistics
        pdf_data["statistics"] = {
            "total_tokens": sum(page["token_count"] for page in pdf_data["pages"]),
            "total_tables": sum(len(page["tables"]) for page in pdf_data["pages"]),
            "total_paragraphs": sum(len(page["paragraphs"]) for page in pdf_data["pages"])
        }
        
        return pdf_data
    
    def _count_tokens(self, text: str) -> int:
        """Count tokens in text using tiktoken or fallback estimation"""
        if self.encoder:
            return len(self.encoder.encode(text))
        else:
            # Rough estimation: ~4 characters per token
            return len(text) // 4
