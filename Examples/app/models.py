from pydantic import BaseModel
from typing import List, Optional, Set
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field


class ScanProgress(BaseModel):
    status: str = "idle"
    progress: int = 0
    entries_done: int = 0
    entries_total: int = 0
    xml_found: int = 0
    groups_detected: int = 0
    error: Optional[str] = None


class ConversionProgress(BaseModel):
    status: str = "idle"
    progress: int = 0
    files_done: int = 0
    files_total: int = 0
    successful: int = 0
    errors: int = 0
    mb_per_sec: float = 0.0
    eta_min: float = 0.0
    output_format: str = "csv"
    error: Optional[str] = None


class GroupInfo(BaseModel):
    name: str
    count: int
    size_mb: float


class FileInfo(BaseModel):
    filename: str
    logical_path: str
    group: str
    size_mb: float
    rows: int


@dataclass
class SessionInfo:
    session_id: str
    zip_path: Path
    session_dir: Path
    custom_prefixes: Set[str]
    created_at: datetime

    scan_progress: ScanProgress = field(default_factory=ScanProgress)
    conversion_progress: ConversionProgress = field(default_factory=ConversionProgress)

    xml_inventory: List = field(default_factory=list)
    groups: List[GroupInfo] = field(default_factory=list)
    conversion_results: List = field(default_factory=list)
