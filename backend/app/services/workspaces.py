"""Workspace lifecycle: upload → scan → convert → datasets. All file paths derive from DB ids."""

import hashlib
import logging
import multiprocessing
import os
import re
import shutil
from collections import defaultdict
from concurrent.futures import Future, ProcessPoolExecutor, as_completed
from pathlib import Path, PurePosixPath

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import new_session
from app.models import Dataset, SourceFile, User, Workspace, new_id
from app.schemas import GroupSummary
from app.services import jobs, search
from app.services.flatten import TableStats, to_csv
from app.services.oracle_catalog import lookup
from app.services.scanning import Limits, scan_upload

log = logging.getLogger("ret.workspaces")

_NAME_UNSAFE = re.compile(r"[^A-Za-z0-9._\- ]+")
_SPACES = re.compile(r"\s+")
# Below this many files the process-pool start-up cost outweighs parallelism.
INLINE_CONVERT_MAX_FILES = 4


def workspace_dir(workspace_id: str) -> Path:
    return get_settings().workspaces_dir / workspace_id


def sources_dir(workspace_id: str) -> Path:
    return workspace_dir(workspace_id) / "sources"


def datasets_dir(workspace_id: str) -> Path:
    return workspace_dir(workspace_id) / "datasets"


def dataset_path(ds: Dataset) -> Path:
    return datasets_dir(ds.workspace_id) / ds.stored_name


def get_owned(db: Session, user: User, workspace_id: str) -> Workspace:
    """Load a workspace the user may access. 404 (not 403) avoids leaking existence."""
    ws = db.get(Workspace, workspace_id)
    if ws is None or ws.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workspace not found.")
    return ws


def get_owned_dataset(db: Session, user: User, dataset_id: str) -> Dataset:
    ds = db.get(Dataset, dataset_id)
    if ds is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dataset not found.")
    get_owned(db, user, ds.workspace_id)
    return ds


def new_workspace_dir() -> tuple[str, Path]:
    ws_id = new_id()
    root = workspace_dir(ws_id)
    root.mkdir(parents=True)
    return ws_id, root / "upload.bin"


def create_from_upload(
    db: Session, owner: User, ws_id: str, filename: str, upload: Path
) -> Workspace:
    """Scan an already-streamed upload into a new workspace (runs in a worker thread)."""
    settings = get_settings()
    ws = Workspace(id=ws_id, owner_id=owner.id, name=PurePosixPath(filename).name[:255])
    root = workspace_dir(ws.id)
    try:
        ws.upload_bytes = upload.stat().st_size
        result = scan_upload(
            upload,
            filename,
            sources_dir(ws.id),
            Limits(
                max_files=settings.max_scan_files,
                max_bytes=settings.max_unzipped_mb * 1024 * 1024,
                max_depth=settings.max_zip_depth,
                max_ratio=settings.max_compression_ratio,
            ),
        )
    except ValueError as exc:
        shutil.rmtree(root, ignore_errors=True)
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    except BaseException:
        shutil.rmtree(root, ignore_errors=True)
        raise
    finally:
        upload.unlink(missing_ok=True)

    ws.scan_notes = result.notes
    ws.sources = [
        SourceFile(
            logical_path=f.logical_path,
            filename=f.filename,
            group=f.group,
            file_type=f.file_type,
            size=f.size,
            stored_name=f.stored_name,
        )
        for f in result.files
    ]
    db.add(ws)
    db.commit()
    log.info(
        "workspace %s scanned: %d files, %d bytes", ws.id, len(result.files), result.bytes_written
    )
    return ws


def group_summaries(ws: Workspace) -> list[GroupSummary]:
    files: dict[str, int] = defaultdict(int)
    size: dict[str, int] = defaultdict(int)
    for s in ws.sources:
        files[s.group] += 1
        size[s.group] += s.size
    out = []
    for code in sorted(files):
        info = lookup(code)
        out.append(
            GroupSummary(
                code=code,
                module=info.name if info else None,
                domain=info.domain if info else None,
                files=files[code],
                bytes=size[code],
            )
        )
    return out


def delete_workspace(db: Session, ws: Workspace) -> None:
    search.drop_workspace(db, ws.id)
    db.delete(ws)
    db.commit()
    shutil.rmtree(workspace_dir(ws.id), ignore_errors=True)


# --- conversion ------------------------------------------------------------------------------


def dataset_name(logical_path: str, used: set[str]) -> str:
    """``…/AR_TERMS.xml`` → ``AR_TERMS.CSV``; deterministic ``__SHA8`` suffix on collision."""
    stem = PurePosixPath(logical_path).name
    for suffix in (".gz", ".xml", ".csv", ".xlsx"):
        if stem.lower().endswith(suffix):
            stem = stem[: -len(suffix)]
    stem = _SPACES.sub(" ", _NAME_UNSAFE.sub("_", stem)).strip()[:160] or "FILE"
    name = f"{stem}.CSV".upper()
    if name in used:
        sha = hashlib.sha1(logical_path.encode(), usedforsecurity=False).hexdigest()[:8]
        name = f"{stem}__{sha}.CSV".upper()
    used.add(name)
    return name


