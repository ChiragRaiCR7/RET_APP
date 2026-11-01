"""Compare two converted workspaces: pair datasets, then diff rows without needing keys.

Row diff algorithm (keyless, order-independent):
1. Columns are aligned by *name* (union of both headers); ignored columns (audit/WHO
   columns by default) are excluded from equality.
2. Rows with an identical normalised fingerprint on both sides cancel out (multiset).
3. Leftover rows are paired as MODIFIED by greedy best Jaccard similarity of their
   ``column=value`` cells (≥ ``PAIR_THRESHOLD``). When the leftover matrix is too large
   for that, rows are paired by their first non-empty compared cell instead.
4. Unpaired leftovers are REMOVED (left only) or ADDED (right only).
"""

import csv
import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from sqlalchemy.orm import Session

from app.db import new_session
from app.models import Comparison, ComparisonItem, Dataset, Workspace
from app.schemas import DiffOut, DiffRow
from app.services.workspaces import base_name, dataset_path

log = logging.getLogger("ret.compare")

MAX_ROWS = 200_000
PAIR_THRESHOLD = 0.5
MAX_PAIR_MATRIX = 250_000  # left×right leftovers above this use the cheap pairing fallback
MAX_DIFF_ROWS = 2_000


def norm_col(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.casefold())


@dataclass
class Options:
    ignore_case: bool = False
    trim_whitespace: bool = True
    ignore_columns: set[str] = field(default_factory=set)  # normalised names

    @classmethod
    def from_stored(cls, raw: dict[str, object]) -> "Options":
        cols = raw.get("ignore_columns") or []
        assert isinstance(cols, list)
        return cls(
            ignore_case=bool(raw.get("ignore_case")),
            trim_whitespace=bool(raw.get("trim_whitespace", True)),
            ignore_columns={norm_col(str(c)) for c in cols},
        )

    def cell(self, v: str) -> str:
        if self.trim_whitespace:
            v = v.strip()
        return v.casefold() if self.ignore_case else v


def _read(path: Path | None) -> tuple[list[str], list[list[str]]]:
    if path is None:
        return [], []
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh)
        header = next(reader, [])
        rows = [r for _, r in zip(range(MAX_ROWS), reader, strict=False)]
    return header, rows


@dataclass
class Diff:
    header: list[str]
    compared: list[int]
    left: list[list[str]]
    right: list[list[str]]
    equal: int
    pairs: list[tuple[int, int, list[int]]]
    removed: list[int]
    added: list[int]


def diff_tables(left_path: Path | None, right_path: Path | None, opts: Options) -> Diff:
    lh, lrows = _read(left_path)
    rh, rrows = _read(right_path)
    header = lh + [h for h in rh if h not in set(lh)]
    lpos = {h: i for i, h in enumerate(lh)}
    rpos = {h: i for i, h in enumerate(rh)}

    def project(row: list[str], pos: dict[str, int]) -> list[str]:
        return [row[pos[h]] if h in pos and pos[h] < len(row) else "" for h in header]

    left = [project(r, lpos) for r in lrows]
    right = [project(r, rpos) for r in rrows]
    compared = [i for i, h in enumerate(header) if norm_col(h) not in opts.ignore_columns]

    def key(row: list[str]) -> str:
        return "\x1f".join(opts.cell(row[i]) for i in compared)

    lkeys = [key(r) for r in left]
    rkeys = [key(r) for r in right]
    rpool: dict[str, list[int]] = defaultdict(list)
    for j, k in enumerate(rkeys):
        rpool[k].append(j)
    equal = 0
    l_left: list[int] = []
    for i, k in enumerate(lkeys):
        if rpool.get(k):
            rpool[k].pop()
            equal += 1
        else:
            l_left.append(i)
    r_left = sorted(j for js in rpool.values() for j in js)

    def changed(i: int, j: int) -> list[int]:
        return [c for c in compared if opts.cell(left[i][c]) != opts.cell(right[j][c])]

    pairs: list[tuple[int, int, list[int]]] = []
    used_l: set[int] = set()
    used_r: set[int] = set()
    if l_left and r_left and len(l_left) * len(r_left) <= MAX_PAIR_MATRIX:
        lt = {i: {f"{c}={opts.cell(left[i][c])}" for c in compared} for i in l_left}
        rt = {j: {f"{c}={opts.cell(right[j][c])}" for c in compared} for j in r_left}
        scored = []
        for i in l_left:
            for j in r_left:
                union = len(lt[i] | rt[j])
                sim = len(lt[i] & rt[j]) / union if union else 0.0
                if sim >= PAIR_THRESHOLD:
                    scored.append((sim, i, j))
        scored.sort(key=lambda t: (-t[0], t[1], t[2]))
        for _, i, j in scored:
            if i not in used_l and j not in used_r:
                used_l.add(i)
                used_r.add(j)
                pairs.append((i, j, changed(i, j)))
    elif l_left and r_left:

        def anchor(row: list[str]) -> str | None:
            return next((opts.cell(row[c]) for c in compared if row[c].strip()), None)

        by_anchor: dict[str, list[int]] = defaultdict(list)
        for j in r_left:
            if (a := anchor(right[j])) is not None:
                by_anchor[a].append(j)
        for i in l_left:
            a = anchor(left[i])
            if a is not None and by_anchor.get(a):
                j = by_anchor[a].pop(0)
                used_l.add(i)
                used_r.add(j)
                pairs.append((i, j, changed(i, j)))
    pairs.sort()
    return Diff(
        header,
        compared,
        left,
        right,
        equal,
        pairs,
        [i for i in l_left if i not in used_l],
        [j for j in r_left if j not in used_r],
    )


