from pydantic import BaseModel
from typing import List, Optional, Dict, Any

class XmlFileInfo(BaseModel):
    filename: str
    path: str
    group: str
    size: int
    
class SimpleConversionRequest(BaseModel):
    session_id: str
    groups: Optional[List[str]] = None

class GroupInfo(BaseModel):
    name: str
    file_count: int
    size: int

class ZipScanResponse(BaseModel):
    session_id: str
    xml_count: int
    group_count: int
    files: List[XmlFileInfo]
    groups: List[GroupInfo]
    summary: Dict[str, int]

class ConversionRequest(BaseModel):
    session_id: str
    groups: Optional[List[str]] = None

class ConversionStats(BaseModel):
    total_files: int
    success: int
    failed: int

class ConvertedFile(BaseModel):
    filename: str
    group: str
    rows: int

class ConversionResponse(BaseModel):
    session_id: str
    stats: ConversionStats
    converted_files: List[ConvertedFile]


# New schemas for file listing and preview

class FileInfo(BaseModel):
    filename: str
    group: str
    rows: int
    columns: int
    size: str

class GroupSummary(BaseModel):
    name: str
    file_count: int
    total_rows: int
    total_size: int

class ConversionFilesResponse(BaseModel):
    session_id: str
    total_files: int
    total_groups: int
    groups: List[GroupSummary]
    files: List[FileInfo]

class FilePreviewResponse(BaseModel):
    filename: str
    headers: List[str]
    rows: List[List[str]]
    total_rows: int
    preview_rows: int
    columns: int

class GroupsListResponse(BaseModel):
    session_id: str
    total_groups: int
    groups: List[GroupSummary]

class DownloadRequest(BaseModel):
    session_id: str
    output_format: str = "csv"
    groups: Optional[List[str]] = None
    preserve_structure: bool = False

