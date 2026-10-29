"""Discover XML/CSV/XLSX files inside an upload (nested ZIPs included) and assign groups.

Grouping rules (kept from v4):
- A group is the 2–3 letter Oracle module prefix of a *business* ZIP name:
  ``AR_PAYMENT_TERM.zip`` → ``AR``, ``FND_APP_TREE.zip`` → ``FND``, ``1_PO_X.zip`` → ``PO``.
- The outermost ZIP that yields a prefix decides the group for everything below it.
- Batch ZIPs (``1_BATCH.zip``) and root/container ZIPs (``Export_20240101_1200.zip``, or long
  names with spaces) never become groups; batches inherit their parent's group.
- Files outside any business ZIP are grouped by their top folder, then their own filename.
  (v4 mistakenly grouped these as ``ROO`` — from the ``ROOT`` placeholder.)
- No usable prefix → ``EXTRAS``.

Safety: every member is bounded by a total byte budget, a file-count budget, a nesting depth
and a compression-ratio ceiling. Nested ZIPs are spilled to disk, never held in memory.
"""

import hashlib
import re
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from app.services.flatten import copy_bounded, gunzip_to

EXTRAS = "EXTRAS"
BATCH_ZIP = re.compile(r"^\d+[_\-]?BATCH", re.IGNORECASE)
ROOT_ZIP = re.compile(r".*_\d{8}_\d{4,6}.*\.zip$", re.IGNORECASE)
_UNSAFE_SEGMENT = re.compile(r'[<>:"\\|?*\x00-\x1F]')
SUPPORTED = {".xml": "xml", ".xml.gz": "xml", ".csv": "csv", ".xlsx": "xlsx"}
IGNORED_PREFIXES = ("__MACOSX/",)


@dataclass(frozen=True)
class Limits:
    max_files: int
    max_bytes: int
    max_depth: int
    max_ratio: int


@dataclass
class ScannedFile:
    logical_path: str
    filename: str
    group: str
    file_type: str
    size: int
    stored_name: str


@dataclass
class ScanResult:
    files: list[ScannedFile] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    bytes_written: int = 0


def module_prefix(name: str) -> str:
    """``AR_PAYMENT_TERM`` → ``AR``; ``2-FND_TREE.xml`` → ``FND``; ``x.xml`` → ``EXTRAS``."""
    stem = PurePosixPath((name or "").strip()).name
    for suffix in (".gz", ".xml", ".zip", ".csv", ".xlsx"):
        if stem.lower().endswith(suffix):
            stem = stem[: -len(suffix)]
    stem = re.sub(r"^\d+[_\-]+", "", stem)
    head = stem.split("_", 1)[0]
    letters = "".join(ch for ch in head if ch.isalpha()).upper()
    return letters[:3] if len(letters) >= 2 else EXTRAS


def is_batch_zip(name: str) -> bool:
    return bool(BATCH_ZIP.match(PurePosixPath(name).stem))


def is_root_zip(name: str) -> bool:
    stem = PurePosixPath(name).stem
    return bool(ROOT_ZIP.match(name)) or (" " in stem and len(stem) > 30)


def zip_group(name: str) -> str | None:
    """Group contributed by a ZIP's name, or None for batch/root containers."""
    if is_batch_zip(name) or is_root_zip(name):
        return None
    return module_prefix(name)


def group_for_loose_file(member_path: str) -> str:
    parts = PurePosixPath(member_path).parts
    if len(parts) > 1:
        g = module_prefix(parts[0])
        if g != EXTRAS:
            return g
    return module_prefix(parts[-1] if parts else member_path)


def safe_member_path(raw: str) -> str:
    """Normalise a ZIP member name to a relative POSIX path without traversal segments."""
    parts = []
    for seg in raw.replace("\\", "/").split("/"):
        seg = seg.strip()
        if seg in ("", ".", ".."):
            continue
        parts.append(_UNSAFE_SEGMENT.sub("_", seg))
    return "/".join(parts)


def file_type_for(name: str) -> tuple[str, str] | None:
    lower = name.lower()
    for suffix, ftype in SUPPORTED.items():
        if lower.endswith(suffix):
            return suffix, ftype
    return None


def _stored_name(logical_path: str, file_type: str) -> str:
    digest = hashlib.sha1(logical_path.encode(), usedforsecurity=False).hexdigest()[:20]
    return f"{digest}.{file_type}"


