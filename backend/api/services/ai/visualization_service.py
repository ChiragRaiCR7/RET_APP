"""
Visualization service for rendering static chart images using matplotlib + seaborn.

Parses ```chart``` blocks in AI responses and generates PNG images
encoded as base64 for optional UI display or export.
"""

from __future__ import annotations

import base64
import io
import json
import re
from typing import Any, Dict, List, Optional, cast

_CHART_BLOCK_RE = re.compile(r"```chart\s*\n([\s\S]*?)```", re.IGNORECASE)
_THEME_INITIALIZED = False
_MPL_AVAILABLE: Optional[bool] = None


def _load_matplotlib() -> bool:
    global _MPL_AVAILABLE
    if _MPL_AVAILABLE is not None:
        return _MPL_AVAILABLE

    try:
        import matplotlib

        matplotlib.use("Agg")

        import matplotlib.pyplot as plt  # noqa: WPS433
        from matplotlib.patches import Circle  # noqa: WPS433
        from matplotlib.projections.polar import PolarAxes  # noqa: WPS433
        import numpy as np  # noqa: WPS433
        import seaborn as sns  # noqa: WPS433

        globals()["plt"] = plt
        globals()["Circle"] = Circle
        globals()["PolarAxes"] = PolarAxes
        globals()["np"] = np
        globals()["sns"] = sns

        _MPL_AVAILABLE = True
    except Exception:
        _MPL_AVAILABLE = False

    return _MPL_AVAILABLE


def _init_theme() -> None:
    global _THEME_INITIALIZED
    if not _load_matplotlib():
        return
    if _THEME_INITIALIZED:
        return
    sns.set_theme(style="darkgrid")
    _THEME_INITIALIZED = True


def _extract_chart_blocks(answer: str) -> List[Dict[str, Any]]:
    if not answer:
        return []

    blocks: List[Dict[str, Any]] = []
    for match in _CHART_BLOCK_RE.finditer(answer):
        raw = match.group(1).strip()
        if not raw:
            continue
        try:
            blocks.append(json.loads(raw))
        except Exception:
            continue
    return blocks


def _render_chart_image(config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not _load_matplotlib():
        return None
    chart_type = str(config.get("type", "")).lower().strip()
    data = config.get("data", {}) or {}
    labels = data.get("labels", []) or []
    datasets = data.get("datasets", []) or []

    if not datasets:
        return None

    _init_theme()
    fig = plt.figure(figsize=(6.5, 4.2), dpi=150)

    try:
        if chart_type in {"bar", "line"}:
            ax = fig.add_subplot(1, 1, 1)
            x = np.arange(len(labels)) if labels else np.arange(len(datasets[0].get("data", [])))
            width = 0.8 / max(len(datasets), 1)

            for i, ds in enumerate(datasets):
                values = ds.get("data", []) or []
                label = ds.get("label") or f"Series {i + 1}"

                if chart_type == "bar":
                    offset = (i - (len(datasets) - 1) / 2) * width
                    ax.bar(x + offset, values, width=width, label=label)
                else:
                    ax.plot(x, values, marker="o", label=label)

            if labels:
                ax.set_xticks(x)
                ax.set_xticklabels(labels, rotation=0)

        elif chart_type in {"pie", "doughnut"}:
            ax = fig.add_subplot(1, 1, 1)
            values = datasets[0].get("data", []) or []
            ax.pie(values, labels=labels if labels else None, autopct="%1.1f%%")
            if chart_type == "doughnut":
                centre_circle = Circle((0, 0), 0.55, fc="white")
                ax.add_artist(centre_circle)
            ax.axis("equal")

        elif chart_type == "scatter":
            ax = fig.add_subplot(1, 1, 1)
            for i, ds in enumerate(datasets):
                points = ds.get("data", []) or []
                label = ds.get("label") or f"Series {i + 1}"
                if points and isinstance(points[0], dict):
                    xs = [p.get("x") for p in points]
                    ys = [p.get("y") for p in points]
                else:
                    xs = list(range(len(points)))
                    ys = points
                ax.scatter(xs, ys, label=label)

        elif chart_type in {"radar", "polararea"}:
            ax = cast(PolarAxes, fig.add_subplot(1, 1, 1, polar=True))
            values = datasets[0].get("data", []) or []
            if not values:
                return None
            angles = np.linspace(0, 2 * np.pi, len(values), endpoint=False)

            if chart_type == "radar":
                values = list(values) + [values[0]]
                angles = np.concatenate([angles, [angles[0]]])
                ax.plot(angles, values)
                ax.fill(angles, values, alpha=0.25)
            else:
                width = 2 * np.pi / len(values)
                ax.bar(angles, values, width=width, bottom=0.0)

            if labels:
                angles_deg = (angles[: len(labels)] * 180 / np.pi).tolist()
                label_list = [str(l) for l in labels]
                ax.set_thetagrids(angles_deg, label_list)

        else:
            return None

        title = config.get("title") or ""
        if title:
            fig.suptitle(title)

        if len(datasets) > 1 and chart_type not in {"pie", "doughnut", "polararea"}:
            fig.legend(loc="upper right")

        fig.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight")
        plt.close(fig)
        img_data = base64.b64encode(buf.getvalue()).decode("utf-8")

        return {
            "type": "chart",
            "format": "png",
            "data": img_data,
            "title": title or None,
            "chart_type": chart_type or None,
        }

    except Exception:
        plt.close(fig)
        return None


def render_chart_images_from_answer(answer: str) -> List[Dict[str, Any]]:
    """
    Parse chart blocks in an answer and render PNG images via matplotlib/seaborn.

    Returns a list of visualization objects with base64-encoded PNG data.
    """
    if not _load_matplotlib():
        return []

    charts = _extract_chart_blocks(answer)
    if not charts:
        return []

    rendered: List[Dict[str, Any]] = []
    for config in charts:
        result = _render_chart_image(config)
        if result:
            rendered.append(result)
    return rendered
