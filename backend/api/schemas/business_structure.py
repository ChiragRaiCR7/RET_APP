"""Schemas for the Business Structure hierarchy endpoint."""

from __future__ import annotations

from pydantic import BaseModel
from typing import List, Optional, Literal


class BusinessStructureNode(BaseModel):
    """A node in the 5-layer business structure tree."""
    name: str
    node_type: Literal[
        "business_group",
        "ledger",
        "legal_entity",
        "operating_unit",
        "inventory_org",
    ]
    children: List[BusinessStructureNode] = []


class BusinessStructureResponse(BaseModel):
    """Response from the business-structure endpoint."""
    status: Literal[
        "ready",
        "not_converted",
        "missing_files",
        "missing_columns",
        "no_data",
    ]
    nodes: List[BusinessStructureNode] = []
    diagnostics: List[str] = []
    source_files: List[str] = []
    pruned_summary: Optional[dict] = None
