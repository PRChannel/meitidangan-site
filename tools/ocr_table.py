#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 OCR 的带坐标输出重建成二维表格。

用法：
    python3 tools/ocr_table.py <ocr.box> [--cols 序号,单位名称,许可证编号,单位性质,服务类别]

输入每行格式：文本<TAB>x<TAB>y<TAB>w<TAB>h（像素，原点左上）
输出：JSON 行数组，每个元素为 dict(列名 -> 文本)

重建思路：
1. 用 11 位许可证号作为行锚点（位置固定、取值唯一、最不容易误识别）；
2. 由锚点 y 序列算出平均行距，向上下补齐网格，避免个别证号漏识别导致整行丢失；
3. 每个文本块按 y 落到最近网格行，按 x 落到对应列；
4. 同格内多块按 y 顺序拼接（处理单元格内折行）。
"""
import argparse
import json
import re
import statistics
import sys

LICENSE_RE = re.compile(r"^\d{11}$")
SEQ_RE = re.compile(r"^\d{1,3}$")


def load(path):
    boxes = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) != 5:
                continue
            t, x, y, w, h = parts
            boxes.append((t, int(x), int(y), int(w), int(h)))
    return boxes


def guess_columns(boxes):
    """通用表头检测：顶部区域里块数最多的同一水平层视为表头行。"""
    if not boxes:
        return None
    top = [b for b in boxes if b[2] < 150]
    if len(top) < 3:
        return None
    # 按 y 聚类（±14px），取块数最多的一层
    top.sort(key=lambda b: b[2])
    clusters = []
    for b in top:
        if clusters and abs(b[2] - clusters[-1][0][2]) <= 14:
            clusters[-1].append(b)
        else:
            clusters.append([b])
    header = max(clusters, key=len)
    if len(header) < 3:
        return None
    header.sort(key=lambda b: b[1] + b[3] / 2)
    names = [b[0].strip() for b in header]
    names = [n for n in names if n and len(n) <= 12]
    if len(names) < 3:
        return None
    centers = [b[1] + b[3] / 2 for b in header[: len(names)]]
    bounds = [int((a + b) / 2) for a, b in zip(centers, centers[1:])]
    return names, bounds


def rebuild(boxes, colnames, bounds, seq_expected=None):
    licenses = [(t, x, y) for t, x, y, w, h in boxes if LICENSE_RE.match(t.strip())]
    if not licenses:
        return [], {}

    # 证号在绝大多数名单里靠右且 x 稳定，取众数 x 作为该列定位参考
    xs = [x for _, x, _ in licenses]
    lic_x = statistics.median(xs)
    anchors = sorted(y for _, x, y in licenses if abs(x - lic_x) < 60)
    if len(anchors) < 3:
        anchors = sorted(y for _, _, y in licenses)

    diffs = [b - a for a, b in zip(anchors, anchors[1:]) if 15 < b - a < 120]
    pitch = statistics.median(diffs) if diffs else 35.0

    # 用锚点建立完整行网格：以第一个锚点为基准，向前后按 pitch 扩展
    base = anchors[0]
    grid = []
    # 向上扩展（首行可能没有证号）
    k = 1
    while base - k * pitch > 100:
        grid.append(base - k * pitch)
        k += 1
    grid = sorted(grid)
    for a in anchors:
        grid.append(a)
    # 向下扩展
    k = 1
    last = anchors[-1]
    ymax = max(y for _, _, y, _, _ in boxes)
    while last + k * pitch < ymax:
        grid.append(last + k * pitch)
        k += 1
    grid = sorted(set(round(g, 1) for g in grid))

    # 合并过近的网格行（重叠切片可能重复识别）
    merged = []
    for g in grid:
        if not merged or g - merged[-1] > pitch * 0.5:
            merged.append(g)
    grid = merged

    rows = [dict() for _ in grid]
    for t, x, y, w, h in boxes:
        t = t.strip()
        if not t:
            continue
        # 跳过表头块
        if any(t == n or (len(t) < 12 and t in n) for n in colnames):
            continue
        # 跳过整页标题、注释行
        if len(t) > 45 or t.startswith("（截至") or "许可情况统计表" in t or "获得互联网新闻信息" in t:
            continue
        xc = x + w / 2  # 用块中心判断所属列，长文本起点偏左也不影响
        ci = 0
        for i, b in enumerate(bounds):
            if xc >= b:
                ci = i + 1
        if ci >= len(colnames):
            ci = len(colnames) - 1
        # 找最近的网格行
        best, bestd = None, 1e9
        ym = y + h / 2
        for ri, gy in enumerate(grid):
            d = abs(ym - gy)
            if d < bestd:
                best, bestd = ri, d
        if best is None or bestd > pitch * 0.8:
            continue
        col = colnames[ci]
        cur = rows[best].get(col, "")
        rows[best][col] = (cur + t) if cur else t

    meta = {"pitch": pitch, "rows": len(grid), "license_anchors": len(anchors)}
    return rows, meta


UNICODE_DIGITS = str.maketrans("０１２３４５６７８９", "0123456789")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("box")
    ap.add_argument("--cols", default="序号,单位名称,许可证编号,单位性质,服务类别")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    boxes = load(args.box)
    if not boxes:
        sys.exit("无有效 OCR 数据")

    colnames = args.cols.split(",")
    guess = guess_columns(boxes)
    if guess:
        detected, bounds = guess
        # 检测到的列名可能与预期顺序不同，以检测结果为准
        colnames = detected
    else:
        sys.exit("无法从表头推断列结构，请用 --cols 手工指定列顺序并检查 OCR 结果")

    rows, meta = rebuild(boxes, colnames, bounds)
    rows = [r for r in rows if r.get("许可证编号") or r.get("单位名称")]

    print(f"列结构: {colnames}", file=sys.stderr)
    print(f"行距: {meta['pitch']:.1f}px | 网格行: {meta['rows']} | 证号锚点: {meta['license_anchors']}", file=sys.stderr)
    print(f"重建记录: {len(rows)}", file=sys.stderr)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=2)
        print(f"已写出 {args.out}", file=sys.stderr)
    else:
        for r in rows[:10]:
            print(r)


if __name__ == "__main__":
    main()