def base_name(name: str) -> str:
    """Dataset name without the collision suffix — used to pair datasets across uploads."""
    return re.sub(r"__[0-9A-F]{8}(?=\.CSV$)", "", name.upper())


def start_conversion(db: Session, user: User, ws: Workspace, groups: list[str] | None) -> str:
    if ws.status == "converting":
        raise HTTPException(status.HTTP_409_CONFLICT, "Conversion already in progress.")
    ws.status = "converting"
    db.commit()
    job = jobs.create_job(user.id, "convert", ws.id)
    wanted = {g.upper() for g in groups} if groups else None
    jobs.submit(job.id, lambda job_id: _convert(job_id, ws.id, wanted))
    return job.id


def _convert(job_id: str, workspace_id: str, groups: set[str] | None) -> str:
    settings = get_settings()
    with new_session() as db:
        ws = db.get(Workspace, workspace_id)
        if ws is None:
            raise RuntimeError("Workspace was deleted.")
        try:
            sources = [
                s for s in ws.sources if not s.excluded and (groups is None or s.group in groups)
            ]
            # Re-conversion replaces previous output (and invalidates the AI index).
            search.drop_workspace(db, ws.id)
            db.execute(delete(Dataset).where(Dataset.workspace_id == ws.id))
            ws.indexed_rows, ws.indexed_at = 0, None
            out_dir = datasets_dir(ws.id)
            shutil.rmtree(out_dir, ignore_errors=True)
            out_dir.mkdir(parents=True)
            db.commit()

            used: set[str] = set()
            plan = [(s, dataset_name(s.logical_path, used), f"{new_id()}.csv") for s in sources]
            src_dir = sources_dir(ws.id)
            failures: list[str] = []
            done = 0
            jobs.report_progress(job_id, 0, len(plan))

            def record(src: SourceFile, name: str, stored: str, stats: TableStats) -> None:
                db.add(
                    Dataset(
                        workspace_id=ws.id,
                        source_id=src.id,
                        name=name,
                        group=src.group,
                        logical_path=src.logical_path,
                        record_tag=stats.record_tag,
                        rows=stats.rows,
                        columns=stats.columns,
                        sha256=stats.sha256,
                        stored_name=stored,
                    )
                )

            args = [
                (s.file_type, src_dir / s.stored_name, out_dir / stored, settings.max_field_chars)
                for s, _, stored in plan
            ]
            if len(plan) <= INLINE_CONVERT_MAX_FILES:
                for (src, name, stored), a in zip(plan, args, strict=True):
                    try:
                        record(src, name, stored, to_csv(*a))
                    except Exception as exc:  # per-file isolation: one bad file ≠ failed job
                        failures.append(f"{src.logical_path}: {exc}")
                    done += 1
                jobs.report_progress(job_id, done, len(plan))
            else:
                workers = settings.conversion_workers or os.cpu_count() or 2
                ctx = multiprocessing.get_context("spawn")
                with ProcessPoolExecutor(
                    max_workers=min(workers, len(plan)), mp_context=ctx
                ) as pool:
                    futures: dict[Future[TableStats], tuple[SourceFile, str, str]] = {
                        pool.submit(to_csv, *a): p for p, a in zip(plan, args, strict=True)
                    }
                    for fut in as_completed(futures):
                        src, name, stored = futures[fut]
                        try:
                            record(src, name, stored, fut.result())
                        except Exception as exc:  # per-file isolation
                            failures.append(f"{src.logical_path}: {exc}")
                        done += 1
                        if done % 25 == 0 or done == len(plan):
                            db.commit()
                            jobs.report_progress(job_id, done, len(plan))

            ws.status = "converted"
            ws.scan_notes = [n for n in ws.scan_notes if not n.startswith("Conversion failed")] + [
                f"Conversion failed for {f}"[:500] for f in failures[:50]
            ]
            db.commit()
        except BaseException:
            db.rollback()
            ws.status = "failed"
            db.commit()
            raise
        ok = len(plan) - len(failures)
        return f"Converted {ok} of {len(plan)} files" + (
            f"; {len(failures)} failed." if failures else "."
        )


def set_exclusions(db: Session, ws: Workspace, source_ids: list[str], excluded: bool) -> int:
    ids = sorted(set(source_ids))
    changed = 0
    # Chunked to stay under SQLite's bound-parameter limit.
    for i in range(0, len(ids), 500):
        rows = db.scalars(
            select(SourceFile).where(
                SourceFile.workspace_id == ws.id, SourceFile.id.in_(ids[i : i + 500])
            )
        ).all()
        for s in rows:
            s.excluded = excluded
        changed += len(rows)
    db.commit()
    return changed
