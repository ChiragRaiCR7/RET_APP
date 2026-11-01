"""API request/response contracts. The frontend's TypeScript types are generated from these."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Role = Literal["user", "admin"]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- auth -----------------------------------------------------------------------------------


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class UserOut(ORM):
    id: int
    username: str
    role: Role
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None
    locked_until: datetime | None


class ResetRequestIn(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    reason: str | None = Field(default=None, max_length=500)


class ResetConfirmIn(BaseModel):
    token: str = Field(min_length=16, max_length=128)
    new_password: str = Field(min_length=1, max_length=256)


class ChangePasswordIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


class Message(BaseModel):
    message: str


# --- admin ----------------------------------------------------------------------------------


class UserCreateIn(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.\-]+$")
    password: str = Field(min_length=1, max_length=256)
    role: Role = "user"


class UserUpdateIn(BaseModel):
    role: Role | None = None
    is_active: bool | None = None


class ResetTokenOut(BaseModel):
    token: str
    expires_at: datetime


class ResetRequestOut(ORM):
    id: int
    username: str
    reason: str | None
    status: str
    created_at: datetime


class AuditEventOut(ORM):
    id: int
    actor: str | None
    action: str
    target: str | None
    details: dict[str, object] | None
    created_at: datetime


class AdminStats(BaseModel):
    users: int
    active_sessions: int
    workspaces: int
    datasets: int
    disk_bytes: int
    llm_configured: bool


# --- workspaces & datasets ------------------------------------------------------------------


class SourceFileOut(ORM):
    id: str
    logical_path: str
    filename: str
    group: str
    file_type: str
    size: int
    excluded: bool


class GroupSummary(BaseModel):
    code: str
    module: str | None
    domain: str | None
    files: int
    bytes: int


class DatasetOut(ORM):
    id: str
    name: str
    group: str
    logical_path: str
    record_tag: str | None
    rows: int
    columns: int
    edited: bool


class JobOut(ORM):
    id: str
    kind: str
    subject_id: str
    status: Literal["queued", "running", "succeeded", "failed"]
    progress: int
    total: int
    message: str
    created_at: datetime
    finished_at: datetime | None


class WorkspaceOut(ORM):
    id: str
    name: str
    status: Literal["scanned", "converting", "converted", "failed"]
    upload_bytes: int
    scan_notes: list[str]
    indexed_rows: int
    indexed_at: datetime | None
    created_at: datetime


class WorkspaceDetail(WorkspaceOut):
    sources: list[SourceFileOut]
    datasets: list[DatasetOut]
    groups: list[GroupSummary]
    active_job: JobOut | None


class ExclusionsIn(BaseModel):
    source_ids: list[str] = Field(max_length=100_000)
    excluded: bool


class ConvertIn(BaseModel):
    groups: list[str] | None = Field(
        default=None, description="Restrict conversion to these group codes; null = all."
    )


ColumnKind = Literal["key", "value", "low"]


class ColumnInfo(BaseModel):
    name: str
    kind: ColumnKind
    reason: str | None = None


class DatasetPage(BaseModel):
    dataset: DatasetOut
    columns: list[ColumnInfo]
    rows: list[list[str]]
    offset: int
    total: int


class CellEdit(BaseModel):
    row: int = Field(ge=0)
    column: str = Field(min_length=1, max_length=512)
    value: str = Field(max_length=32_768)


class EditIn(BaseModel):
    cells: list[CellEdit] = Field(default_factory=list, max_length=10_000)
    append_rows: list[dict[str, str]] = Field(default_factory=list, max_length=1_000)
    delete_rows: list[int] = Field(default_factory=list, max_length=10_000)


ExportFormat = Literal["csv", "xlsx"]


class ExportIn(BaseModel):
    format: ExportFormat = "csv"
    dataset_ids: list[str] | None = None
    preserve_structure: bool = False


# --- business structure ---------------------------------------------------------------------

NodeType = Literal["business_group", "ledger", "legal_entity", "operating_unit", "inventory_org"]


class StructureNode(BaseModel):
    name: str
    type: NodeType
    children: list["StructureNode"] = Field(default_factory=list)


class StructureOut(BaseModel):
    status: Literal["ready", "missing_files", "no_data"]
    root: StructureNode | None
    sources: list[str]
    diagnostics: list[str]
    counts: dict[NodeType, int]


# --- comparison -----------------------------------------------------------------------------


class CompareIn(BaseModel):
    left_workspace_id: str
    right_workspace_id: str
    ignore_case: bool = False
    trim_whitespace: bool = True
    ignore_columns: list[str] = Field(
        default_factory=lambda: [
            "CreatedBy",
            "CreationDate",
            "LastUpdatedBy",
            "LastUpdateDate",
            "LastUpdateLogin",
        ],
        max_length=200,
    )


class ComparisonItemOut(ORM):
    id: int
    group: str
    name: str
    status: Literal["SAME", "MODIFIED", "ADDED", "REMOVED"]
    left_dataset_id: str | None
    right_dataset_id: str | None
    rows_left: int
    rows_right: int
    added: int
    removed: int
    modified: int


class ComparisonOut(ORM):
    id: str
    left_workspace_id: str
    right_workspace_id: str
    status: str
    summary: dict[str, int]
    options: dict[str, object]
    created_at: datetime


class ComparisonDetail(ComparisonOut):
    items: list[ComparisonItemOut]
    left_name: str
    right_name: str


class DiffRow(BaseModel):
    kind: Literal["ADDED", "REMOVED", "MODIFIED"]
    left_row: int | None
    right_row: int | None
    left: list[str] | None
    right: list[str] | None
    changed: list[int]


class DiffOut(BaseModel):
    header: list[str]
    ignored: list[int]
    rows: list[DiffRow]
    stats: dict[str, int]
    truncated: bool


# --- AI ------------------------------------------------------------------------------------


class AIStatus(BaseModel):
    llm_configured: bool
    model: str | None
    indexed_rows: int
    indexed_at: datetime | None
    index_job: JobOut | None


class Citation(BaseModel):
    n: int
    dataset_id: str
    dataset: str
    group: str
    row: int
    snippet: str


class ChatIn(BaseModel):
    question: str = Field(min_length=1, max_length=4_000)


class ChatMessageOut(ORM):
    id: int
    role: Literal["user", "assistant"]
    content: str
    citations: list[Citation]
    mode: str | None
    created_at: datetime


StructureNode.model_rebuild()
