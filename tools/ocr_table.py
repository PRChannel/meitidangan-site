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


HEADER_WORDS = [
    "序号", "单位名称", "网站名称", "名称", "许可证编号", "许可证号", "许可编号",
    "单位性质", "服务类别", "服务形式", "域名", "网址", "属地", "所在地",
]


def guess_columns(boxes):
    """按表头关键词识别表头行：同一水平层里含 ≥3 个表头词的视为表头。"""
    if not boxes:
        return None
    cand = [b for b in boxes if b[2] < 400 and len(b[0].strip()) <= 12]
    if len(cand) < 3:
        return None
    cand.sort(key=lambda b: b[2])
    clusters = []
    for b in cand:
        if clusters and abs(b[2] - clusters[-1][0][2]) <= 18:
            clusters[-1].append(b)
        else:
            clusters.append([b])

    best, best_hits = None, 0
    for c in clusters:
        hits = sum(1 for b in c if any(w in b[0] for w in HEADER_WORDS))
        if hits > best_hits:
            best, best_hits = c, hits
    if best is None or best_hits < 3:
        return None

    best.sort(key=lambda b: b[1] + b[3] / 2)
    names = [b[0].strip() for b in best]
    centers = [b[1] + b[3] / 2 for b in best]
    bounds = [int((a + b) / 2) for a, b in zip(centers, centers[1:])]
    return names, bounds


NATURE_WORDS = [
    "事业单位法人", "企业法人", "其他法人", "社会团体法人",
    "民办非企业单位", "企业非法人", "机关法人", "群众团体",
]


def split_merged(boxes):
    """Vision 会把相邻两格的文字合并成一个块（如「XX中心 事业单位法人」）。
    这里按已知的「单位性质」枚举词把这类块拆成两块，右块按字符宽度推算出 x。"""
    out = []
    for t, x, y, w, h in boxes:
        hit = None
        for nw in NATURE_WORDS:
            i = t.find(nw)
            if i > 0:
                hit = (i, nw)
                break
        if not hit:
            out.append((t, x, y, w, h))
            continue
        i, nw = hit
        cw = w / max(len(t), 1)
        left, right = t[:i].strip(), t[i:]
        if left:
            out.append((left, x, y, int(cw * i), h))
        out.append((right, int(x + cw * i), y, int(cw * (len(t) - i)), h))
    return out


def dedupe(boxes, y_tol=26):
    """去掉切片重叠造成的重复识别：同样文本、x 接近、y 相差小于行距一半的块只留一个。"""
    kept = []
    for b in sorted(boxes, key=lambda z: (z[2], z[1])):
        t, x, y, w, h = b
        dup = False
        for k in reversed(kept[-40:]):
            if k[0] == t and abs(k[1] - x) < 8 and abs(k[2] - y) < y_tol:
                dup = True
                break
        if not dup:
            kept.append(b)
    return kept


def rebuild(boxes, colnames, bounds):
    """以 11 位许可证号为行锚点：每个文本块就近归到某一个锚点行，再按 x 归列。"""
    licenses = [b for b in boxes if LICENSE_RE.match(b[0].strip())]
    if not licenses:
        return [], {}

    # 证号列定位：取 x 中位数，剔除明显偏左的误识别
    xs = [x + w / 2 for _, x, _, w, _ in licenses]
    lic_x = statistics.median(xs)
    anchors = sorted({
        round(b[2] + b[4] / 2)
        for b in licenses
        if abs(b[1] + b[3] / 2 - lic_x) < 60
    })
    if len(anchors) < 3:
        anchors = sorted({round(b[2] + b[4] / 2) for b in licenses})

    # 合并相邻过近的锚点（同一行被识别出两个证号块）
    merged = []
    for a in anchors:
        if not merged or a - merged[-1] > 20:
            merged.append(a)
    anchors = merged

    diffs = [b - a for a, b in zip(anchors, anchors[1:]) if 20 < b - a < 200]
    pitch = statistics.median(diffs) if diffs else 40.0

    rows = [dict() for _ in anchors]
    for t, x, y, w, h in boxes:
        t = t.strip()
        if not t:
            continue
        if any(t == n or (len(t) < 12 and t in n) for n in colnames):
            continue
        if len(t) > 45 or t.startswith("（截至") or "许可情况统计表" in t or "获得互联网新闻信息" in t:
            continue
        xc = x + w / 2
        ci = 0
        for i, b in enumerate(bounds):
            if xc >= b:
                ci = i + 1
        if ci >= len(colnames):
            ci = len(colnames) - 1
        ym = y + h / 2
        ri, rd = None, 1e9
        for i, a in enumerate(anchors):
            d = abs(ym - a)
            if d < rd:
                ri, rd = i, d
        if ri is None or rd > pitch * 0.95:
            continue
        col = colnames[ci]
        rows[ri].setdefault(col, []).append((ym, x, t))

    out = []
    for r in rows:
        fixed = {}
        for col, frags in r.items():
            frags.sort(key=lambda z: (z[0], z[1]))
            fixed[col] = "".join(f[2] for f in frags)
        out.append(fixed)

    meta = {"pitch": pitch, "rows": len(anchors), "license_anchors": len(anchors)}
    return out, meta


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
    raw_n = len(boxes)
    boxes = dedupe(boxes)
    boxes = split_merged(boxes)
    print(f"OCR 块: {raw_n} → 去重/拆格后 {len(boxes)}", file=sys.stderr)

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
