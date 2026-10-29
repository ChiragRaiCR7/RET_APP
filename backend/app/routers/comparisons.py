from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from app.models import Comparison, ComparisonItem, Dataset
from app.schemas import (
    CompareIn,
    ComparisonDetail,
    ComparisonItemOut,
    ComparisonOut,
    DiffOut,
    JobOut,
    Message,
)
from app.security import DB, CurrentUser, audit
from app.services import comparison, jobs
from app.services.workspaces import dataset_path, get_owned

router = APIRouter(prefix="/comparisons", tags=["comparisons"])


def _owned(db: DB, user: CurrentUser, comparison_id: str) -> Comparison:
    cmp = db.get(Comparison, comparison_id)
    if cmp is None or cmp.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Comparison not found.")
    return cmp


@router.get("", response_model=list[ComparisonOut])
def list_comparisons(user: CurrentUser, db: DB) -> list[Comparison]:
    return list(
        db.scalars(
            select(Comparison)
            .where(Comparison.owner_id == user.id)
            .order_by(Comparison.created_at.desc())
        )
    )


@router.post("", response_model=JobOut, status_code=202)
def start(body: CompareIn, request: Request, user: CurrentUser, db: DB) -> JobOut:
    left = get_owned(db, user, body.left_workspace_id)
    right = get_owned(db, user, body.right_workspace_id)
    if left.id == right.id:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Choose two different workspaces."
        )
    for ws in (left, right):
        if ws.status != "converted":
            raise HTTPException(status.HTTP_409_CONFLICT, f"Convert “{ws.name}” first.")
    cmp = Comparison(
        owner_id=user.id,
        left_workspace_id=left.id,
        right_workspace_id=right.id,
        options=body.model_dump(exclude={"left_workspace_id", "right_workspace_id"}),
    )
    db.add(cmp)
    audit(db, request, "comparison.started", target=cmp.id, left=left.id, right=right.id)
    db.commit()
    job = jobs.create_job(user.id, "compare", cmp.id)
    jobs.submit(job.id, lambda job_id: comparison.run(job_id, cmp.id))
    fresh = db.get(type(job), job.id)
    assert fresh is not None
    db.refresh(fresh)
    return JobOut.model_validate(fresh)


@router.get("/{comparison_id}", response_model=ComparisonDetail)
def get_comparison(comparison_id: str, user: CurrentUser, db: DB) -> ComparisonDetail:
    cmp = _owned(db, user, comparison_id)
    names = {
        ws_id: get_owned(db, user, ws_id).name
        for ws_id in (cmp.left_workspace_id, cmp.right_workspace_id)
    }
    return ComparisonDetail.model_validate(
        {
            **ComparisonOut.model_validate(cmp).model_dump(),
            "items": [ComparisonItemOut.model_validate(i) for i in cmp.items],
            "left_name": names[cmp.left_workspace_id],
            "right_name": names[cmp.right_workspace_id],
        }
    )


@router.delete("/{comparison_id}", response_model=Message)
def delete_comparison(comparison_id: str, user: CurrentUser, db: DB) -> Message:
    db.delete(_owned(db, user, comparison_id))
    db.commit()
    return Message(message="Comparison deleted.")


@router.get("/{comparison_id}/items/{item_id}/diff", response_model=DiffOut)
def item_diff(comparison_id: str, item_id: int, user: CurrentUser, db: DB) -> DiffOut:
    cmp = _owned(db, user, comparison_id)
    item = db.get(ComparisonItem, item_id)
    if item is None or item.comparison_id != cmp.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Item not found.")
    left = db.get(Dataset, item.left_dataset_id) if item.left_dataset_id else None
    right = db.get(Dataset, item.right_dataset_id) if item.right_dataset_id else None
    if left is None and right is None:
        raise HTTPException(status.HTTP_410_GONE, "Both datasets were deleted since.")
    opts = comparison.Options.from_stored(cmp.options)
    return comparison.diff_to_api(
        comparison.diff_tables(
            dataset_path(left) if left else None, dataset_path(right) if right else None, opts
        )
    )
