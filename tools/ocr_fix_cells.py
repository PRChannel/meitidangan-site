#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""单元格级高倍重识别：对校验不通过的单元格，裁出该格放大后单独 OCR，替换原值。

用法：
    python3 tools/ocr_fix_cells.py <原图> <ocr.box> <rows.json> --col 域名 \
        --pattern '^[a-z0-9.-]+\\.[a-z]{2,}$' --scale 5 --out rows.fixed.json

思路：
1. 用 ocr.box 推断表头列边界与行锚点（与 ocr_table.py 同一套规则）；
2. 逐行检查目标列值是否匹配 pattern，不匹配的裁出该单元格；
3. 调用 /tmp/ocr 放大识别，取识别结果的并集，再按 pattern 过滤；
4. 命中最长匹配则替换，否则保留原值并标记为待人工核对。
"""
import argparse
import json
import re
import socket
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

LICENSE_RE = re.compile(r"^\d{11}$")
HEADER_WORDS = ["序号", "网站名称", "单位名称", "域名", "属地", "许可证编号", "单位性质", "服务类别"]


def load_boxes(path):
    boxes = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) != 5:
                continue
            t, x, y, w, h = parts
            boxes.append((t, int(x), int(y), int(w), int(h)))
    return boxes


def header_bounds(boxes):
    """返回 (列名列表, 列边界 x 列表)。"""
    cand = [b for b in boxes if b[2] < 400 and len(b[0].strip()) <= 12]
    cand.sort(key=lambda b: b[2])
    clusters = []
    for b in cand:
        if clusters and abs(b[2] - clusters[-1][0][2]) <= 18:
            clusters[-1].append(b)
        else:
            clusters.append([b])
    best, hits = None, 0
    for c in clusters:
        h = sum(1 for b in c if any(w in b[0] for w in HEADER_WORDS))
        if h > hits:
            best, hits = c, h
    if not best or hits < 3:
        return None, None, None
    best.sort(key=lambda b: b[1] + b[3] / 2)
    names = [b[0].strip() for b in best]
    centers = [b[1] + b[3] / 2 for b in best]
    bounds = [int((a + b) / 2) for a, b in zip(centers, centers[1:])]
    return names, bounds, centers


def anchors_of(boxes):
    lics = [b for b in boxes if LICENSE_RE.match(b[0].strip())]
    if not lics:
        return [], 40.0
    xs = [b[1] + b[3] / 2 for b in lics]
    mx = statistics.median(xs)
    ys = sorted({round(b[2] + b[4] / 2) for b in lics if abs(b[1] + b[3] / 2 - mx) < 60})
    merged = []
    for y in ys:
        if not merged or y - merged[-1] > 20:
            merged.append(y)
    diffs = [b - a for a, b in zip(merged, merged[1:]) if 20 < b - a < 200]
    pitch = statistics.median(diffs) if diffs else 40.0
    return merged, pitch


def ocr_crop(image, rect, scale, ocr_bin):
    x, y, w, h = rect
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tf:
        out = tf.name
    cmd = [ocr_bin, image, "--crop", f"{x},{y},{w},{h}", "--scale", str(scale)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    Path(out).unlink(missing_ok=True)
    return [l for l in r.stdout.splitlines() if l.strip()]


def best_variant(domain, pat, dns):
    """生成常见 OCR 混淆的修正变体，DNS 能解析的那个即为真值。"""
    base = domain.lower().rstrip(".")
    cands = []

    def add(x):
        if x and x not in cands and pat.match(x):
            cands.append(x)

    add(base)
    for a, b in [("o", "0"), ("l", "1"), ("i", "1"), ("rn", "m")]:
        add(base.replace(a, b))
    add(base.replace("o", "0").replace("l", "1").replace("i", "1"))
    add(re.sub(r"\.comcn$", ".com.cn", base))
    add(re.sub(r"\.con$|\.c0m$|\.corn$", ".com", base))
    add(re.sub(r"\.cm$", ".cn", base))
    add(re.sub(r"\.(c n|cn )$", ".cn", base))

    if not dns:
        return cands[0] if cands else None
    for c in cands:
        try:
            socket.gethostbyname(c)
            return c
        except Exception:
            continue
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("box")
    ap.add_argument("rows")
    ap.add_argument("--col", required=True)
    ap.add_argument("--pattern", required=True)
    ap.add_argument("--scale", type=float, default=5.0)
    ap.add_argument("--ocr-bin", default="/tmp/ocr2")
    ap.add_argument("--dns", action="store_true", help="同时要求域名能解析，作为真实性校验")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    boxes = load_boxes(args.box)
    names, bounds, centers = header_bounds(boxes)
    if not names or args.col not in names:
        sys.exit(f"表头里没有列 {args.col}；检测到 {names}")
    ci = names.index(args.col)
    # 该列的 x 范围
    left = 0 if ci == 0 else bounds[ci - 1]
    right = centers[-1] + 60 if ci == len(names) - 1 else bounds[ci]
    if ci == len(names) - 1:
        right = max(b[1] + b[3] for b in boxes)

    anchors, pitch = anchors_of(boxes)
    rows = json.loads(Path(args.rows).read_text(encoding="utf-8"))
    pat = re.compile(args.pattern, re.I)

    def ok(val):
        if not val:
            return False
        for part in val.split("、"):
            part = part.strip()
            if not part or not pat.match(part):
                return False
            if args.dns:
                try:
                    socket.gethostbyname(part)
                except Exception:
                    return False
        return True

    fixed = unchanged = failed = 0
    for i, row in enumerate(rows):
        val = (row.get(args.col) or "").strip()
        if ok(val):
            unchanged += 1
            continue
        if i >= len(anchors):
            failed += 1
            continue
        y0 = int(anchors[i] - pitch * 0.55)
        h = int(pitch * 1.1)
        text = " ".join(ocr_crop(args.image, (left, y0, right - left, h), args.scale, args.ocr_bin))
        raw = []
        for c in re.split(r"[^\w.\-]+", text):
            c = c.strip(".")
            if c and pat.match(c) and c not in raw:
                raw.append(c)
        # 候选变体：修正常见 OCR 混淆，再用 DNS 确认
        resolved = []
        for c in raw:
            v = best_variant(c, pat, args.dns)
            if v and v not in resolved:
                resolved.append(v)
        if resolved:
            best = "、".join(resolved)
            print(f"  行{i+1}: {val!r} → {best!r}", file=sys.stderr)
            row[args.col] = best
            fixed += 1
        else:
            print(f"  行{i+1}: {val!r} 重识别失败（原文 {text!r}）", file=sys.stderr)
            row["_待核"] = True
            failed += 1

    print(f"合规 {unchanged} | 修复 {fixed} | 失败 {failed}", file=sys.stderr)
    out = args.out or args.rows
    Path(out).write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已写出 {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
