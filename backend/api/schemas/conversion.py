from pydantic import BaseModel
from typing import List, Optional, Dict

class ZipScanResponse(BaseModel):
    session_id: str
    xml_count: int
    files: List[Dict[str, str]]

class ConversionRequest(BaseModel):
    session_id: str

class ConversionStats(BaseModel):
    total_files: int
    success: int
    failed: int

class ConversionResponse(BaseModel):
    session_id: str
    stats: ConversionStats
