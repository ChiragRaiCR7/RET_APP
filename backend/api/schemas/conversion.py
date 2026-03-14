
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

try:
    # Pydantic v2
    from pydantic import ConfigDict
    _HAS_V2 = True
except Exception:
    ConfigDict = None
    _HAS_V2 = False


# ------------------------------------------------------------
# Base model: tolerate extra fields from backend (safe evolution)
# ------------------------------------------------------------

class _BaseModel(BaseModel):
    """
    Base model that ignores unknown fields.
    This prevents response validation errors if backend adds new keys.
    """
    if _HAS_V2 and ConfigDict is not None:
        model_config = ConfigDict(extra="ignore")  # type: ignore[misc]


# ------------------------------------------------------------
# Scan response models
# ------------------------------------------------------------

class ScannedFileEntry(_BaseModel):
    """
    Represents a discovered file during scan.
    Supports: XML/XML.GZ/CSV/XLSX/XLS (and ZIP scan expansion results).
    """
    filename: str
    path: str
    group: str
    size: int

    abs_path: Optional[str] = None
    logical_path: Optional[str] = None

    # xml/csv/xlsx/xls/file
    file_type: Optional[str] = None

    business_zip: Optional[str] = ""
    folder_path: Optional[str] = ""
    root_folder: Optional[str] = ""
    zip_chain: List[str] = Field(default_factory=list)


class ScanGroupEntry(_BaseModel):
    name: str
    file_count: int
    size: int
    auto_embed_eligible: Optional[bool] = None
    auto_embed_reason: Optional[str] = None


class ScanSummary(_BaseModel):
    totalFiles: int
    totalGroups: int
    totalSize: int

    # file type counts: {"xml": 120, "csv": 5, "xlsx": 2, "xls": 12}
    typeCounts: Optional[Dict[str, int]] = None


class ZipScanResponse(_BaseModel):
    session_id: str
    xml_count: int
    group_count: int

    # Newer scan returns file_count (total scanned files)
    file_count: Optional[int] = None

    files: List[ScannedFileEntry] = Field(default_factory=list)
    groups: List[ScanGroupEntry] = Field(default_factory=list)
    summary: ScanSummary


# ------------------------------------------------------------
# Conversion index / listing models
# ------------------------------------------------------------

class ConversionFileEntry(_BaseModel):
    filename: str
    group: str
    rows: int = 0
    columns: int = 0

    # formatted string from backend e.g. "1.2 MB"
    size: str = ""

    # csv/xlsx/xls/file
    file_type: Optional[str] = None

    # may be empty for some copied files (depends on how index was built)
    logical_path: Optional[str] = None


class ConversionGroupEntry(_BaseModel):
    name: str
    file_count: int
    total_rows: int = 0
    total_size: int = 0


class ConversionFilesResponse(_BaseModel):
    session_id: str
    total_files: int
    total_groups: int

    excluded_count: Optional[int] = 0

    groups: List[ConversionGroupEntry] = Field(default_factory=list)
    files: List[ConversionFileEntry] = Field(default_factory=list)


# ------------------------------------------------------------
# Preview models
# ------------------------------------------------------------

class FilePreviewResponse(_BaseModel):
    filename: str
    headers: List[str] = Field(default_factory=list)
    rows: List[List[str]] = Field(default_factory=list)

    total_rows: int = 0
    preview_rows: int = 0
    columns: int = 0


class GroupsListItem(_BaseModel):
    name: str
    file_count: int
    total_rows: int = 0
    total_size: int = 0


class GroupsListResponse(_BaseModel):
    session_id: str
    total_groups: int
    groups: List[GroupsListItem] = Field(default_factory=list)


class ExclusionListResponse(_BaseModel):
    session_id: str
    excluded_count: int = 0
    excluded: List[str] = Field(default_factory=list)


# ------------------------------------------------------------
# Edit request models
# ------------------------------------------------------------

class AddRowRequest(_BaseModel):
    filename: str
    row: Dict[str, Any]


class AddFileRequest(_BaseModel):
    filename: str
    group: Optional[str] = None
    headers: List[str]


class CellChange(_BaseModel):
    row_index: int
    column: str
    value: Any = ""


class UpdateCellsRequest(_BaseModel):
    filename: str
    changes: List[CellChange] = Field(default_factory=list)


class SaveEditsRequest(_BaseModel):
    changes: Optional[List[Dict[str, Any]]] = None
