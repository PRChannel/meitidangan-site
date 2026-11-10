# -*- coding: utf-8 -*-
"""边框网格检测：从公告图中检出表格的横线、竖线，切出单元格矩形。

核心思路（与历史上 rowocr5/rowocr6 一致）：
- 灰度 < 阈值(默认 180) 记为暗像素；
- 一整行/列的暗像素占比 > dark_frac(默认 0.55) 视为分隔线；
- 竖线往往不贯通全图（不同分段列布局不同），所以在每两条横线围成的
  「行带」内独立检测竖线，而不是只做全图均值。
"""
from __future__ import annotations

import numpy as np
from PIL import Image


def load_gray(path: str) -> np.ndarray:
    img = Image.open(path).convert("L")
    return np.asarray(img, dtype=np.uint8)


def _runs(mask: np.ndarray, min_len: int) -> list[tuple[int, int]]:
    """把布尔序列中连续 True 段合并为 (start, end)；相邻段间隔 < min_len 时粘连。"""
    runs: list[tuple[int, int]] = []
    idx = np.flatnonzero(mask)
    if idx.size == 0:
        return runs
    start = prev = int(idx[0])
    for i in idx[1:]:
        i = int(i)
        if i - prev <= min_len:
            prev = i
        else:
            runs.append((start, prev))
            start = prev = i
    runs.append((start, prev))
    return runs


def hlines(gray: np.ndarray, thresh: int = 180, dark_frac: float = 0.55) -> list[int]:
    """横线：整行暗像素占比超阈值的行中心。"""
    dark = gray < thresh
    frac = dark.mean(axis=1)
    runs = _runs(frac > dark_frac, min_len=2)
    return [(a + b) // 2 for a, b in runs]


def vlines_in_band(gray: np.ndarray, y0: int, y1: int,
                   thresh: int = 180, dark_frac: float = 0.55) -> list[int]:
    """行带内竖线：只在 [y0, y1) 高度内统计每列暗像素占比。"""
    dark = gray[y0:y1, :] < thresh
    frac = dark.mean(axis=0)
    runs = _runs(frac > dark_frac, min_len=2)
    return [(a + b) // 2 for a, b in runs]


def bands(gray: np.ndarray, thresh: int = 180, dark_frac: float = 0.55,
          min_band_h: int = 12) -> list[dict]:
    """把图切成行带：每条行带 = 两条相邻横线之间。返回带竖线的网格描述。"""
    ys = hlines(gray, thresh, dark_frac)
    if len(ys) < 2:
        return []
    out = []
    for a, b in zip(ys, ys[1:]):
        if b - a < min_band_h:
            continue
        xs = vlines_in_band(gray, a, b, thresh, dark_frac)
        out.append({"y0": int(a), "y1": int(b), "vlines": [int(x) for x in xs]})
    return out


def band_cells(band: dict, img_w: int, pad: int = 2) -> list[dict]:
    """行带 → 单元格矩形列表（含左右 padding，防切字）。"""
    xs = band["vlines"]
    if len(xs) < 2:
        return []
    edges = [0] + xs + [img_w]
    cells = []
    for i in range(len(edges) - 1):
        x0, x1 = edges[i], edges[i + 1]
        if x1 - x0 < 8:
            continue
        cells.append({
            "col": i,
            "x0": max(0, x0 + pad), "x1": min(img_w, x1 - pad),
            "y0": band["y0"] + pad, "y1": band["y1"] - pad,
        })
    return cells


def align_bands(bs: list[dict], img_w: int, tol: int = 30, edge_margin: int = 20,
                pad: int = 2) -> list[dict]:
    """把行带按「列布局」分组对齐，同一张图里不同表格允许不同列宽。

    - 一张公告图常有多张表（网站表/应用表…），列边界不同；
    - 连续且竖线一致的带划为一组，组内以竖线最多的带为列基准；
    - 某带缺某条内线 → 该格横跨多列（合并单元格），记 cols=(i, j)；
    - 无表线（len<2）的带（分段标题）被剔除。
    """
    if not bs:
        return []

    def clean(xs):
        return [x for x in xs if edge_margin < x < img_w - edge_margin]

    groups: list[list[dict]] = []
    cur: list[dict] = []
    cur_ref: list[int] = []
    for b in bs:
        xs = clean(b["vlines"])
        if len(xs) < 2:
            if cur:
                groups.append(cur)
                cur, cur_ref = [], []
            continue
        if cur and (len(xs) != len(cur_ref)
                    or any(abs(x - r) > tol for x, r in zip(xs, cur_ref))):
            groups.append(cur)
            cur, cur_ref = [], []
        cur.append(b)
        if not cur_ref or len(xs) > len(cur_ref):
            cur_ref = xs
    if cur:
        groups.append(cur)

    out = []
    for g in groups:
        ref = max(g, key=lambda b: len(b["vlines"]))
        edges = clean(ref["vlines"])
        if len(edges) < 2:
            continue
        for b in g:
            xs = clean(b["vlines"])
            cells = []
            i = 0
            while i < len(edges) - 1:
                x0, x1 = edges[i], edges[i + 1]
                span_end = i
                for j in range(i + 1, len(edges) - 1):
                    mid = edges[j]
                    if not any(abs(x - mid) <= tol for x in xs):
                        span_end = j  # 没有线 → 与下一列合并
                    else:
                        break
                cells.append({
                    "cols": (i, span_end),
                    "x0": max(0, x0 + pad), "x1": min(img_w, edges[span_end + 1] - pad),
                    "y0": b["y0"] + pad, "y1": b["y1"] - pad,
                })
                i = span_end + 1
            out.append({"y0": b["y0"], "y1": b["y1"], "cells": cells,
                        "ncols": len(edges) - 1})
    return out


def crop_cell(path: str, rect: dict) -> Image.Image:
    img = Image.open(path)
    return img.crop((rect["x0"], rect["y0"], rect["x1"], rect["y1"]))
