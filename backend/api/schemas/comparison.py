from pydantic import BaseModel
from typing import List, Dict, Optional, Any


class ComparisonRequest(BaseModel):
    left_session_id: str
    right_session_id: str


class ComparisonOptions(BaseModel):
    ignore_case: bool = False
    trim_whitespace: bool = True
    similarity_pairing: bool = True
    sim_threshold: float = 0.65


class FileMatch(BaseModel):
    filename: str
    similarity: float


class DeltaRow(BaseModel):
    row_id: int
    change_type: str  # added / removed / modified
    before: Optional[Dict] = None
    after: Optional[Dict] = None


class CellChange(BaseModel):
    """Represents a change in a specific cell"""
    col_index: int
    col_name: str
    old_value: str
    new_value: str
    indicator: str  # 🟢 for unchanged, 🔴 for changed


class RowDelta(BaseModel):
    """Represents a row-level change with cell-level details"""
    kind: str  # MODIFIED, ADDED, REMOVED
    row_a: Optional[int] = None
    row_b: Optional[int] = None
    changed_cols: List[int] = []
    old_vals: Dict[int, str] = {}
    new_vals: Dict[int, str] = {}


class FileComparisonDetail(BaseModel):
    """Detailed comparison result for a single file pair"""
    group: str
    filename: str
    status: str  # SAME, MODIFIED, ADDED, REMOVED
    similarity: float
    rows_a: int = 0
    rows_b: int = 0
    cols_a: int = 0
    cols_b: int = 0
    sha_a: str = ""
    sha_b: str = ""
    path_a: str = ""
    path_b: str = ""
    message: str = ""


class DeltaFrame(BaseModel):
    """Side-by-side delta data for drilldown"""
    headers: List[str] = []
    rows: List[Dict[str, Any]] = []


class DrilldownResult(BaseModel):
    """Drilldown comparison result for a specific file pair"""
    filename: str
    group: str
    header: List[str] = []
    stats: Dict[str, int] = {}
    truncated: bool = False
    delta_a: DeltaFrame
    delta_b: DeltaFrame
    row_count_a: int = 0
    row_count_b: int = 0
    col_count: int = 0


class ComparisonSummary(BaseModel):
    total_files: int = 0
    matched_files: int = 0
    same: int = 0
    modified: int = 0
    added: int = 0
    removed: int = 0
    overall_similarity: float = 0.0


class FolderChange(BaseModel):
    folder: str
    count_a: int
    count_b: int
    delta: int


class GroupChange(BaseModel):
    group: str
    count_a: int
    count_b: int
    delta: int


class ZipComparisonResponse(BaseModel):
    """Full comparison response for ZIP files"""
    summary: ComparisonSummary
    files: List[FileComparisonDetail] = []
    folder_changes: List[FolderChange] = []
    group_changes: List[GroupChange] = []
    info_a: Dict[str, Any] = {}
    info_b: Dict[str, Any] = {}


class FileComparisonResult(BaseModel):
    filename: str
    similarity: float
    deltas: List[DeltaRow]


class ComparisonResponse(BaseModel):
    summary: ComparisonSummary
    results: List[FileComparisonResult] = []
    # Extended fields for ZIP comparison
    similarity: float = 0.0
    same: int = 0
    modified: int = 0
    added: int = 0
    removed: int = 0
    total_changes: int = 0
    changes: List[Dict[str, Any]] = []
    folder_changes: List[Dict[str, Any]] = []
    group_deltas: List[Dict[str, Any]] = []
