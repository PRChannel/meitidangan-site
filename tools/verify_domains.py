#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""域名核验：访问名单里登记的域名，用首页标题判断是否是同一家网站。

用法：
    python3 tools/verify_domains.py <rows.json> --name-column 网站名称 --domain-column 域名 \
        --out verified.json

输出：在原行上追加 _核验（reachable / title_match / mismatch / unreachable）与 _标题。
判断规则（宽松，只用于筛掉明显错误的 OCR 结果）：
- 首页 HTTP 2xx/3xx 视为可达；
- 标题里出现网站名称去掉「网/在线/频道」等后缀后的前 2-4 个字，视为同一站点；
- 可达但标题不含站点名 → mismatch，交人工判断（可能是改版或别名）。
"""
import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

import subprocess

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

SUFFIX = ["在线", "新闻", "频道", "网站", "网", "在线网"]


def core(name):
    n = re.sub(r"[（(].*?[)）]", "", name).strip()
    for s in sorted(SUFFIX, key=len, reverse=True):
        if n.endswith(s) and len(n) > len(s) + 1:
            n = n[: -len(s)]
            break
    return n


def fetch(url, timeout=12):
    try:
        r = subprocess.run(
            ["curl", "-sSL", "-m", str(timeout), "-A", UA, "-o", "-", "-w", "\n@@%{http_code}@@", url],
            capture_output=True, text=True, errors="ignore",
        )
        body, _, tail = r.stdout.rpartition("\n@@")
        code = tail.replace("@@", "").strip()
        return code, body
    except Exception:
        return "000", ""


def check(row, name_col, dom_col):
    host = (row.get(dom_col) or "").split("、")[0].strip().lower()
    name = (row.get(name_col) or "").strip()
    if not host:
        row["_核验"], row["_标题"] = "no_domain", ""
        return row
    code, body = "000", ""
    for scheme in ("http://", "https://"):
        code, body = fetch(scheme + host)
        if code.startswith(("2", "3")):
            break
    if not code.startswith(("2", "3")):
        row["_核验"], row["_标题"] = "unreachable", ""
        return row
    m = re.search(r"<title[^>]*>(.*?)</title>", body, re.S | re.I)
    title = re.sub(r"\s+", " ", m.group(1)).strip() if m else ""
    row["_标题"] = title[:60]
    c = core(name)
    hit = c and c[:2] in title
    row["_核验"] = "title_match" if hit else "mismatch"
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rows")
    ap.add_argument("--name-column", default="网站名称")
    ap.add_argument("--domain-column", default="域名")
    ap.add_argument("--out", default=None)
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    rows = json.loads(Path(args.rows).read_text(encoding="utf-8"))
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        rows = list(ex.map(lambda r: check(r, args.name_column, args.domain_column), rows))

    stat = {}
    for r in rows:
        stat[r["_核验"]] = stat.get(r["_核验"], 0) + 1
    for r in rows:
        if r["_核验"] != "title_match":
            print(f"  {r['_核验']:<12} {(r.get(args.domain_column) or '')[:26]:<28} "
                  f"{(r.get(args.name_column) or '')[:16]:<18} {r.get('_标题','')[:30]}", file=sys.stderr)
    print("核验统计:", stat, file=sys.stderr)

    out = args.out or args.rows
    Path(out).write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已写出 {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
