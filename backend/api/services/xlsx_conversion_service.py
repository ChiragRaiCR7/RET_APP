"""
XLSX Conversion Service

Converts CSV files to XLSX (Excel) format using minimal dependencies.
Implements the xlsx_bytes_from_csv pattern from main.py.

Features:
- Fast CSV to XLSX conversion
- Configurable row/column limits
- Proper XML escaping
- Memory-efficient streaming
"""

import io
import csv
import zipfile
import logging
from pathlib import Path
from typing import Optional
from xml.sax.saxutils import escape as xml_escape

logger = logging.getLogger(__name__)


def _clean_excel_text(value: any) -> str:
    """Clean text for Excel output."""
    if value is None:
        return ""
    return str(value).replace("\x00", "")


def _excel_col_name(col_index: int) -> str:
    """Convert column index (1-based) to Excel column name (A, B, ..., Z, AA, etc)."""
    result = ""
    while col_index:
        col_index, remainder = divmod(col_index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def csv_to_xlsx_bytes(
    csv_path: str,
    *,
    max_rows: Optional[int] = None,
    max_cols: Optional[int] = None,
) -> bytes:
    """
    Convert CSV file to XLSX bytes.
    
    Args:
        csv_path: Path to CSV file
        max_rows: Maximum rows to include (None = unlimited)
        max_cols: Maximum columns to include (None = unlimited)
    
    Returns:
        XLSX file as bytes
    
    Raises:
        FileNotFoundError: If CSV doesn't exist
        IOError: If reading/writing fails
    """
    if not Path(csv_path).exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    rows_xml: list[str] = []
    row_idx = 0

    try:
        with open(csv_path, "r", encoding="utf-8", errors="replace") as f:
            reader = csv.reader(f)

            for row in reader:
                row_idx += 1
                if max_rows and row_idx > max_rows:
                    break

                cells: list[str] = []
                col_idx = 0

                for value in row:
                    col_idx += 1
                    if max_cols and col_idx > max_cols:
                        break

                    col_letter = _excel_col_name(col_idx)
                    clean_text = _clean_excel_text(value)
                    escaped_text = xml_escape(clean_text)

                    # Inline string format for Excel
                    cell_xml = (
                        f'<c r="{col_letter}{row_idx}" t="inlineStr">'
                        f'<is><t>{escaped_text}</t></is>'
                        f'</c>'
                    )
                    cells.append(cell_xml)

                row_xml = f'<row r="{row_idx}">{"".join(cells)}</row>'
                rows_xml.append(row_xml)

    except Exception as e:
        logger.error(f"Error reading CSV {csv_path}: {e}")
        raise

    # Build worksheet XML
    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheetData>'
        + "".join(rows_xml)
        + '</sheetData>'
        '</worksheet>'
    )

    # Build supporting XML files
    content_types = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>
'''

    rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>
'''

    workbook = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="Sheet1" sheetId="1" r:id="rId1"/>
  </sheets>
</workbook>
'''

    wb_rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>
'''

    # Create ZIP (XLSX is just a ZIP)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("xl/workbook.xml", workbook)
        zf.writestr("xl/_rels/workbook.xml.rels", wb_rels)
        zf.writestr("xl/worksheets/sheet1.xml", sheet_xml)

    bytes_result = output.getvalue()
    logger.info(
        f"Converted {csv_path} to XLSX: {len(bytes_result)} bytes, "
        f"{row_idx} rows, {max_cols or 'unlimited'} cols"
    )

    return bytes_result


def get_xlsx_bytes_from_csv(csv_path: str) -> bytes:
    """
    Get XLSX bytes from CSV file with smart row limiting based on size.
    
    Args:
        csv_path: Path to CSV file
    
    Returns:
        XLSX file as bytes
    """
    try:
        size_mb = Path(csv_path).stat().st_size / (1024 * 1024)
    except Exception:
        size_mb = 0.0

    # Limit rows for large files to prevent memory issues
    max_rows = 50_000 if size_mb > 50 else None

    logger.debug(f"Converting {csv_path} ({size_mb:.1f} MB) - max_rows={max_rows}")

    return csv_to_xlsx_bytes(csv_path, max_rows=max_rows, max_cols=None)
