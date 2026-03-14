
"""
XLSX Generation Service (No external dependencies)

Creates minimal Excel (.xlsx) files from CSV data (or in-memory rows) without
libraries like openpyxl.

Now supports MULTIPLE SHEETS.

Limitations / Notes:
- All cells are written as inline strings (t="inlineStr")
- No styling, types, formulas, merged cells, etc.
- Designed for portability and simplicity.
"""

from __future__ import annotations

import csv
import io
import logging
import re
import zipfile
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Sequence, Tuple
from xml.sax.saxutils import escape as xml_escape

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------
# Static XML parts (minimal package)
# --------------------------------------------------------------------

_RELS_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1"
    Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"
    Target="xl/workbook.xml"/>
</Relationships>
"""


# --------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------

_INVALID_SHEET_CHARS = re.compile(r"[\[\]\:\*\?\/\\]")

def _excel_col_name(n: int) -> str:
    """Convert 1-based column index to Excel column letters."""
    if n <= 0:
        raise ValueError("Column index must be >= 1")
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _clean_excel_text(value: object) -> str:
    """Clean text for Excel XML by removing null characters."""
    if value is None:
        return ""
    return str(value).replace("\x00", "")


def _sanitize_sheet_name(name: str, used: set[str]) -> str:
    """
    Excel sheet name rules (simplified):
    - Max 31 chars
    - Cannot contain: []:*?/\\
    - Cannot be empty
    - Avoid duplicates
    """
    if name is None:
        name = "Sheet"

    name = name.strip() or "Sheet"
    name = _INVALID_SHEET_CHARS.sub("_", name)
    name = name[:31]

    # Ensure unique
    base = name
    i = 2
    while name in used:
        suffix = f"_{i}"
        name = (base[: max(0, 31 - len(suffix))] + suffix)[:31]
        i += 1

    used.add(name)
    return name


def _iter_csv_rows(csv_path: str, *, max_rows: Optional[int] = None) -> Iterator[List[str]]:
    """
    Yield rows from a CSV file. Tries UTF-8-SIG, falls back to Latin-1.
    """
    def _read(enc: str) -> Iterator[List[str]]:
        with open(csv_path, "r", encoding=enc, newline="") as f:
            reader = csv.reader(f)
            for i, row in enumerate(reader, start=1):
                if max_rows is not None and i > max_rows:
                    break
                yield row

    try:
        yield from _read("utf-8-sig")
        return
    except UnicodeDecodeError:
        logger.warning("UTF-8 decode failed for %s, falling back to latin-1", csv_path)

    yield from _read("latin-1")


def _rows_to_sheet_xml(
    rows: Iterable[Sequence[object]],
    *,
    max_rows: Optional[int] = None,
    max_cols: Optional[int] = None,
) -> str:
    """
    Convert rows into worksheet XML (<sheetData>...), inline strings.
    """
    rows_xml_parts: List[str] = []

    for r_idx, row in enumerate(rows, start=1):
        if max_rows is not None and r_idx > max_rows:
            break

        cells: List[str] = []
        for c_idx, raw_val in enumerate(row, start=1):
            if max_cols is not None and c_idx > max_cols:
                break

            col = _excel_col_name(c_idx)
            text_val = xml_escape(_clean_excel_text(raw_val))
            cells.append(
                f'<c r="{col}{r_idx}" t="inlineStr"><is><t>{text_val}</t></is></c>'
            )

        rows_xml_parts.append(f'<row r="{r_idx}">{"".join(cells)}</row>')

    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        "<sheetData>"
        + "".join(rows_xml_parts)
        + "</sheetData>"
        "</worksheet>"
    )


# --------------------------------------------------------------------
# Dynamic XLSX package builders (multi-sheet)
# --------------------------------------------------------------------

def _build_content_types_xml(sheet_count: int) -> str:
    overrides = "\n".join(
        f'  <Override PartName="/xl/worksheets/sheet{i}.xml" '
        f'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        for i in range(1, sheet_count + 1)
    )
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
{overrides}
</Types>
"""


def _build_workbook_xml(sheet_names: List[str]) -> str:
    # rId1, rId2, ...
    sheet_entries = "\n".join(
        f'    <sheet name="{xml_escape(name)}" sheetId="{i}" r:id="rId{i}"/>'
        for i, name in enumerate(sheet_names, start=1)
    )
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
{sheet_entries}
  </sheets>
</workbook>
"""


def _build_workbook_rels_xml(sheet_count: int) -> str:
    rel_entries = "\n".join(
        f'  <Relationship Id="rId{i}" '
        f'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        f'Target="worksheets/sheet{i}.xml"/>'
        for i in range(1, sheet_count + 1)
    )
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
{rel_entries}
</Relationships>
"""


