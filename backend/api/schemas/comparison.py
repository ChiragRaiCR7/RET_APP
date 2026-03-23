


from __future__ import annotations

from typing import Annotated, Any, Dict, List, Optional, Literal

from pydantic import BaseModel, ConfigDict, Field


NonNegativeInt = Annotated[int, Field(ge=0)]
UnitFloat = Annotated[float, Field(ge=0.0, le=1.0)]
PercentFloat = Annotated[float, Field(ge=0.0, le=100.0)]


# ============================================================
# Requests / Options
# ============================================================

class ComparisonRequest(BaseModel):
    """
    Used for async session-to-session comparison (/comparison/compare).
    """
    left_session_id: str = Field(..., min_length=1, description="Left session id")
    right_session_id: str = Field(..., min_length=1, description="Right session id")


class ComparisonOptions(BaseModel):
    """
    Options accepted by /comparison/run and /comparison/drilldown.
    """
    ignore_case: bool = Field(False, description="Ignore case while comparing values")
    trim_whitespace: bool = Field(True, description="Trim whitespace from values")
    similarity_pairing: bool = Field(True, description="Use similarity pairing for row matching")
    sim_threshold: UnitFloat = Field(0.65, description="Similarity threshold [0.0, 1.0]")
    ignore_columns: Optional[str] = Field(
        None,
        description="Comma-separated columns to ignore during diff (WHO columns etc.)",
    )


# ============================================================
# Common / Small Models
# ============================================================

class FileMatch(BaseModel):
    filename: str = Field(..., min_length=1)
    similarity: UnitFloat = Field(...)


# Older / generic delta row model (kept)
class DeltaRow(BaseModel):
    row_id: NonNegativeInt = Field(..., description="Row index/id")
    change_type: Literal["added", "removed", "modified"] = Field(..., description="Row change type")
    before: Optional[Dict[str, Any]] = Field(None)
    after: Optional[Dict[str, Any]] = Field(None)


class CellChange(BaseModel):
    """
    Represents a change in a specific cell.
    (Some UI clients may still use this; leaving it for compatibility.)
    """
    col_index: NonNegativeInt = Field(..., description="Column index")
    col_name: str = Field("", description="Column name")
    old_value: str = Field("", description="Old cell value")
    new_value: str = Field("", description="New cell value")
    indicator: str = Field("", description="Indicator icon/text e.g. 🟢 or 🔴")


class RowDelta(BaseModel):
    """
    Row-level change details (used by drilldown output).
    Mirrors comparison_service.DeltaRow-like structure.
    """
    kind: Literal["MODIFIED", "ADDED", "REMOVED"] = Field(..., description="Row delta kind")
    row_a: Optional[NonNegativeInt] = Field(None, description="Row index on A side")
    row_b: Optional[NonNegativeInt] = Field(None, description="Row index on B side")
    changed_cols: List[int] = Field(default_factory=list, description="Indexes of columns changed")
    old_vals: Dict[int, str] = Field(default_factory=dict, description="Old values by column index")
    new_vals: Dict[int, str] = Field(default_factory=dict, description="New values by column index")


# ============================================================
# File Comparison Output Models
# ============================================================

class FileComparisonDetail(BaseModel):
    """
    Detailed comparison result for a single file pair.

    Used by /comparison/run and /comparison/compare-zip.

    Includes:
    - record delta counts (added_rows/removed_rows/modified_rows)
    - drilldown CSV paths (csv_path_a/csv_path_b)
    - Oracle EBS module metadata enrichment
    """
    group: str = Field("", description="Inferred group/module")
    filename: str = Field("", description="Logical filename used for matching")
    status: Literal["SAME", "MODIFIED", "ADDED", "REMOVED", ""] = Field("", description="Comparison status")
    similarity: UnitFloat = Field(0.0, description="Similarity [0..1]")

    rows_a: NonNegativeInt = Field(0)
    rows_b: NonNegativeInt = Field(0)
    cols_a: NonNegativeInt = Field(0)
    cols_b: NonNegativeInt = Field(0)

    added_rows: NonNegativeInt = Field(0, description="Rows added in B vs A")
    removed_rows: NonNegativeInt = Field(0, description="Rows removed in B vs A")
    modified_rows: NonNegativeInt = Field(0, description="Rows modified between A and B")

    sha_a: str = Field("", description="SHA256 for side A CSV")
    sha_b: str = Field("", description="SHA256 for side B CSV")

    path_a: str = Field("", description="Logical path of file A")
    path_b: str = Field("", description="Logical path of file B")
    message: str = Field("", description="Human-friendly explanation")

    csv_path_a: str = Field("", description="Local CSV path for drilldown side A")
    csv_path_b: str = Field("", description="Local CSV path for drilldown side B")

    # Oracle EBS module metadata
    oracle_module_name: Optional[str] = Field(None, description="Oracle module human name")
    oracle_business_domain: Optional[str] = Field(None, description="Oracle business domain")


