"""
Build a 5-layer Business Structure hierarchy from converted CSV contents.

    Business Group → Ledger → Legal Entity → Operating Unit → Inventory Organization

Source CSVs (case-insensitive resolution):
  • FUN_BUSINESS_UNIT.CSV         → PrimaryLedgerName (Ledger), LegalEntityName (Legal Entity)
  • INVENTORYORGANIZATIONMASTER.CSV  → NAME (Inv Org), BusinessUnitName (Operating Unit)
  • INVENTORYORGANIZATIONCHILD.CSV   → NAME (Inv Org), BusinessUnitName (Operating Unit)

Join strategy: BusinessUnitName in inventory CSVs bridges to FUN_BUSINESS_UNIT rows.
Merge rule: Union + deduplicate the two inventory CSVs.
Business Group layer: configurable (source file TBD), placeholder for now.
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import unquote

from api.schemas.business_structure import (
    BusinessStructureNode,
    BusinessStructureResponse,
)
from api.services.storage_service import get_session_dir, get_session_metadata

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Target file names (matched case-insensitively)
# ---------------------------------------------------------------------------
FUN_BU_FILENAME = "FUN_BUSINESS_UNIT.CSV"
INV_MASTER_FILENAME = "INVENTORYORGANIZATIONMASTER.CSV"
INV_CHILD_FILENAME = "INVENTORYORGANIZATIONCHILD.CSV"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _resolve_file(out_dir: Path, filename: str) -> Optional[Path]:
    """Resolve *filename* inside *out_dir* trying several casing variants."""
    if not filename:
        return None
    candidates = [
        filename,
        unquote(filename),
        filename.upper(),
        unquote(filename).upper(),
        filename.lower(),
        unquote(filename).lower(),
    ]
    for c in candidates:
        p = out_dir / c
        if p.exists():
            return p
    return None


def _read_csv(path: Path) -> Tuple[List[str], List[Dict[str, str]]]:
    """Read a CSV returning (headers, rows-as-dicts)."""
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        headers = list(reader.fieldnames or [])
        rows = [dict(r) for r in reader]
    return headers, rows


def _find_column(headers: List[str], target: str) -> Optional[str]:
    """Return the actual header name that matches *target* case-insensitively."""
    target_lower = target.lower()
    for h in headers:
        if h.lower() == target_lower:
            return h
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def build_business_structure(
    session_id: str,
    user_id: str,
    business_group_name: Optional[str] = None,
) -> BusinessStructureResponse:
    """
    Build the 5-layer hierarchy from converted CSV output files.

    Parameters
    ----------
    session_id : str
        Active session whose ``output/`` folder holds converted CSVs.
    user_id : str
        Requesting user – used for ownership check.
    business_group_name : str, optional
        Top-level Business Group label.  Defaults to ``"Default Business Group"``
        until a dedicated source file is configured.
    """
    diagnostics: List[str] = []
    source_files: List[str] = []

    # ---- ownership / session check ------------------------------------
    meta = get_session_metadata(session_id)
    if meta.get("user_id") and meta["user_id"] != user_id:
        raise ValueError("Unauthorized")

    sess_dir = get_session_dir(session_id)
    out_dir = sess_dir / "output"

    if not out_dir.exists():
        return BusinessStructureResponse(
            status="not_converted",
            diagnostics=["Conversion output directory does not exist."],
        )

    # ---- discover required CSVs ---------------------------------------
    fun_path = _resolve_file(out_dir, FUN_BU_FILENAME)
    inv_master_path = _resolve_file(out_dir, INV_MASTER_FILENAME)
    inv_child_path = _resolve_file(out_dir, INV_CHILD_FILENAME)

    missing: List[str] = []
    if fun_path:
        source_files.append(fun_path.name)
    else:
        missing.append(FUN_BU_FILENAME)

    if inv_master_path:
        source_files.append(inv_master_path.name)
    else:
        missing.append(INV_MASTER_FILENAME)

    if inv_child_path:
        source_files.append(inv_child_path.name)
    else:
        missing.append(INV_CHILD_FILENAME)

    if not fun_path and not inv_master_path and not inv_child_path:
        return BusinessStructureResponse(
            status="missing_files",
            diagnostics=[f"None of the required CSVs found: {', '.join(missing)}"],
            source_files=source_files,
        )

    if missing:
        diagnostics.append(f"Missing CSVs (partial data): {', '.join(missing)}")

    # ---- read FUN_BUSINESS_UNIT ---------------------------------------
    fun_rows: List[Dict[str, str]] = []
    fun_ledger_col: Optional[str] = None
    fun_le_col: Optional[str] = None
    fun_bu_col: Optional[str] = None

    if fun_path:
        fun_headers, fun_rows = _read_csv(fun_path)
        fun_ledger_col = _find_column(fun_headers, "PrimaryLedgerName")
        fun_le_col = _find_column(fun_headers, "LegalEntityName")
        fun_bu_col = _find_column(fun_headers, "BusinessUnitName") or _find_column(fun_headers, "Name")

        col_issues = []
        if not fun_ledger_col:
            col_issues.append("PrimaryLedgerName")
        if not fun_le_col:
            col_issues.append("LegalEntityName")
        if col_issues:
            diagnostics.append(
                f"{FUN_BU_FILENAME} missing columns: {', '.join(col_issues)}"
            )

    # ---- read & merge inventory CSVs -----------------------------------
    inv_rows: List[Dict[str, str]] = []
    inv_name_col: Optional[str] = None
    inv_bu_col: Optional[str] = None

    for inv_path, inv_label in [
        (inv_master_path, INV_MASTER_FILENAME),
        (inv_child_path, INV_CHILD_FILENAME),
    ]:
        if not inv_path:
            continue
        headers, rows = _read_csv(inv_path)

        name_col = _find_column(headers, "NAME")
        bu_col = _find_column(headers, "BusinessUnitName")

        if not name_col:
            diagnostics.append(f"{inv_label} missing column: NAME")
        if not bu_col:
            diagnostics.append(f"{inv_label} missing column: BusinessUnitName")

        if name_col and bu_col:
            if inv_name_col is None:
                inv_name_col = name_col
            if inv_bu_col is None:
                inv_bu_col = bu_col
            inv_rows.extend(rows)

    # Deduplicate inventory rows by (BusinessUnitName, NAME)
    if inv_bu_col and inv_name_col:
        seen = set()
        deduped: List[Dict[str, str]] = []
        for row in inv_rows:
            key = (
                (row.get(inv_bu_col) or "").strip().lower(),
                (row.get(inv_name_col) or "").strip().lower(),
            )
            if key not in seen:
                seen.add(key)
                deduped.append(row)
        inv_rows = deduped

    # ---- build hierarchy (strict prune) ---------------------------------
    bg_label = (business_group_name or "Default Business Group").strip()

    # Track pruned rows for diagnostics
    pruned = {"fun_missing_ledger": 0, "fun_missing_le": 0, "fun_missing_bu": 0,
              "inv_no_bu": 0, "inv_unlinked": 0, "inv_no_name": 0}

    # Index FUN rows by BusinessUnitName (lower) for join — strict: skip incomplete rows
    fun_by_bu: Dict[str, Dict[str, str]] = {}
    if fun_rows and fun_bu_col:
        for row in fun_rows:
            ledger = (row.get(fun_ledger_col) or "").strip() if fun_ledger_col else ""
            le = (row.get(fun_le_col) or "").strip() if fun_le_col else ""
            bu = (row.get(fun_bu_col) or "").strip()

            if not ledger:
                pruned["fun_missing_ledger"] += 1
                continue
            if not le:
                pruned["fun_missing_le"] += 1
                continue
            if not bu:
                pruned["fun_missing_bu"] += 1
                continue

            fun_by_bu[bu.lower()] = row

    # Assemble: Ledger → Legal Entity → Operating Unit → Inventory Org
    # Structure: ledger_name -> le_name -> ou_name -> set(inv_org_name)
    hierarchy: Dict[str, Dict[str, Dict[str, set]]] = {}

    # Populate from FUN rows (strict: only rows with all three fields)
    if fun_rows and fun_ledger_col and fun_le_col:
        for row in fun_rows:
            ledger = (row.get(fun_ledger_col) or "").strip()
            le = (row.get(fun_le_col) or "").strip()
            ou = (row.get(fun_bu_col) or "").strip() if fun_bu_col else ""

            if not ledger or not le or not ou:
                continue  # already counted in pruned above

            hierarchy.setdefault(ledger, {}).setdefault(le, {}).setdefault(ou, set())

    # Enrich with inventory rows (strict: drop unlinked rows)
    if inv_rows and inv_bu_col and inv_name_col:
        for row in inv_rows:
            ou = (row.get(inv_bu_col) or "").strip()
            inv_org = (row.get(inv_name_col) or "").strip()

            if not ou:
                pruned["inv_no_bu"] += 1
                continue
            if not inv_org:
                pruned["inv_no_name"] += 1
                continue

            # Strict: only attach if the OU joins to a FUN row
            bu_key = ou.lower()
            fun_match = fun_by_bu.get(bu_key)

            if not fun_match or not fun_ledger_col or not fun_le_col:
                pruned["inv_unlinked"] += 1
                continue

            ledger = (fun_match.get(fun_ledger_col) or "").strip()
            le = (fun_match.get(fun_le_col) or "").strip()

            if not ledger or not le:
                pruned["inv_unlinked"] += 1
                continue

            hierarchy.setdefault(ledger, {}).setdefault(le, {}).setdefault(ou, set())
            hierarchy[ledger][le][ou].add(inv_org)

    # Build pruned_summary for the response
    total_pruned = sum(pruned.values())
    pruned_summary = None
    if total_pruned > 0:
        pruned_summary = {k: v for k, v in pruned.items() if v > 0}
        pruned_summary["total"] = total_pruned
        parts = []
        if pruned.get("fun_missing_ledger"):
            parts.append(f"{pruned['fun_missing_ledger']} FUN rows missing PrimaryLedgerName")
        if pruned.get("fun_missing_le"):
            parts.append(f"{pruned['fun_missing_le']} FUN rows missing LegalEntityName")
        if pruned.get("fun_missing_bu"):
            parts.append(f"{pruned['fun_missing_bu']} FUN rows missing BusinessUnitName")
        if pruned.get("inv_unlinked"):
            parts.append(f"{pruned['inv_unlinked']} inventory rows with no matching FUN_BUSINESS_UNIT")
        if pruned.get("inv_no_bu"):
            parts.append(f"{pruned['inv_no_bu']} inventory rows missing BusinessUnitName")
        if pruned.get("inv_no_name"):
            parts.append(f"{pruned['inv_no_name']} inventory rows missing NAME")
        if parts:
            diagnostics.append(f"Strict pruning: {'; '.join(parts)}")

    if not hierarchy:
        return BusinessStructureResponse(
            status="no_data",
            diagnostics=diagnostics or ["CSVs found but no usable data extracted."],
            source_files=source_files,
        )

    # ---- convert dict hierarchy → Pydantic tree -----------------------
    ledger_nodes: List[BusinessStructureNode] = []
    for ledger_name in sorted(hierarchy):
        le_map = hierarchy[ledger_name]
        le_nodes: List[BusinessStructureNode] = []
        for le_name in sorted(le_map):
            ou_map = le_map[le_name]
            ou_nodes: List[BusinessStructureNode] = []
            for ou_name in sorted(ou_map):
                inv_set = ou_map[ou_name]
                inv_nodes = [
                    BusinessStructureNode(
                        name=inv_name,
                        node_type="inventory_org",
                    )
                    for inv_name in sorted(inv_set)
                ]
                ou_nodes.append(
                    BusinessStructureNode(
                        name=ou_name,
                        node_type="operating_unit",
                        children=inv_nodes,
                    )
                )
            le_nodes.append(
                BusinessStructureNode(
                    name=le_name,
                    node_type="legal_entity",
                    children=ou_nodes,
                )
            )
        ledger_nodes.append(
            BusinessStructureNode(
                name=ledger_name,
                node_type="ledger",
                children=le_nodes,
            )
        )

    bg_node = BusinessStructureNode(
        name=bg_label,
        node_type="business_group",
        children=ledger_nodes,
    )

    return BusinessStructureResponse(
        status="ready",
        nodes=[bg_node],
        diagnostics=diagnostics,
        source_files=source_files,
        pruned_summary=pruned_summary,
    )
