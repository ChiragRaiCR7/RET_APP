from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import zipfile, uuid, asyncio, io, shutil, time
from typing import Dict, List, Optional
from datetime import datetime

from app.zip_scanner import scan_zip_for_xml, XmlEntry
from app.xml_convert_parallel import convert_inventory_parallel
from app.models import (
    SessionInfo, ScanProgress, ConversionProgress,
    GroupInfo, FileInfo
)
from app.utils import infer_group

app = FastAPI(title="XML Archive Converter Pro")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

SESSIONS: Dict[str, SessionInfo] = {}
OUTPUT_DIR = Path("./outputs")
OUTPUT_DIR.mkdir(exist_ok=True)


@app.post("/api/scan")
async def scan_archive(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    custom_prefixes: str = ""
):
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(400, "Only ZIP files supported")

    session_id = str(uuid.uuid4())
    session_dir = OUTPUT_DIR / session_id
    session_dir.mkdir(parents=True)

    zip_path = session_dir / file.filename
    zip_path.write_bytes(await file.read())

    prefixes = {p.strip().upper() for p in custom_prefixes.split(",") if p.strip()}

    SESSIONS[session_id] = SessionInfo(
        session_id=session_id,
        zip_path=zip_path,
        session_dir=session_dir,
        custom_prefixes=prefixes,
        created_at=datetime.now()
    )

    background_tasks.add_task(scan_background, session_id)
    return {"session_id": session_id, "status": "scanning_started"}


async def scan_background(session_id: str):
    session = SESSIONS[session_id]
    work_dir = session.session_dir / "extracted"
    work_dir.mkdir(exist_ok=True)

    try:
        session.scan_progress.status = "scanning"

        entries = scan_zip_for_xml(
            session.zip_path,
            work_dir,
            progress_callback=lambda d, t, f: update_scan_progress(
                session_id, d, t, f
            )
        )

        session.xml_inventory = entries
        session.groups = group_xml_files(entries, session.custom_prefixes)

        session.scan_progress.status = "completed"
        session.scan_progress.xml_found = len(entries)
        session.scan_progress.groups_detected = len(session.groups)

    except Exception as e:
        session.scan_progress.status = "error"
        session.scan_progress.error = str(e)


def update_scan_progress(session_id: str, done: int, total: int, found: int):
    p = SESSIONS[session_id].scan_progress
    p.entries_done = done
    p.entries_total = total
    p.xml_found = found
    p.progress = int((done / max(total, 1)) * 100)


def group_xml_files(entries: List[XmlEntry], prefixes: set) -> List[GroupInfo]:
    from collections import Counter

    counts = Counter()
    sizes = {}

    for e in entries:
        g = infer_group(e.logical_path, prefixes)
        counts[g] += 1
        sizes[g] = sizes.get(g, 0) + e.size

    return [
        GroupInfo(name=g, count=c, size_mb=round(sizes[g] / (1024 * 1024), 2))
        for g, c in counts.items()
    ]


@app.post("/api/convert")
async def start_conversion(
    background_tasks: BackgroundTasks,
    session_id: str,
    selected_groups: Optional[List[str]] = None
):
    session = SESSIONS.get(session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    inventory = session.xml_inventory
    if selected_groups:
        inventory = [
            e for e in inventory
            if infer_group(e.logical_path, session.custom_prefixes) in selected_groups
        ]

    session.conversion_progress = ConversionProgress(
        status="converting",
        files_total=len(inventory)
    )

    background_tasks.add_task(convert_background, session_id, inventory)
    return {"status": "conversion_started", "files": len(inventory)}


async def convert_background(session_id: str, inventory: List[XmlEntry]):
    session = SESSIONS[session_id]
    out_dir = session.session_dir / "csv_outputs"
    out_dir.mkdir(exist_ok=True)

    start = time.time()
    total_mb = sum(e.size for e in inventory) / (1024 * 1024)

    results = convert_inventory_parallel(
        inventory,
        out_dir,
        session.custom_prefixes,
        progress_callback=lambda d, t: update_conversion_progress(
            session_id, d, t, start, total_mb
        )
    )

    p = session.conversion_progress
    p.status = "completed"
    p.files_done = len(results)
    p.successful = sum(r["success"] for r in results)
    p.errors = p.files_done - p.successful
    session.conversion_results = results


def update_conversion_progress(session_id: str, done: int, total: int, start: float, total_mb: float):
    p = SESSIONS[session_id].conversion_progress
    elapsed = time.time() - start

    p.files_done = done
    p.progress = int((done / max(total, 1)) * 100)

    if elapsed > 0 and done > 0:
        p.mb_per_sec = round((done / total * total_mb) / elapsed, 2)
        p.eta_min = round(((total - done) / done * elapsed) / 60, 1)