class _Scanner:
    def __init__(self, dest: Path, limits: Limits) -> None:
        self.dest = dest
        self.limits = limits
        self.result = ScanResult()
        self.seen: set[str] = set()

    @property
    def budget_left(self) -> int:
        return self.limits.max_bytes - self.result.bytes_written

    def note(self, msg: str) -> None:
        if len(self.result.notes) < 50:
            self.result.notes.append(msg)

    def full(self) -> bool:
        return len(self.result.files) >= self.limits.max_files or self.budget_left <= 0

    def walk(self, zip_path: Path, chain: list[str], group: str | None, depth: int) -> None:
        if depth > self.limits.max_depth:
            self.note(f"Skipped {chain[-1]}: nesting deeper than {self.limits.max_depth}.")
            return
        try:
            zf = zipfile.ZipFile(zip_path)
        except zipfile.BadZipFile:
            self.note(f"Skipped {chain[-1]}: not a valid ZIP archive.")
            return
        with zf:
            for info in zf.infolist():
                if self.full():
                    self.note("Stopped early: file-count or size budget reached.")
                    return
                if info.is_dir():
                    continue
                member = safe_member_path(info.filename)
                if not member or member.startswith(IGNORED_PREFIXES):
                    continue
                if PurePosixPath(member).name.startswith("."):
                    continue
                if (
                    info.compress_size
                    and info.file_size / info.compress_size > self.limits.max_ratio
                ):
                    self.note(f"Skipped {member}: suspicious compression ratio.")
                    continue
                try:
                    if member.lower().endswith(".zip"):
                        self._nested(zf, info, member, chain, group, depth)
                    else:
                        self._target(zf, info, member, chain, group)
                except (ValueError, zipfile.BadZipFile, OSError, EOFError) as exc:
                    self.note(f"Skipped {member}: {exc}")

    def _nested(
        self,
        zf: zipfile.ZipFile,
        info: zipfile.ZipInfo,
        member: str,
        chain: list[str],
        group: str | None,
        depth: int,
    ) -> None:
        name = PurePosixPath(member).name
        child_group = group if group is not None else zip_group(name)
        tmp_dir = self.dest / ".tmp"
        tmp_dir.mkdir(exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=tmp_dir, suffix=".zip", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            with zf.open(info) as src:
                copy_bounded(src, tmp_path, self.budget_left)
            self.walk(tmp_path, [*chain, name], child_group, depth + 1)
        finally:
            tmp_path.unlink(missing_ok=True)

    def _target(
        self,
        zf: zipfile.ZipFile,
        info: zipfile.ZipInfo,
        member: str,
        chain: list[str],
        group: str | None,
    ) -> None:
        kind = file_type_for(member)
        if kind is None:
            return
        suffix, ftype = kind
        logical = "/".join([*chain, member])
        if logical in self.seen:
            return
        self.seen.add(logical)
        stored = _stored_name(logical, ftype)
        out = self.dest / stored
        with zf.open(info) as src:
            if suffix == ".xml.gz":
                written = gunzip_to(src, out, self.budget_left)
            else:
                written = copy_bounded(src, out, self.budget_left)
        self.result.bytes_written += written
        self.result.files.append(
            ScannedFile(
                logical_path=logical,
                filename=PurePosixPath(member).name,
                group=group or group_for_loose_file(member),
                file_type=ftype,
                size=written,
                stored_name=stored,
            )
        )


def scan_upload(upload: Path, original_name: str, dest: Path, limits: Limits) -> ScanResult:
    """Scan an uploaded ZIP / XML / XML.GZ / CSV / XLSX into ``dest`` (the sources dir)."""
    dest.mkdir(parents=True, exist_ok=True)
    scanner = _Scanner(dest, limits)
    name = PurePosixPath(safe_member_path(original_name) or "upload").name
    try:
        if name.lower().endswith(".zip"):
            scanner.walk(upload, [name], zip_group(name), depth=1)
        elif (kind := file_type_for(name)) is not None:
            suffix, ftype = kind
            stored = _stored_name(name, ftype)
            with upload.open("rb") as src:
                writer = gunzip_to if suffix == ".xml.gz" else copy_bounded
                size = writer(src, dest / stored, limits.max_bytes)
            scanner.result.bytes_written = size
            scanner.result.files.append(
                ScannedFile(name, name, module_prefix(name), ftype, size, stored)
            )
        else:
            raise ValueError("Unsupported file type. Upload a .zip, .xml, .xml.gz, .csv or .xlsx.")
    finally:
        tmp = dest / ".tmp"
        if tmp.exists():
            for p in tmp.iterdir():
                p.unlink(missing_ok=True)
            tmp.rmdir()
    if not scanner.result.files:
        scanner.note("No XML, CSV or XLSX files were found in the upload.")
    return scanner.result
