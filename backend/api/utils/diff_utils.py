def compute_row_diff(left: list[dict], right: list[dict]) -> list[dict]:
    deltas = []

    left_map = {i: row for i, row in enumerate(left)}
    right_map = {i: row for i, row in enumerate(right)}

    all_keys = set(left_map.keys()) | set(right_map.keys())

    for k in all_keys:
        l = left_map.get(k)
        r = right_map.get(k)

        if l and not r:
            deltas.append({"row_id": k, "change_type": "removed", "before": l, "after": None})
        elif r and not l:
            deltas.append({"row_id": k, "change_type": "added", "before": None, "after": r})
        elif l != r:
            deltas.append({"row_id": k, "change_type": "modified", "before": l, "after": r})

    return deltas
