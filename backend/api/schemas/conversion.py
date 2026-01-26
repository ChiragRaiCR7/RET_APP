from pydantic import BaseModel
from typing import List, Optional, Dict

class XmlFileInfo(BaseModel):
    filename: str
    path: str
    group: str
    size: int

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
