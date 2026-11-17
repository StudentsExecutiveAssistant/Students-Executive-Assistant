"""Генерація файлів .docx (Times New Roman 14, шапка справа, таблиці, колонки та додатки)."""
from __future__ import annotations

import re
from io import BytesIO

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

from app.config import SIGNERS

FONT = "Times New Roman"
TEXT_WIDTH = Cm(17)  # Ширина тексту на A4 (21 см) за полів 2.5 см зліва та 1.5 см справа.
PAGE_SIZE = 76       # До 38 рядків у кожній із 2 колонок (14pt, інтервал 1.15) на сторінку A4.

_APPENDIX_NUM_RE = re.compile(r"((?:зазначен(?:им|их|ої|ою|ого) у Додатку |Додаток ))\d+")


def with_appendix_num(spec: dict, n: int) -> dict:
    app = spec.get("appendix")
    if not app:
        return spec
    paras = [
        {**p, "t": _APPENDIX_NUM_RE.sub(rf"\g<1>{n}", p["t"], count=1)} if p["k"] == "body" else p
        for p in spec["paras"]
    ]
    return {**spec, "paras": paras, "appendix": {**app, "title": f"Додаток {n}"}}


def _run(p, text: str, bold: bool = False, size: int = 14):
    r = p.add_run(text)
    r.bold = bold
    r.font.name = FONT
    r.font.size = Pt(size)
    r._element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
    return r


def _style_par(
    p,
    *,
    align=None,
    indent=None,
    first=None,
    before: int = 0,
    after: int = 0,
    line: float = 1.0,
    keep: bool = False,
    page_break: bool = False,
):
    f = p.paragraph_format
    f.space_before, f.space_after, f.line_spacing = Pt(before), Pt(after), line
    if align is not None:
        p.alignment = align
    if indent is not None:
        f.left_indent = indent
    if first is not None:
        f.first_line_indent = first
    if keep:
        f.keep_with_next = True
    if page_break:
        f.page_break_before = True
    return p


def _par(
    doc: Document,
    text: str = "",
    *,
    align=None,
    indent=None,
    first=None,
    before: int = 0,
    after: int = 0,
    line: float = 1.0,
    bold: bool = False,
    keep: bool = False,
    page_break: bool = False,
):
    p = _style_par(
        doc.add_paragraph(),
        align=align,
        indent=indent,
        first=first,
        before=before,
        after=after,
        line=line,
        keep=keep,
        page_break=page_break,
    )
    if text:
        _run(p, text, bold)
    return p


def new_document() -> Document:
    doc = Document()
    s = doc.sections[0]
    s.page_width, s.page_height = Cm(21), Cm(29.7)
    s.left_margin, s.right_margin, s.top_margin, s.bottom_margin = Cm(2.5), Cm(1.5), Cm(1.5), Cm(1.5)
    st = doc.styles["Normal"]
    st.font.name, st.font.size = FONT, Pt(14)
    st.element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
    st.paragraph_format.space_after = Pt(0)
    return doc


def _blank(doc: Document, n: int = 1, line: float = 1.15, keep: bool = False, page_break: bool = False) -> None:
    for i in range(n):
        _par(doc, line=line, keep=keep, page_break=(page_break and i == 0))


def add_petition(doc: Document, spec: dict, first: bool = True, page_break: bool = False) -> None:
    keep = sum(len(p["items"]) if p["k"] in ("cols", "rows") else (p["k"] in ("list", "names")) for p in spec["paras"]) < 20
    _blank(doc, 6, line=1.5, keep=keep, page_break=page_break)
    for line in spec["addressee"]:
        _par(doc, line, align=WD_ALIGN_PARAGRAPH.RIGHT, line=1.15, keep=keep)
    _par(
        doc,
        spec.get("heading", "КЛОПОТАННЯ"),
        align=WD_ALIGN_PARAGRAPH.CENTER,
        before=12,
        after=12,
        line=1.15,
        bold=True,
        keep=True,
    )
    prev = None
    for para in spec["paras"]:
        if para["k"] == "cols":
            _add_inline_cols(doc, para["items"], keep=keep)
        elif para["k"] == "rows":
            _add_award_rows(doc, para["items"], keep=keep)
        elif para["k"] == "names":
            if prev != "names":
                _blank(doc, keep=keep)
            _par(doc, para["t"], indent=Cm(1.27), line=1.15, keep=keep)
        elif para["k"] == "body" or para["t"].startswith("Відповідальні за проведення"):
            _par(doc, para["t"], align=WD_ALIGN_PARAGRAPH.JUSTIFY, first=Cm(1.27), line=1.15, keep=keep)
        elif para["k"] == "list" and para["t"].startswith("-\t"):
            p = _par(doc, para["t"], indent=Cm(1.27), first=Cm(-0.63), line=1.15, keep=keep)
            p.paragraph_format.tab_stops.add_tab_stop(Cm(1.27))
        else:
            _par(doc, para["t"], line=1.15, keep=keep)
        prev = para["k"]
    _blank(doc, 3, keep=keep)
    for n, key in enumerate(spec["signers"]):
        lines, name = SIGNERS[key]
        last = n == len(spec["signers"]) - 1
        k = keep and not last
        p = _par(doc, line=1.15, keep=keep and (not last or len(lines) > 1))
        p.paragraph_format.tab_stops.add_tab_stop(TEXT_WIDTH, WD_TAB_ALIGNMENT.RIGHT)
        _run(p, lines[0] + "\t" + name)
        for extra in lines[1:]:
            _par(doc, extra, line=1.15, keep=k)
        if not last:
            _blank(doc, 2, keep=keep)
    app = spec.get("appendix")
    if app and app.get("kind") == "table":
        _add_table(doc, app)
    elif app and app.get("kind") == "students":
        _add_students(doc, app)
    elif app and app.get("kind") == "award":
        _add_award_appendix(doc, app)
    else:
        _blank(doc, 4)


