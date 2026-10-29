import shutil
from pathlib import Path, PurePosixPath
from urllib.parse import quote

import anyio
from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, Response, StreamingResponse
from sqlalchemy import delete, select
from starlette.background import BackgroundTask

from app.config import get_settings
from app.models import ChatMessage, Dataset, Job, Workspace, new_id
from app.schemas import (
    AIStatus,
    ChatIn,
    ChatMessageOut,
    ConvertIn,
    DatasetOut,
    DatasetPage,
    EditIn,
    ExclusionsIn,
    ExportFormat,
    ExportIn,
    JobOut,
    Message,
    StructureOut,
    WorkspaceDetail,
    WorkspaceOut,
)
from app.security import DB, CurrentUser, audit
from app.services import assistant, datasets, jobs, search, structure
from app.services import workspaces as svc

router = APIRouter(tags=["workspaces"])


def _attachment(name: str) -> dict[str, str]:
    return {"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"}


def _detail(ws: Workspace) -> WorkspaceDetail:
    job = jobs.active_job("convert", ws.id)
    return WorkspaceDetail.model_validate(
        {
            **WorkspaceOut.model_validate(ws).model_dump(),
            "sources": ws.sources,
            "datasets": ws.datasets,
            "groups": svc.group_summaries(ws),
            "active_job": job,
        }
    )


@router.get("/workspaces", response_model=list[WorkspaceOut])
def list_workspaces(user: CurrentUser, db: DB) -> list[Workspace]:
    return list(
        db.scalars(
            select(Workspace)
            .where(Workspace.owner_id == user.id)
            .order_by(Workspace.created_at.desc())
        )
    )


@router.post(
    "/workspaces",
    response_model=WorkspaceDetail,
    status_code=201,
    openapi_extra={
        "requestBody": {
            "content": {
                "application/octet-stream": {"schema": {"type": "string", "format": "binary"}}
            },
            "required": True,
        }
    },
)
async def upload(
    request: Request, user: CurrentUser, db: DB, filename: str = Query(min_length=1, max_length=255)
) -> WorkspaceDetail:
    """Upload a .zip/.xml/.xml.gz/.csv/.xlsx as the raw request body.

    Raw-body upload (not multipart) lets the size limit apply while bytes stream in,
    instead of after the whole request has been spooled to disk.
    """
    limit = get_settings().max_upload_mb * 1024 * 1024
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE, f"Upload exceeds {get_settings().max_upload_mb} MB."
        )
    ws_id, dest = await run_in_threadpool(svc.new_workspace_dir)
    written = 0
    try:
        async with await anyio.open_file(dest, "wb") as out:
            async for chunk in request.stream():
                written += len(chunk)
                if written > limit:
                    raise HTTPException(
                        status.HTTP_413_CONTENT_TOO_LARGE,
                        f"Upload exceeds {get_settings().max_upload_mb} MB.",
                    )
                await out.write(chunk)
        if written == 0:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "The file is empty.")
    except BaseException:
        shutil.rmtree(svc.workspace_dir(ws_id), ignore_errors=True)
        raise
    name = PurePosixPath(filename.replace("\\", "/")).name
    ws = await run_in_threadpool(svc.create_from_upload, db, user, ws_id, name, dest)
    audit(
        db,
        request,
        "workspace.created",
        target=ws.id,
        name=ws.name,
        bytes=written,
        files=len(ws.sources),
    )
    db.commit()
    return _detail(ws)


@router.get("/workspaces/{workspace_id}", response_model=WorkspaceDetail)
def get_workspace(workspace_id: str, user: CurrentUser, db: DB) -> WorkspaceDetail:
    return _detail(svc.get_owned(db, user, workspace_id))


@router.delete("/workspaces/{workspace_id}", response_model=Message)
def delete_workspace(workspace_id: str, request: Request, user: CurrentUser, db: DB) -> Message:
    ws = svc.get_owned(db, user, workspace_id)
    if ws.status == "converting":
        raise HTTPException(status.HTTP_409_CONFLICT, "Wait for the conversion to finish.")
    svc.delete_workspace(db, ws)
    audit(db, request, "workspace.deleted", target=workspace_id, name=ws.name)
    db.commit()
    return Message(message="Workspace deleted.")


