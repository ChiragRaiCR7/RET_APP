"""Turn record-oriented XML (and CSV/XLSX) into normalised UTF-8 CSV files.

XML rules (kept from v4):
- The record element is the most frequent direct child of the root (e.g. ROWSET/ROW,
  DATA_DS/G_1). If every child is unique, each root child is one record; an empty root
  is itself the record.
- A record is flattened depth-first: leaf text becomes a column named by its path
  (``Parent.Child``), repeated siblings are suffixed ``[2]``, ``[3]``…, attributes become
  ``path@attr``.
- Column order is first-seen order across all records.

Parsing is streaming (constant memory) and hardened: no DTD loading, no entity expansion,
no network access.
"""

import csv
import gzip
import hashlib
import io
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any

from lxml import etree

DETECT_SAMPLE_CHILDREN = 500
# Excel's per-cell limit; also our cap so one runaway field cannot exhaust disk.
MAX_CELL_CHARS = 32_767


@dataclass(frozen=True)
class TableStats:
    rows: int
    columns: int
    record_tag: str | None
    sha256: str


def _local(tag: Any) -> str | None:
    # Comments / processing instructions have non-string tags.
    if not isinstance(tag, str):
        return None
    return tag.rsplit("}", 1)[-1]


def _iterparse(source: Path, events: tuple[str, ...]) -> Iterator[tuple[str, Any]]:
    return etree.iterparse(  # type: ignore[no-any-return]
        str(source),
        events=events,
        resolve_entities=False,
        no_network=True,
        load_dtd=False,
        huge_tree=False,
        remove_comments=True,
        remove_pis=True,
    )


def detect_record_tag(xml_path: Path) -> str | None:
    """Most common direct child tag of the root, or None if root children are all distinct."""
    counts: Counter[str] = Counter()
    depth = 0
    seen = 0
    for event, elem in _iterparse(xml_path, ("start", "end")):
        if event == "start":
            depth += 1
            if depth == 2:
                name = _local(elem.tag)
                if name:
                    counts[name] += 1
                    seen += 1
                if seen >= DETECT_SAMPLE_CHILDREN:
                    break
        else:
            depth -= 1
            if depth >= 1:
                elem.clear()
    if not counts:
        return None
    tag, n = counts.most_common(1)[0]
    return tag if n > 1 or len(counts) == 1 else None


def flatten_record(elem: Any, max_chars: int = MAX_CELL_CHARS) -> dict[str, str]:
    row: dict[str, str] = {}

    def put(key: str, value: str | None) -> None:
        if key and key not in row:
            row[key] = (value or "").strip()[:max_chars]

    for attr, val in elem.attrib.items():
        put(f"@{_local(attr)}", val)

    stack: list[tuple[Any, str]] = []
    counts: Counter[str] = Counter()
    kids = [c for c in elem if _local(c.tag)]
    for child in kids:
        name = _local(child.tag) or ""
        counts[name] += 1
        stack.append((child, name if counts[name] == 1 else f"{name}[{counts[name]}]"))
    stack.reverse()

    while stack:
        node, path = stack.pop()
        for attr, val in node.attrib.items():
            put(f"{path}@{_local(attr)}", val)
        children = [c for c in node if _local(c.tag)]
        if not children:
            put(path, node.text)
            continue
        local: Counter[str] = Counter()
        pending: list[tuple[Any, str]] = []
        for child in children:
            name = _local(child.tag) or ""
            local[name] += 1
            idx = local[name]
            pending.append((child, f"{path}.{name}" if idx == 1 else f"{path}.{name}[{idx}]"))
        stack.extend(reversed(pending))
    return row


def iter_xml_records(
    xml_path: Path, max_chars: int = MAX_CELL_CHARS
) -> tuple[str | None, Iterator[dict[str, str]]]:
    """Return (record_tag, row iterator). Records are cleared after use to bound memory."""
    record_tag = detect_record_tag(xml_path)

    def rows() -> Iterator[dict[str, str]]:
        depth = 0
        root_has_children = False
        for event, elem in _iterparse(xml_path, ("start", "end")):
            if event == "start":
                depth += 1
                if depth == 2:
                    root_has_children = True
                continue
            depth -= 1
            if depth == 1 and (record_tag is None or _local(elem.tag) == record_tag):
                yield flatten_record(elem, max_chars)
                elem.clear()
                parent = elem.getparent()
                if parent is not None:
                    # Drop processed siblings so the tree never grows beyond one record.
                    while elem.getprevious() is not None:
                        del parent[0]
            elif depth == 0 and not root_has_children:
                yield flatten_record(elem, max_chars)

    return record_tag, rows()


