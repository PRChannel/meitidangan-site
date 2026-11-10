#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""管线编排 CLI。

用法（在仓库根目录执行）：
    python3 -m tools.pipeline extract pending/tianjin_20260930_m01.png \
        --cols 序号,服务名称,服务地址,许可证编号 --out /tmp/tj_web.json

    # 与公告口径核对
    python3 -m tools.pipeline check /tmp/tj_web.json --expect 网站=10

说明：
- 多图按顺序处理；每行带来源图片名（_src），便于回溯与定点复 OCR；
- 每张图先全局横线、再逐行带检测竖线（竖线不贯通时不会漏列）；
- 所有格级 OCR 结果缓存于 .build/cache/ocr/，重跑同一图零成本；
- 只产出行数据，不改 data/；入库仍走 tools/ingest_province_rows.py。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import grid, ocr, rows as R


def extract_images(paths: list[str], scale: int = 3, min_band_h: int = 12,
                   thresh: int = 180, dark_frac: float = 0.55,
                   cols: list[str] | None = None, skip_header: bool = True) -> dict:
    all_rows: list[list[str]] = []
    meta: list[dict] = []
    for p in paths:
        gray = grid.load_gray(p)
        bs = grid.bands(gray, thresh, dark_frac, min_band_h)
        abands = grid.align_bands(bs, gray.shape[1])
        band_cells = []
        for b in abands:
            texts = []
            for c in b["cells"]:
                text = ocr.ocr_region(p, c, scale=scale)
                texts.append({"cols": c["cols"], "ncols": b["ncols"], "text": text})
            band_cells.append(texts)
            meta.append({"image": Path(p).name, "y0": b["y0"], "y1": b["y1"],
                         "cols": b["ncols"]})
        for row in R.assemble_rows(band_cells, skip_header=skip_header):
            all_rows.append(row)
    columns = cols or []
    out = {
        "columns": columns,
        "rows": R.to_dicts(all_rows, columns) if columns else all_rows,
        "raw_rows": all_rows,
        "bands": meta,
        "counts": {"images": len(paths), "bands": len(meta), "rows": len(all_rows)},
    }
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(prog="tools.pipeline", description="公告图 → 结构化行")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("extract", help="图片 → rows.json")
    p1.add_argument("images", nargs="+")
    p1.add_argument("--cols", default="", help="逗号分隔列名；不给则只出 raw_rows")
    p1.add_argument("--out", default="")
    p1.add_argument("--scale", type=int, default=3)
    p1.add_argument("--min-band-h", type=int, default=12)
    p1.add_argument("--thresh", type=int, default=180)
    p1.add_argument("--dark-frac", type=float, default=0.55)
    p1.add_argument("--keep-header", action="store_true")

    p2 = sub.add_parser("check", help="对 rows.json 跑口径/格式校验")
    p2.add_argument("rows_file")
    p2.add_argument("--expect", action="append", default=[], help="如 网站表=10")

    a = ap.parse_args(argv)

    if a.cmd == "extract":
        cols = [c for c in a.cols.split(",") if c] if a.cols else None
        out = extract_images(a.images, scale=a.scale, min_band_h=a.min_band_h,
                             thresh=a.thresh, dark_frac=a.dark_frac,
                             cols=cols, skip_header=not a.keep_header)
        text = json.dumps(out, ensure_ascii=False, indent=1)
        if a.out:
            Path(a.out).write_text(text, encoding="utf-8")
            print(f"行数 {out['counts']['rows']}，带 {out['counts']['bands']}，"
                  f"输出 {a.out}")
        else:
            print(text[:4000])
        return

    if a.cmd == "check":
        data = json.loads(Path(a.rows_file).read_text(encoding="utf-8"))
        rws = data["rows"] if isinstance(data, dict) and "rows" in data else data
        columns = data.get("columns", []) if isinstance(data, dict) else []
        expect = {}
        for e in a.expect:
            k, v = e.split("=", 1)
            expect[k] = int(v)
        problems = R.run_checks(rws, columns, expect or None)
        if problems:
            for kind, items in problems.items():
                for it in items:
                    print(f"[{kind}] {it}")
            sys.exit(1)
        print(f"校验通过：{len(rws)} 行，无异常")
        return


if __name__ == "__main__":
    main()