@router.post("/workspaces/{workspace_id}/exclusions", response_model=Message)
def set_exclusions(workspace_id: str, body: ExclusionsIn, user: CurrentUser, db: DB) -> Message:
    ws = svc.get_owned(db, user, workspace_id)
    n = svc.set_exclusions(db, ws, body.source_ids, body.excluded)
    return Message(message=f"{n} files {'excluded' if body.excluded else 'included'}.")


@router.post("/workspaces/{workspace_id}/convert", response_model=JobOut, status_code=202)
def convert(workspace_id: str, body: ConvertIn, request: Request, user: CurrentUser, db: DB) -> Job:
    ws = svc.get_owned(db, user, workspace_id)
    job_id = svc.start_conversion(db, user, ws, body.groups)
    audit(db, request, "workspace.convert", target=ws.id, groups=body.groups)
    db.commit()
    job = db.get(Job, job_id)
    assert job is not None
    db.refresh(job)
    return job


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: str, user: CurrentUser, db: DB) -> Job:
    job = db.get(Job, job_id)
    if job is None or job.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found.")
    return job


@router.get("/workspaces/{workspace_id}/structure", response_model=StructureOut)
def business_structure(
    workspace_id: str,
    user: CurrentUser,
    db: DB,
    business_group: str | None = Query(None, max_length=120),
) -> StructureOut:
    return structure.build(svc.get_owned(db, user, workspace_id), business_group)


@router.post("/workspaces/{workspace_id}/export")
def export(workspace_id: str, body: ExportIn, user: CurrentUser, db: DB) -> FileResponse:
    ws = svc.get_owned(db, user, workspace_id)
    chosen = [d for d in ws.datasets if body.dataset_ids is None or d.id in set(body.dataset_ids)]
    if not chosen:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "No datasets to export.")
    tmp = svc.workspace_dir(ws.id) / f"export-{new_id()}.zip"
    datasets.export_zip(chosen, body.format, body.preserve_structure, tmp)
    stem = PurePosixPath(ws.name).stem or "export"
    return FileResponse(
        tmp,
        media_type="application/zip",
        headers=_attachment(f"{stem}_{body.format}.zip"),
        background=BackgroundTask(tmp.unlink, missing_ok=True),
    )


# --- datasets --------------------------------------------------------------------------------


@router.get("/datasets/{dataset_id}", response_model=DatasetPage)
def read_dataset(
    dataset_id: str,
    user: CurrentUser,
    db: DB,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    q: str | None = Query(None, max_length=200),
) -> DatasetPage:
    ds = svc.get_owned_dataset(db, user, dataset_id)
    header, rows, total = datasets.page(ds, offset, limit, q or None)
    cols = datasets.profile_columns(ds)
    if len(cols) != len(header):  # header changed by an edit between calls; trust the file
        cols = cols[: len(header)]
    return DatasetPage(
        dataset=DatasetOut.model_validate(ds), columns=cols, rows=rows, offset=offset, total=total
    )


@router.patch("/datasets/{dataset_id}", response_model=DatasetOut)
def edit_dataset(
    dataset_id: str, body: EditIn, request: Request, user: CurrentUser, db: DB
) -> Dataset:
    ds = svc.get_owned_dataset(db, user, dataset_id)
    datasets.apply_edits(db, ds, body)
    audit(
        db,
        request,
        "dataset.edited",
        target=ds.id,
        name=ds.name,
        cells=len(body.cells),
        appended=len(body.append_rows),
        deleted=len(body.delete_rows),
    )
    db.commit()
    return ds


@router.delete("/datasets/{dataset_id}", response_model=Message)
def delete_dataset(dataset_id: str, request: Request, user: CurrentUser, db: DB) -> Message:
    ds = svc.get_owned_dataset(db, user, dataset_id)
    path = svc.dataset_path(ds)
    search.drop_dataset(db, ds)
    db.delete(ds)
    audit(db, request, "dataset.deleted", target=dataset_id, name=ds.name)
    db.commit()
    path.unlink(missing_ok=True)
    return Message(message=f"Deleted {ds.name}.")


