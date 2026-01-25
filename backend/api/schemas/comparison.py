from pydantic import BaseModel
from typing import List, Dict, Optional

class ComparisonRequest(BaseModel):
    left_session_id: str
    right_session_id: str

class FileMatch(BaseModel):
    filename: str
    similarity: float

class DeltaRow(BaseModel):
    row_id: int
    change_type: str  # added / removed / modified
    before: Optional[Dict]
    after: Optional[Dict]

class FileComparisonResult(BaseModel):
    filename: str
    similarity: float
    deltas: List[DeltaRow]

class ComparisonSummary(BaseModel):
    total_files: int
    matched_files: int
    average_similarity: float

class ComparisonResponse(BaseModel):
    summary: ComparisonSummary
    results: List[FileComparisonResult]
