from __future__ import annotations
from typing import List

from .elements import TextBox, Rect


def merge_spans_into_lines(lines):
    """Placeholder: no span merge yet."""
    return lines


def _union_rect(a: Rect, b: Rect) -> Rect:
    return Rect(
        x0=min(a.x0, b.x0),
        y0=min(a.y0, b.y0),
        x1=max(a.x1, b.x1),
        y1=max(a.y1, b.y1),
    )


def _same_column(col_x0: float, box_x0: float, x_tol: float) -> bool:
    return abs(col_x0 - box_x0) <= x_tol


def group_textboxes(text_boxes: List[TextBox], y_gap_tol: float = 14.0, x_tol: float = 10.0) -> List[TextBox]:
    """Group text boxes into columns/blocks by x alignment and vertical proximity.
    Tolerances increased to merge visually adjacent lines into one box for editability.
    """
    if not text_boxes:
        return []

    boxes = sorted(text_boxes, key=lambda b: (-b.bbox.y0, b.bbox.x0))

    columns: List[List[TextBox]] = []
    col_xs: List[float] = []

    for box in boxes:
        placed = False
        for idx, col_x0 in enumerate(col_xs):
            if _same_column(col_x0, box.bbox.x0, x_tol):
                columns[idx].append(box)
                col_xs[idx] = (col_x0 + box.bbox.x0) / 2
                placed = True
                break
        if not placed:
            columns.append([box])
            col_xs.append(box.bbox.x0)

    merged: List[TextBox] = []
    for col in columns:
        col_sorted = sorted(col, key=lambda b: b.bbox.y0)
        if not col_sorted:
            continue
        current = col_sorted[0]
        for nxt in col_sorted[1:]:
            gap = nxt.bbox.y0 - current.bbox.y1
            overlap_x = not (nxt.bbox.x0 > current.bbox.x1 or nxt.bbox.x1 < current.bbox.x0)
            if gap <= y_gap_tol and overlap_x:
                current.paragraphs.extend(nxt.paragraphs)
                current.bbox = _union_rect(current.bbox, nxt.bbox)
            else:
                merged.append(current)
                current = nxt
        merged.append(current)

    merged = sorted(merged, key=lambda b: b.z_index)
    return merged
