"""
XLSX Generation Service
Creates Excel files from CSV data without external dependencies like openpyxl.
Based on logic from main.py
"""
import io
import csv
import zipfile
from pathlib import Path
from typing import Optional
from xml.sax.saxutils import escape as xml_escape
import logging

logger = logging.getLogger(__name__)


def _excel_col_name(n: int) -> str:
    """Convert column number to Excel column letter (A, B, ... Z, AA, AB, etc.)"""
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _clean_excel_text(v) -> str:
    """Clean text for Excel by removing null characters"""
    if v is None:
        return ""
    return str(v).replace("\x00", "")


def csv_to_xlsx_bytes(
    csv_path: str, 
    max_rows: Optional[int] = None, 
    max_cols: Optional[int] = None
) -> bytes:
    """
    Convert CSV file to XLSX bytes.
    Creates a minimal valid XLSX file without external dependencies.
    """
    rows_xml = []
    r_idx = 0

    try:
        with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f)
            for row in reader:
                r_idx += 1
                if max_rows and r_idx > max_rows:
                    break

                cells = []
                c_idx = 0
                for val in row:
                    c_idx += 1
                    if max_cols and c_idx > max_cols:
                        break
                    col = _excel_col_name(c_idx)
                    text_val = xml_escape(_clean_excel_text(val))
                    cells.append(f'<c r="{col}{r_idx}" t="inlineStr"><is><t>{text_val}</t></is></c>')

                rows_xml.append(f'<row r="{r_idx}">{"".join(cells)}</row>')
    except UnicodeDecodeError:
        # Fallback to latin-1 encoding
        with open(csv_path, "r", encoding="latin-1", newline="") as f:
            reader = csv.reader(f)
            r_idx = 0
            for row in reader:
                r_idx += 1
                if max_rows and r_idx > max_rows:
                    break

                cells = []
                c_idx = 0
                for val in row:
                    c_idx += 1
                    if max_cols and c_idx > max_cols:
                        break
                    col = _excel_col_name(c_idx)
                    text_val = xml_escape(_clean_excel_text(val))
                    cells.append(f'<c r="{col}{r_idx}" t="inlineStr"><is><t>{text_val}</t></is></c>')

                rows_xml.append(f'<row r="{r_idx}">{"".join(cells)}</row>')

    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        "<sheetData>" + "".join(rows_xml) + "</sheetData>"
        "</worksheet>"
    )

    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>
"""
    rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>
"""
    workbook = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="Sheet1" sheetId="1" r:id="rId1"/>
  </sheets>
</workbook>
"""
    wb_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>
"""

    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("xl/workbook.xml", workbook)
        zf.writestr("xl/_rels/workbook.xml.rels", wb_rels)
        zf.writestr("xl/worksheets/sheet1.xml", sheet_xml)

    return out.getvalue()


def get_xlsx_bytes_from_csv(csv_path: str, max_rows: Optional[int] = None) -> bytes:
    """
    Get XLSX bytes for a CSV file with automatic size handling.
    For large files (>50MB), limits to 50000 rows.
    """
    try:
        size_mb = Path(csv_path).stat().st_size / (1024 * 1024)
    except Exception:
        size_mb = 0.0
    
    if max_rows is None:
        max_rows = 50_000 if size_mb > 50 else None
    
    return csv_to_xlsx_bytes(csv_path, max_rows=max_rows, max_cols=None)