def _set_borderless(table) -> None:
    table.autofit = False
    tbl_pr = table._tbl.tblPr
    tbl_pr.remove_all("w:tblBorders")
    tbl_pr.get_or_add_tblLayout().type = "fixed"
    borders = OxmlElement("w:tblBorders")
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{side}")
        el.set(qn("w:val"), "none")
        borders.append(el)
    tbl_pr.insert_element_before(borders, "w:tblLayout", "w:tblCellMar", "w:tblLook")


def _set_cell_margins(cell, left_dxa: int, right_dxa: int) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    tc_pr.remove_all("w:tcMar")
    mar = OxmlElement("w:tcMar")
    for side, val in (("top", 0), ("left", left_dxa), ("bottom", 0), ("right", right_dxa)):
        el = OxmlElement(f"w:{side}")
        el.set(qn("w:w"), str(val))
        el.set(qn("w:type"), "dxa")
        mar.append(el)
    tc_pr.insert_element_before(mar, "w:textDirection", "w:tcFitText", "w:vAlign", "w:hideMark")


def _two_col_table(
    doc: Document,
    left_lines: list[str],
    right_lines: list[str],
    *,
    indent_left,
    first_left,
    tab_left,
    indent_right,
    first_right,
    tab_right,
    widths: tuple = (Cm(8.5), Cm(8.5)),
    keep: bool = False,
) -> None:
    table = doc.add_table(rows=1, cols=2)
    table.alignment = WD_TABLE_ALIGNMENT.LEFT
    _set_borderless(table)
    for i, w in enumerate(widths):
        table.columns[i].width = w
        table.rows[0].cells[i].width = w
    left_cell, right_cell = table.rows[0].cells
    _set_cell_margins(left_cell, 0, 170)
    _set_cell_margins(right_cell, 170, 0)
    cols = (
        (left_cell, left_lines, indent_left, first_left, tab_left),
        (right_cell, right_lines, indent_right, first_right, tab_right),
    )
    for cell, lines, indent, first, tab_stop in cols:
        if not lines:
            _style_par(cell.paragraphs[0], line=1.15, keep=keep)
            continue
        for j, text in enumerate(lines):
            p = cell.paragraphs[0] if j == 0 else cell.add_paragraph()
            _style_par(p, indent=indent, first=first, line=1.15, keep=keep)
            p.paragraph_format.tab_stops.add_tab_stop(tab_stop)
            _run(p, text, size=14)


def _add_inline_cols(doc: Document, items: list[str], *, keep: bool) -> None:
    half = (len(items) + 1) // 2
    _two_col_table(
        doc,
        [f"-\t{s}" for s in items[:half]],
        [f"-\t{s}" for s in items[half:]],
        indent_left=Cm(1.27),
        first_left=Cm(-0.55),
        tab_left=Cm(1.27),
        indent_right=Cm(0.55),
        first_right=Cm(-0.55),
        tab_right=Cm(0.55),
        widths=(Cm(8.8), Cm(8.2)),
        keep=keep,
    )


