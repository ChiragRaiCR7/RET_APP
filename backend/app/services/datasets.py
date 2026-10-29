"""Read, edit and export dataset CSVs."""

import csv
import io
import os
import threading
import zipfile
from collections import defaultdict
from collections.abc import Iterator
from pathlib import Path, PurePosixPath

from fastapi import HTTPException, status
from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from sqlalchemy.orm import Session

from app.models import Dataset
from app.schemas import ColumnInfo, EditIn
from app.services import search
from app.services.flatten import file_sha256
from app.services.workspaces import dataset_path

PROFILE_SAMPLE_ROWS = 500
# Whole-file edits load the CSV in memory; refuse beyond this to protect the server.
MAX_EDIT_BYTES = 64 * 1024 * 1024
_BOOLISH = frozenset({"true", "false", "yes", "no", "0", "1", "y", "n", "t", "f"})
# ponytail: process-local locks; a multi-process deployment needs a DB-level version check.
_locks: defaultdict[str, threading.Lock] = defaultdict(threading.Lock)


def read_rows(path: Path) -> Iterator[list[str]]:
    with path.open(encoding="utf-8", newline="") as fh:
        yield from csv.reader(fh)


def page(
    ds: Dataset, offset: int, limit: int, query: str | None
) -> tuple[list[str], list[list[str]], int]:
    """Return (header, rows, total). With ``query``, total counts matching rows only.

    ponytail: linear scan — fine for the converted Oracle extracts (≤ ~1M rows); move rows
    into SQLite if deep paging on huge files becomes a hot path.
    """
    it = read_rows(dataset_path(ds))
    header = next(it, [])
    needle = query.casefold() if query else None
    rows: list[list[str]] = []
    total = 0
    for row in it:
        if needle and not any(needle in c.casefold() for c in row):
            continue
        if offset <= total < offset + limit:
            rows.append(row)
        total += 1
    return header, rows, total


def profile_columns(ds: Dataset) -> list[ColumnInfo]:
    """Flag columns that carry little information so the UI can tuck them away (v4 rules)."""
    it = read_rows(dataset_path(ds))
    header = next(it, [])
    sample = [r for _, r in zip(range(PROFILE_SAMPLE_ROWS), it, strict=False)]
    out = []
    for i, name in enumerate(header):
        values = [r[i].strip() for r in sample if i < len(r)]
        filled = [v for v in values if v]
        distinct = {v.casefold() for v in filled}
        reason = None
        if sample and len(filled) < 0.2 * len(sample):
            reason = "mostly empty"
        elif len(distinct) == 1 and len(sample) > 1:
            reason = "single value"
        elif 0 < len(distinct) <= 2 and distinct <= _BOOLISH:
            reason = "boolean flag"
        out.append(ColumnInfo(name=name, kind="low" if reason else "value", reason=reason))
    return out


def apply_edits(db: Session, ds: Dataset, edits: EditIn) -> Dataset:
    path = dataset_path(ds)
    if path.stat().st_size > MAX_EDIT_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Dataset too large to edit online.")
    with _locks[ds.id]:
        it = read_rows(path)
        header = next(it, [])
        rows = list(it)
        index = {name: i for i, name in enumerate(header)}

        for cell in edits.cells:
            if cell.row >= len(rows):
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT, f"Row {cell.row} does not exist."
                )
            if cell.column not in index:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT, f"Unknown column {cell.column!r}."
                )
            row = rows[cell.row]
            row.extend([""] * (len(header) - len(row)))
            row[index[cell.column]] = cell.value

        for new in edits.append_rows:
            unknown = set(new) - set(index)
            if unknown:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT,
                    f"Unknown columns: {', '.join(sorted(unknown))}.",
                )
            rows.append([new.get(h, "") for h in header])

        drop = set(edits.delete_rows)
        if any(r >= len(rows) for r in drop):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "Row to delete does not exist."
            )
        if drop:
            rows = [r for i, r in enumerate(rows) if i not in drop]

        tmp = path.with_suffix(".edit")
        with tmp.open("w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(header)
            w.writerows(rows)
        os.replace(tmp, path)  # atomic: readers see the old or new file, never half of one

        ds.rows, ds.columns, ds.edited = len(rows), len(header), True
        ds.sha256 = file_sha256(path)
        search.reindex_dataset(db, ds)
        db.commit()
    return ds


def _xlsx_bytes(path: Path) -> bytes:
    """CSV → XLSX with every cell stored as text, so data like ``=HYPERLINK(...)`` never
    becomes a live formula in the recipient's Excel (CSV/formula injection)."""
    wb = Workbook(write_only=True)
    ws = wb.create_sheet("Data")
    for row in read_rows(path):
        cells = []
        for value in row:
            cell = WriteOnlyCell(ws, value=value)
            cell.data_type = "s"  # override openpyxl's "starts with =" → formula inference
            cells.append(cell)
        ws.append(cells)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def export_one(ds: Dataset, fmt: str) -> tuple[bytes | Path, str, str]:
    path = dataset_path(ds)
    if fmt == "xlsx":
        return (
            _xlsx_bytes(path),
            ds.name.removesuffix(".CSV") + ".XLSX",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    return path, ds.name, "text/csv; charset=utf-8"


def _archive_name(ds: Dataset, fmt: str, preserve: bool) -> str:
    ext = ".XLSX" if fmt == "xlsx" else ".CSV"
    if preserve and ds.logical_path:
        parent = PurePosixPath(ds.logical_path).parent
        return str(parent / (ds.name.removesuffix(".CSV") + ext)).lstrip("/")
    return f"{ds.group}/{ds.name.removesuffix('.CSV')}{ext}"


def export_zip(datasets: list[Dataset], fmt: str, preserve: bool, dest: Path) -> None:
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for ds in datasets:
            name = _archive_name(ds, fmt, preserve)
            if fmt == "xlsx":
                zf.writestr(name, _xlsx_bytes(dataset_path(ds)))
            else:
                zf.write(dataset_path(ds), name)