def diff_to_api(d: Diff) -> DiffOut:
    rows: list[DiffRow] = []
    for i, j, ch in d.pairs:
        rows.append(
            DiffRow(
                kind="MODIFIED",
                left_row=i,
                right_row=j,
                left=d.left[i],
                right=d.right[j],
                changed=ch,
            )
        )
    rows += [
        DiffRow(
            kind="REMOVED",
            left_row=i,
            right_row=None,
            left=d.left[i],
            right=None,
            changed=d.compared,
        )
        for i in d.removed
    ]
    rows += [
        DiffRow(
            kind="ADDED",
            left_row=None,
            right_row=j,
            left=None,
            right=d.right[j],
            changed=d.compared,
        )
        for j in d.added
    ]
    stats = {
        "equal": d.equal,
        "modified": len(d.pairs),
        "removed": len(d.removed),
        "added": len(d.added),
    }
    ignored = [i for i in range(len(d.header)) if i not in set(d.compared)]
    return DiffOut(
        header=d.header,
        ignored=ignored,
        rows=rows[:MAX_DIFF_ROWS],
        stats=stats,
        truncated=len(rows) > MAX_DIFF_ROWS,
    )


def _strip_root(logical: str) -> str:
    parts = PurePosixPath(logical).parts
    return "/".join(parts[1:]) if len(parts) > 1 else logical


def pair_datasets(
    left: list[Dataset], right: list[Dataset]
) -> list[tuple[Dataset | None, Dataset | None]]:
    """Pair by (group, name without collision suffix); within a key prefer identical
    content, then identical path below the upload root, then file order."""
    lmap: dict[tuple[str, str], list[Dataset]] = defaultdict(list)
    rmap: dict[tuple[str, str], list[Dataset]] = defaultdict(list)
    for ds in left:
        lmap[(ds.group, base_name(ds.name))].append(ds)
    for ds in right:
        rmap[(ds.group, base_name(ds.name))].append(ds)
    out: list[tuple[Dataset | None, Dataset | None]] = []
    for k in sorted(set(lmap) | set(rmap)):
        ls, rs = list(lmap.get(k, [])), list(rmap.get(k, []))
        for match in (
            lambda a, b: a.sha256 == b.sha256,
            lambda a, b: _strip_root(a.logical_path) == _strip_root(b.logical_path),
            lambda a, b: True,
        ):
            for a in list(ls):
                b = next((x for x in rs if match(a, x)), None)
                if b is not None:
                    out.append((a, b))
                    ls.remove(a)
                    rs.remove(b)
        out += [(a, None) for a in ls] + [(None, b) for b in rs]
    return out


def run(job_id: str, comparison_id: str) -> str:
    with new_session() as db:
        cmp = db.get(Comparison, comparison_id)
        if cmp is None:
            raise RuntimeError("Comparison was deleted.")
        try:
            return _run(db, cmp, job_id)
        except BaseException:
            db.rollback()
            cmp.status = "failed"
            db.commit()
            raise


def _run(db: Session, cmp: Comparison, job_id: str) -> str:
    from app.services import jobs

    left = db.get(Workspace, cmp.left_workspace_id)
    right = db.get(Workspace, cmp.right_workspace_id)
    assert left is not None and right is not None
    opts = Options.from_stored(cmp.options)
    cmp.status = "running"
    db.commit()
    pairs = pair_datasets(list(left.datasets), list(right.datasets))
    summary: Counter[str] = Counter()
    for n, (a, b) in enumerate(pairs, 1):
        ref = a or b
        assert ref is not None  # pair_datasets never yields (None, None)
        item = ComparisonItem(
            comparison_id=cmp.id,
            group=ref.group,
            name=base_name(ref.name),
            left_dataset_id=a.id if a else None,
            right_dataset_id=b.id if b else None,
            rows_left=a.rows if a else 0,
            rows_right=b.rows if b else 0,
        )
        if a is None:
            item.status, item.added = "ADDED", item.rows_right
        elif b is None:
            item.status, item.removed = "REMOVED", item.rows_left
        elif a.sha256 == b.sha256:
            item.status = "SAME"
        else:
            d = diff_tables(dataset_path(a), dataset_path(b), opts)
            item.added, item.removed, item.modified = len(d.added), len(d.removed), len(d.pairs)
            item.status = "MODIFIED" if item.added or item.removed or item.modified else "SAME"
        summary[item.status] += 1
        db.add(item)
        if n % 20 == 0:
            db.commit()
            jobs.report_progress(job_id, n, len(pairs))
    cmp.summary = {s: summary.get(s, 0) for s in ("SAME", "MODIFIED", "ADDED", "REMOVED")}
    cmp.status = "succeeded"
    db.commit()
    return (
        f"{len(pairs)} datasets compared: {summary['MODIFIED']} modified, "
        f"{summary['ADDED']} added, {summary['REMOVED']} removed."
    )