class _CsvSink:
    """Writes rows whose column set grows over time; pads early rows when finalising."""

    def __init__(self, dest: Path) -> None:
        self.dest = dest
        self.tmp = dest.with_suffix(".part")
        self._fh = self.tmp.open("w", encoding="utf-8", newline="")
        self._w = csv.writer(self._fh)
        self.columns: dict[str, int] = {}
        self.rows = 0

    def add(self, record: dict[str, str]) -> None:
        for key in record:
            if key not in self.columns:
                self.columns[key] = len(self.columns)
        out = [""] * len(self.columns)
        for key, val in record.items():
            out[self.columns[key]] = val
        self._w.writerow(out)
        self.rows += 1

    def finish(self) -> tuple[int, int]:
        self._fh.close()
        width = len(self.columns)
        with (
            self.tmp.open(encoding="utf-8", newline="") as src,
            self.dest.open("w", encoding="utf-8", newline="") as dst,
        ):
            writer = csv.writer(dst)
            writer.writerow(list(self.columns))
            for row in csv.reader(src):
                writer.writerow(row + [""] * (width - len(row)))
        self.tmp.unlink()
        return self.rows, width

    def abort(self) -> None:
        self._fh.close()
        self.tmp.unlink(missing_ok=True)


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def xml_to_csv(src: Path, dest: Path, max_chars: int = MAX_CELL_CHARS) -> TableStats:
    record_tag, records = iter_xml_records(src, max_chars)
    sink = _CsvSink(dest)
    try:
        for record in records:
            if record:
                sink.add(record)
    except BaseException:
        sink.abort()
        raise
    rows, cols = sink.finish()
    if rows == 0:
        dest.unlink(missing_ok=True)
        raise ValueError("No records found in XML.")
    return TableStats(rows, cols, record_tag, file_sha256(dest))


def _open_text(path: Path) -> io.TextIOWrapper:
    raw: IO[bytes] = path.open("rb")
    head = raw.read(1 << 16)
    raw.seek(0)
    try:
        head.decode("utf-8")
        encoding = "utf-8-sig"
    except UnicodeDecodeError:
        # Legacy exports; cp1252 decodes every byte so this never fails.
        encoding = "cp1252"
    return io.TextIOWrapper(raw, encoding=encoding, newline="")


def csv_to_csv(src: Path, dest: Path) -> TableStats:
    """Normalise an uploaded CSV to UTF-8 with a rectangular shape."""
    with _open_text(src) as fh:
        reader = csv.reader(fh)
        header = next(reader, None)
        if not header:
            raise ValueError("CSV file is empty.")
        rows = 0
        with dest.open("w", encoding="utf-8", newline="") as out:
            writer = csv.writer(out)
            writer.writerow(header)
            width = len(header)
            for row in reader:
                if not any(row):
                    continue
                writer.writerow((row + [""] * width)[:width] if len(row) != width else row)
                rows += 1
    return TableStats(rows, width, None, file_sha256(dest))


def xlsx_to_csv(src: Path, dest: Path) -> TableStats:
    """First worksheet of an XLSX → CSV (values only, formulas are not evaluated)."""
    from openpyxl import load_workbook

    wb = load_workbook(src, read_only=True, data_only=True)
    try:
        ws = wb.worksheets[0]
        it = ws.iter_rows(values_only=True)
        header_raw = next(it, None)
        if not header_raw:
            raise ValueError("Worksheet is empty.")
        header = [str(h) if h is not None else f"COL_{i + 1}" for i, h in enumerate(header_raw)]
        rows = 0
        with dest.open("w", encoding="utf-8", newline="") as out:
            writer = csv.writer(out)
            writer.writerow(header)
            for values in it:
                cells = ["" if v is None else str(v) for v in values[: len(header)]]
                if not any(cells):
                    continue
                writer.writerow(cells + [""] * (len(header) - len(cells)))
                rows += 1
    finally:
        wb.close()
    return TableStats(rows, len(header), None, file_sha256(dest))


def to_csv(file_type: str, src: Path, dest: Path, max_chars: int = MAX_CELL_CHARS) -> TableStats:
    """Process-pool entry point: convert any supported source type to a dataset CSV."""
    if file_type == "xml":
        return xml_to_csv(src, dest, max_chars)
    if file_type == "csv":
        return csv_to_csv(src, dest)
    if file_type == "xlsx":
        return xlsx_to_csv(src, dest)
    raise ValueError(f"Unsupported file type: {file_type}")


def gunzip_to(src: IO[bytes], dest: Path, max_bytes: int) -> int:
    """Inflate a .gz stream to dest, refusing to write more than max_bytes."""
    written = 0
    with gzip.GzipFile(fileobj=src) as gz, dest.open("wb") as out:
        while chunk := gz.read(1 << 20):
            written += len(chunk)
            if written > max_bytes:
                raise ValueError("Inflated .gz exceeds the remaining size budget.")
            out.write(chunk)
    return written


def copy_bounded(src: IO[bytes], dest: Path, max_bytes: int) -> int:
    written = 0
    with dest.open("wb") as out:
        while chunk := src.read(1 << 20):
            written += len(chunk)
            if written > max_bytes:
                raise ValueError("File exceeds the remaining size budget.")
            out.write(chunk)
    return written
