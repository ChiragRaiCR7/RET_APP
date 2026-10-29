"""Business Group → Ledger → Legal Entity → Operating Unit → Inventory Organization.

Sources (matched by dataset name, case-insensitive, collision suffix ignored):
- FUN_BUSINESS_UNIT.CSV: PrimaryLedgerName, LegalEntityName, BusinessUnitName (or Name)
- INVENTORYORGANIZATIONMASTER.CSV / …CHILD.CSV: NAME, BusinessUnitName (merged, de-duplicated)

Strict rules (kept from v4): business units need ledger + legal entity + name; inventory
organizations attach only when their BusinessUnitName joins to a business unit.
"""

import csv
from collections import Counter

from app.models import Workspace
from app.schemas import NodeType, StructureNode, StructureOut
from app.services.workspaces import base_name, dataset_path

FUN_BU = "FUN_BUSINESS_UNIT.CSV"
INV_FILES = ("INVENTORYORGANIZATIONMASTER.CSV", "INVENTORYORGANIZATIONCHILD.CSV")
DEFAULT_BG = "Default Business Group"


def _rows(ws: Workspace, name: str) -> tuple[list[str], list[dict[str, str]]] | None:
    matches = [d for d in ws.datasets if base_name(d.name) == name]
    if not matches:
        return None
    header: list[str] = []
    rows: list[dict[str, str]] = []
    for ds in matches:
        with dataset_path(ds).open(encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            header = header or list(reader.fieldnames or [])
            rows.extend(reader)
    return header, rows


def _col(header: list[str], *names: str) -> str | None:
    lower = {h.casefold(): h for h in header}
    return next((lower[n.casefold()] for n in names if n.casefold() in lower), None)


def build(ws: Workspace, business_group: str | None = None) -> StructureOut:
    diagnostics: list[str] = []
    sources: list[str] = []
    counts: dict[NodeType, int] = dict.fromkeys(
        ("business_group", "ledger", "legal_entity", "operating_unit", "inventory_org"), 0
    )
    fun = _rows(ws, FUN_BU)
    invs = [(n, _rows(ws, n)) for n in INV_FILES]
    if fun is None and all(r is None for _, r in invs):
        return StructureOut(
            status="missing_files",
            root=None,
            sources=[],
            counts=counts,
            diagnostics=[f"Convert an extract containing {FUN_BU} or {' / '.join(INV_FILES)}."],
        )

    pruned: Counter[str] = Counter()
    tree: dict[str, dict[str, dict[str, set[str]]]] = {}
    bu_index: dict[str, tuple[str, str, str]] = {}

    if fun is None:
        diagnostics.append(f"{FUN_BU} not found: inventory organizations cannot be placed.")
    else:
        sources.append(FUN_BU)
        header, rows = fun
        led, le = _col(header, "PrimaryLedgerName"), _col(header, "LegalEntityName")
        bu = _col(header, "BusinessUnitName", "Name")
        missing = [
            n
            for n, c in (
                ("PrimaryLedgerName", led),
                ("LegalEntityName", le),
                ("BusinessUnitName", bu),
            )
            if c is None
        ]
        if missing:
            diagnostics.append(f"{FUN_BU} is missing columns: {', '.join(missing)}.")
        else:
            assert led and le and bu
            for r in rows:
                vals = (r.get(led, "").strip(), r.get(le, "").strip(), r.get(bu, "").strip())
                if not all(vals):
                    pruned["business units missing ledger, legal entity or name"] += 1
                    continue
                tree.setdefault(vals[0], {}).setdefault(vals[1], {}).setdefault(vals[2], set())
                bu_index[vals[2].casefold()] = vals

    seen: set[tuple[str, str]] = set()
    for name, data in invs:
        if data is None:
            continue
        sources.append(name)
        header, rows = data
        org, bu = _col(header, "NAME"), _col(header, "BusinessUnitName")
        if org is None or bu is None:
            diagnostics.append(f"{name} is missing NAME or BusinessUnitName.")
            continue
        for r in rows:
            o, b = r.get(org, "").strip(), r.get(bu, "").strip()
            if not o or not b:
                pruned["inventory orgs missing NAME or BusinessUnitName"] += 1
                continue
            if (b.casefold(), o.casefold()) in seen:
                continue
            seen.add((b.casefold(), o.casefold()))
            parent = bu_index.get(b.casefold())
            if parent is None:
                pruned["inventory orgs whose business unit is not in FUN_BUSINESS_UNIT"] += 1
                continue
            tree[parent[0]][parent[1]][parent[2]].add(o)

    diagnostics += [f"Skipped {n} {what}." for what, n in pruned.items()]
    if not tree:
        return StructureOut(
            status="no_data",
            root=None,
            sources=sources,
            counts=counts,
            diagnostics=diagnostics or ["No usable rows found."],
        )

    def node(name: str, type_: NodeType, children: list[StructureNode]) -> StructureNode:
        counts[type_] += 1
        return StructureNode(name=name, type=type_, children=children)

    root = node(
        business_group or DEFAULT_BG,
        "business_group",
        [
            node(
                ledger,
                "ledger",
                [
                    node(
                        le,
                        "legal_entity",
                        [
                            node(
                                ou,
                                "operating_unit",
                                [node(o, "inventory_org", []) for o in sorted(orgs)],
                            )
                            for ou, orgs in sorted(ous.items())
                        ],
                    )
                    for le, ous in sorted(les.items())
                ],
            )
            for ledger, les in sorted(tree.items())
        ],
    )
    return StructureOut(
        status="ready", root=root, sources=sources, diagnostics=diagnostics, counts=counts
    )