# ============================================================
# Drilldown Models
# ============================================================

class DeltaFrame(BaseModel):
    """
    Side-by-side delta data for drilldown.
    """
    headers: List[str] = Field(default_factory=list)
    rows: List[Dict[str, Any]] = Field(default_factory=list)


class DrilldownResult(BaseModel):
    """
    Drilldown comparison result for a specific file pair.

    Backend returns:
      - deltaA / deltaB
      - row_count_A / row_count_B
    Some older clients may send:
      - delta_a / delta_b
      - row_count_a / row_count_b

    This model supports both using aliases.
    """
    filename: str = Field("", description="Filename shown in UI")
    group: str = Field("", description="Group shown in UI")

    header: List[str] = Field(default_factory=list)
    stats: Dict[str, int] = Field(default_factory=dict)
    truncated: bool = Field(False)

    # Accept backend keys deltaA/deltaB
    delta_a: DeltaFrame = Field(default_factory=DeltaFrame, alias="deltaA")
    delta_b: DeltaFrame = Field(default_factory=DeltaFrame, alias="deltaB")

    # Accept backend keys row_count_A/row_count_B
    row_count_a: int = Field(default=0, alias="row_count_A")
    row_count_b: int = Field(default=0, alias="row_count_B")

    col_count: int = Field(0)

    model_config = ConfigDict(populate_by_name=True)


# ============================================================
# Summary / Structure Models
# ============================================================

class ComparisonSummary(BaseModel):
    """
    Summary used by typed ZIP response and session compare.
    """
    total_files: NonNegativeInt = Field(0)
    matched_files: NonNegativeInt = Field(0)

    same: NonNegativeInt = Field(0)
    modified: NonNegativeInt = Field(0)
    added: NonNegativeInt = Field(0)
    removed: NonNegativeInt = Field(0)

    overall_similarity: PercentFloat = Field(0.0, description="Overall similarity percent (0-100)")

    # Oracle EBS domain breakdown: {"Finance & Accounting": 12, ...}
    by_oracle_domain: Optional[Dict[str, int]] = Field(None, description="File count by Oracle business domain")


class FolderChange(BaseModel):
    folder: str = Field(..., description="Folder path")
    count_a: NonNegativeInt = Field(..., description="Count in A")
    count_b: NonNegativeInt = Field(..., description="Count in B")
    delta: int = Field(..., description="count_b - count_a")


class GroupChange(BaseModel):
    group: str = Field(..., description="Group name")
    count_a: NonNegativeInt = Field(..., description="Count in A")
    count_b: NonNegativeInt = Field(..., description="Count in B")
    delta: int = Field(..., description="count_b - count_a")


# ============================================================
# Response Models
# ============================================================

class ZipComparisonResponse(BaseModel):
    """
    Typed response for /comparison/compare-zip.
    """
    summary: ComparisonSummary = Field(
        default_factory=lambda: ComparisonSummary(
            total_files=0,
            matched_files=0,
            same=0,
            modified=0,
            added=0,
            removed=0,
            overall_similarity=0.0,
        )
    )
    files: List[FileComparisonDetail] = Field(default_factory=list)
    folder_changes: List[FolderChange] = Field(default_factory=list)
    group_changes: List[GroupChange] = Field(default_factory=list)
    info_a: Dict[str, Any] = Field(default_factory=dict)
    info_b: Dict[str, Any] = Field(default_factory=dict)


class FileComparisonResult(BaseModel):
    """
    Generic file comparison result used by older clients.
    """
    filename: str = Field(..., min_length=1)
    similarity: UnitFloat = Field(...)
    deltas: List[DeltaRow] = Field(default_factory=list)


class ComparisonResponse(BaseModel):
    """
    Aggregated comparison response.

    This model supports both:
    - older style: summary + results
    - extended fields from compare_files().to_dict() payload
    """
    summary: ComparisonSummary = Field(
        default_factory=lambda: ComparisonSummary(
            total_files=0,
            matched_files=0,
            same=0,
            modified=0,
            added=0,
            removed=0,
            overall_similarity=0.0,
        )
    )
    results: List[FileComparisonResult] = Field(default_factory=list)

    # Extended fields (matches compare_files().to_dict())
    similarity: PercentFloat = Field(0.0, description="Overall similarity percent (0-100)")
    same: NonNegativeInt = Field(0)
    modified: NonNegativeInt = Field(0)
    added: NonNegativeInt = Field(0)
    removed: NonNegativeInt = Field(0)
    total_changes: NonNegativeInt = Field(0)

    changes: List[Dict[str, Any]] = Field(default_factory=list)
    folder_changes: List[Dict[str, Any]] = Field(default_factory=list)
    group_deltas: List[Dict[str, Any]] = Field(default_factory=list)