def _add_students(doc: Document, app: dict) -> None:
    _par(doc, app["title"], align=WD_ALIGN_PARAGRAPH.RIGHT, after=14, line=1.15, page_break=True)
    numbered = list(enumerate(app["items"], 1))
    for offset in range(0, len(numbered), PAGE_SIZE):
        chunk = numbered[offset : offset + PAGE_SIZE]
        if offset > 0:
            sep = _par(doc, line=1.0, page_break=True)
            sep.paragraph_format.line_spacing = Pt(1)
            _run(sep, "", size=1)
        half = (len(chunk) + 1) // 2
        _two_col_table(
            doc,
            [f"{idx}.\t{item}" for idx, item in chunk[:half]],
            [f"{idx}.\t{item}" for idx, item in chunk[half:]],
            indent_left=Cm(0.9),
            first_left=Cm(-0.9),
            tab_left=Cm(0.9),
            indent_right=Cm(0.9),
            first_right=Cm(-0.9),
            tab_right=Cm(0.9),
        )


def _add_borderless_rows(doc: Document, rows: list[tuple[str, ...]], widths: tuple, *, keep: bool = False) -> None:
    table = doc.add_table(rows=len(rows), cols=len(widths))
    table.alignment = WD_TABLE_ALIGNMENT.LEFT
    _set_borderless(table)
    for r_idx, row in enumerate(rows):
        for c_idx, val in enumerate(row):
            cell = table.rows[r_idx].cells[c_idx]
            cell.width = widths[c_idx]
            _set_cell_margins(cell, 0, 80)
            p = cell.paragraphs[0]
            _style_par(p, line=1.15, keep=keep)
            _run(p, val, size=14)


def _add_award_rows(doc: Document, items: list[list[str]], *, keep: bool) -> None:
    rows = [tuple((row + ["", "", ""])[:3]) for row in items]
    _add_borderless_rows(doc, rows, (Cm(10.5), Cm(2.5), Cm(4.0)), keep=keep)


def _add_award_appendix(doc: Document, app: dict) -> None:
    _par(doc, app["title"], align=WD_ALIGN_PARAGRAPH.RIGHT, after=14, line=1.15, page_break=True)
    rows = [
        (f"{r_idx}.", *(row + ["", "", ""])[:3])
        for r_idx, row in enumerate(app["items"], 1)
    ]
    _add_borderless_rows(doc, rows, (Cm(1.4), Cm(9.6), Cm(2.4), Cm(3.6)))


def _add_table(doc: Document, t: dict) -> None:
    _par(doc, t["title"], align=WD_ALIGN_PARAGRAPH.RIGHT, after=8, line=1.15, page_break=True)
    table = doc.add_table(rows=1, cols=len(t["header"]))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    widths = [Cm(1), Cm(8.2), Cm(1.6), Cm(3), Cm(3.2)]
    for i, h in enumerate(t["header"]):
        c = table.rows[0].cells[i]
        c.text = ""
        _run(c.paragraphs[0], h, bold=True, size=12)
    for row in t["rows"]:
        cells = table.add_row().cells
        for i, v in enumerate(row):
            cells[i].text = ""
            _run(cells[i].paragraphs[0], v, bold=(row[1] == "Разом"), size=12)
    for r in table.rows:
        for i, w in enumerate(widths[: len(t["header"])]):
            r.cells[i].width = w
    if t.get("note"):
        _blank(doc, 1)
        _par(doc, t["note"], align=WD_ALIGN_PARAGRAPH.LEFT, first=Cm(1.27), line=1.15)


def build_docx(specs: list[dict]) -> bytes:
    doc = new_document()
    app_no = 0
    prev_had_appendix = False
    for i, spec in enumerate(specs):
        if spec.get("appendix"):
            app_no += 1
            spec = with_appendix_num(spec, app_no)
        add_petition(doc, spec, first=(i == 0), page_break=prev_had_appendix)
        prev_had_appendix = bool(spec.get("appendix"))
    body = doc.element.body
    while (
        len(doc.paragraphs) > 1
        and len(body) >= 2
        and body[-2].tag == qn("w:p")
        and not doc.paragraphs[-1].text.strip()
    ):
        body.remove(body[-2])
    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()


def preview_text(spec: dict) -> str:
    out = ["\n".join(spec["addressee"]), "", spec.get("heading", "КЛОПОТАННЯ"), ""]
    for p in spec["paras"]:
        if p["k"] == "cols":
            out.extend(f"- {x}" for x in p["items"])
        elif p["k"] == "rows":
            out.extend("  ".join(x for x in r if x) for r in p["items"])
        elif p["k"] == "list":
            out.append(p["t"].replace("-\t", "- "))
        else:
            out.append(p["t"])
    app = spec.get("appendix")
    if app:
        if app.get("kind") == "table":
            note = f" + примітка" if app.get("note") else ""
            out.append(f"\n[{app['title']}: {len(app['rows']) - 1} поз.{note}]")
        elif app.get("kind") in ("students", "award"):
            out.append(f"\n[{app['title']}: {len(app['items'])} студ.]")
    return "\n".join(out)