@router.get("/datasets/{dataset_id}/download")
def download_dataset(
    dataset_id: str, user: CurrentUser, db: DB, format: ExportFormat = "csv"
) -> Response:
    ds = svc.get_owned_dataset(db, user, dataset_id)
    payload, name, media = datasets.export_one(ds, format)
    if isinstance(payload, Path):
        return FileResponse(payload, media_type=media, headers=_attachment(name))
    return Response(payload, media_type=media, headers=_attachment(name))


# --- AI ------------------------------------------------------------------------------------


@router.get("/workspaces/{workspace_id}/ai", response_model=AIStatus)
def ai_status(workspace_id: str, user: CurrentUser, db: DB) -> AIStatus:
    ws = svc.get_owned(db, user, workspace_id)
    s = get_settings()
    job = jobs.active_job("index", ws.id)
    return AIStatus(
        llm_configured=s.llm_configured,
        model=s.azure_openai_chat_model,
        indexed_rows=ws.indexed_rows,
        indexed_at=ws.indexed_at,
        index_job=JobOut.model_validate(job) if job else None,
    )


@router.post("/workspaces/{workspace_id}/ai/index", response_model=JobOut, status_code=202)
def build_index(workspace_id: str, request: Request, user: CurrentUser, db: DB) -> Job:
    ws = svc.get_owned(db, user, workspace_id)
    if not ws.datasets:
        raise HTTPException(status.HTTP_409_CONFLICT, "Convert the workspace before indexing.")
    if jobs.active_job("index", ws.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "Indexing already in progress.")
    job = jobs.create_job(user.id, "index", ws.id)
    jobs.submit(job.id, lambda job_id: search.build_index(job_id, ws.id))
    audit(db, request, "workspace.index", target=ws.id)
    db.commit()
    fresh = db.get(Job, job.id)
    assert fresh is not None
    db.refresh(fresh)
    return fresh


@router.get("/workspaces/{workspace_id}/ai/messages", response_model=list[ChatMessageOut])
def chat_history(workspace_id: str, user: CurrentUser, db: DB) -> list[ChatMessage]:
    ws = svc.get_owned(db, user, workspace_id)
    return list(
        db.scalars(
            select(ChatMessage).where(ChatMessage.workspace_id == ws.id).order_by(ChatMessage.id)
        )
    )


@router.delete("/workspaces/{workspace_id}/ai/messages", response_model=Message)
def clear_chat(workspace_id: str, user: CurrentUser, db: DB) -> Message:
    ws = svc.get_owned(db, user, workspace_id)
    db.execute(delete(ChatMessage).where(ChatMessage.workspace_id == ws.id))
    db.commit()
    return Message(message="Conversation cleared.")


@router.post("/workspaces/{workspace_id}/ai/chat")
def chat(workspace_id: str, body: ChatIn, user: CurrentUser, db: DB) -> StreamingResponse:
    """Server-sent events: ``citations``, ``token``…, then ``done`` or ``error``."""
    ws = svc.get_owned(db, user, workspace_id)
    if ws.indexed_at is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Build the search index first.")
    return StreamingResponse(
        assistant.answer_stream(ws.id, body.question.strip()),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/workspaces/{workspace_id}/ai/transcript")
def transcript(workspace_id: str, user: CurrentUser, db: DB) -> Response:
    ws = svc.get_owned(db, user, workspace_id)
    lines = [f"# Conversation — {ws.name}", ""]
    for m in db.scalars(
        select(ChatMessage).where(ChatMessage.workspace_id == ws.id).order_by(ChatMessage.id)
    ):
        lines += [
            f"## {'You' if m.role == 'user' else 'Assistant'} · {m.created_at:%Y-%m-%d %H:%M} UTC",
            "",
            m.content,
            "",
        ]
        for c in m.citations:
            lines.append(f"- [{c['n']}] {c['dataset']} row {c['row'] + 1}")
        lines.append("")
    stem = PurePosixPath(ws.name).stem or "workspace"
    return Response(
        "\n".join(lines),
        media_type="text/markdown; charset=utf-8",
        headers=_attachment(f"{stem}_conversation.md"),
    )