def _package_xlsx_multi(sheet_xml_by_index: Dict[int, str], sheet_names: List[str]) -> bytes:
    """
    Create an XLSX package containing N worksheets.
    sheet_xml_by_index keys are 1..N.
    """
    sheet_count = len(sheet_names)

    content_types_xml = _build_content_types_xml(sheet_count)
    workbook_xml = _build_workbook_xml(sheet_names)
    wb_rels_xml = _build_workbook_rels_xml(sheet_count)

    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types_xml)
        zf.writestr("_rels/.rels", _RELS_XML)
        zf.writestr("xl/workbook.xml", workbook_xml)
        zf.writestr("xl/_rels/workbook.xml.rels", wb_rels_xml)

        for i in range(1, sheet_count + 1):
            zf.writestr(f"xl/worksheets/sheet{i}.xml", sheet_xml_by_index[i])

    return out.getvalue()


# --------------------------------------------------------------------
# Public API (single-sheet, backward compatible)
# --------------------------------------------------------------------

def csv_to_xlsx_bytes(
    csv_path: str,
    max_rows: Optional[int] = None,
    max_cols: Optional[int] = None,
) -> bytes:
    """
    Convert a CSV file to XLSX bytes (single sheet "Sheet1").
    """
    rows = _iter_csv_rows(csv_path, max_rows=max_rows)
    return rows_to_xlsx_bytes(rows, sheet_name="Sheet1", max_rows=max_rows, max_cols=max_cols)


def get_xlsx_bytes_from_csv(csv_path: str, max_rows: Optional[int] = None) -> bytes:
    """
    Get XLSX bytes for a CSV file with automatic size handling.
    For large files (>50MB), limits to 50,000 rows unless max_rows is provided.
    """
    try:
        size_mb = Path(csv_path).stat().st_size / (1024 * 1024)
    except Exception:
        size_mb = 0.0

    if max_rows is None and size_mb > 50:
        max_rows = 50_000

    return csv_to_xlsx_bytes(csv_path, max_rows=max_rows, max_cols=None)


def rows_to_xlsx_bytes(
    rows: Iterable[Sequence[object]],
    sheet_name: str = "Sheet1",
    max_rows: Optional[int] = None,
    max_cols: Optional[int] = None,
) -> bytes:
    """
    Build a single-sheet XLSX bytes from an iterable of rows (no CSV required).
    """
    used = set()
    safe_name = _sanitize_sheet_name(sheet_name, used)
    sheet_xml = _rows_to_sheet_xml(rows, max_rows=max_rows, max_cols=max_cols)
    return _package_xlsx_multi({1: sheet_xml}, [safe_name])


# --------------------------------------------------------------------
# NEW: Public API (multi-sheet)
# --------------------------------------------------------------------

def csvs_to_xlsx_bytes(
    sheets: Sequence[Tuple[str, str]],
    *,
    max_rows: Optional[int] = None,
    max_cols: Optional[int] = None,
) -> bytes:
    """
    Convert multiple CSV files into a single XLSX with multiple sheets.

    Args:
        sheets: sequence of (sheet_name, csv_path)
        max_rows: optional row limit per sheet
        max_cols: optional column limit per sheet

    Returns:
        XLSX bytes containing all sheets.
    """
    if not sheets:
        raise ValueError("No sheets provided")

    used_names: set[str] = set()
    sheet_names: List[str] = []
    sheet_xml_by_index: Dict[int, str] = {}

    for idx, (name, csv_path) in enumerate(sheets, start=1):
        safe_name = _sanitize_sheet_name(name, used_names)
        sheet_names.append(safe_name)

        rows = _iter_csv_rows(csv_path, max_rows=max_rows)
        sheet_xml_by_index[idx] = _rows_to_sheet_xml(rows, max_rows=max_rows, max_cols=max_cols)

    return _package_xlsx_multi(sheet_xml_by_index, sheet_names)


def multi_rows_to_xlsx_bytes(
    sheets: Sequence[Tuple[str, Iterable[Sequence[object]]]],
    *,
    max_rows: Optional[int] = None,
    max_cols: Optional[int] = None,
) -> bytes:
    """
    Build a multi-sheet XLSX from in-memory row iterables.

    Args:
        sheets: sequence of (sheet_name, rows_iterable)
        max_rows: optional row limit per sheet
        max_cols: optional col limit per sheet
    """
    if not sheets:
        raise ValueError("No sheets provided")

    used_names: set[str] = set()
    sheet_names: List[str] = []
    sheet_xml_by_index: Dict[int, str] = {}

    for idx, (name, rows) in enumerate(sheets, start=1):
        safe_name = _sanitize_sheet_name(name, used_names)
        sheet_names.append(safe_name)
        sheet_xml_by_index[idx] = _rows_to_sheet_xml(rows, max_rows=max_rows, max_cols=max_cols)

    return _package_xlsx_multi(sheet_xml_by_index, sheet_names)
