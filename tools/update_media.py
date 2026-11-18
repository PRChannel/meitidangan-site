#!/usr/bin/env python3
"""单媒体维护工具：针对资质库（data/public-records.json）中个别记录做查找与域名修正。

背景：批量入库走 ingest_province_rows.py / ingest_cac_records.py；行业媒体单条走
import_industry.py（单行 JSON 即可）。本工具只处理"已有记录的个别修正"，两类典型场景：

1. 媒体换域名（名单登记旧域，实际用新域）：add-alt
   例：潮新闻，名单登记 www.tianmunews.com，实际使用 tidenews.com.cn
       python3 tools/update_media.py add-alt --rid CN-ZJ-202606-WEB-105 \
         --domain tidenews.com.cn --method "首页标题+301跳转核验" --write
   记录原则：登记域名照抄官方名单原文不动；新域写入 alt_domains，并自动生成
   域名变更说明（含核验日期与方法）。build_domain_index.py 会把 alt_domains
   的 apex（与登记域不同时）补进域名索引，条目带 unlisted=true。

2. 转录纠错（名单原文如此，但当时 OCR/录入读错了）：set-domain
   例：证号漏印一位、域名误读 1↔l
       python3 tools/update_media.py set-domain --rid CN-XX-...-WEB-n \
         --domain 正确域名 --note "原图放大复读确认，xxx" --write
   要求 --note 写明核验依据；旧值自动存入 domain_correction 字段留痕。

其他子命令：
  find <关键词>   按域名/名称/证号/记录编号模糊查找，确认 rid 后再做修改

不修改名单统计日期（list_as_of）、来源与证据字段——那是名单版本的事实，不因
后续核验变更。需要换名单版本走批量入库。
"""
import argparse
import collections
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "public-records.json"
DOMAIN_RE = re.compile(
    r"^(?=.{4,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z]{2,}$|^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.(?:com|net|org|gov|edu|cn)\.cn$")


def norm_domain(d):
    d = (d or "").strip().lower()
    d = re.sub(r"^https?://", "", d).split("/")[0].split(":")[0]
    if not DOMAIN_RE.match(d):
        sys.exit(f"域名格式不合法：{d!r}")
    return d


def load():
    raw = DATA.read_text(encoding="utf-8")
    return json.loads(raw, object_pairs_hook=collections.OrderedDict), raw


def save(data):
    blob = json.dumps(data, ensure_ascii=False, separators=(", ", ": "))
    DATA.write_text(blob, encoding="utf-8")
    print(f"已写回 {DATA}（{len(blob)} 字符）")
    print("下一步：python3 build_domain_index.py && python3 build_site.py，然后提交。")


def find_record(data, rid):
    for r in data["records"]:
        if r["record_id"].lower() == rid.lower():
            return r
    sys.exit(f"未找到记录编号 {rid}（用 find 子命令确认编号）")


def show(r):
    keys = ["record_id", "name", "region", "license_number", "registered_domains",
            "alt_domains", "list_as_of", "source_url"]
    print(json.dumps({k: r.get(k) for k in keys}, ensure_ascii=False, indent=1))


def cmd_find(args):
    data, _ = load()
    q = args.query.strip().lower()
    hits = [r for r in data["records"] if q in json.dumps(
        {k: r.get(k) for k in ("record_id", "name", "license_number",
                               "registered_domains", "alt_domains",
                               "registered_addresses_raw")}, ensure_ascii=False).lower()]
    print(f"命中 {len(hits)} 条：")
    for r in hits[:20]:
        show(r)


def cmd_add_alt(args):
    data, _ = load()
    r = find_record(data, args.rid)
    d = norm_domain(args.domain)
    if d in r["registered_domains"] or d in (r.get("alt_domains") or []):
        sys.exit(f"{d} 已在该记录的 registered_domains/alt_domains 中，无需重复添加")
    if d in [x for rr in data["records"] if rr is not r for x in rr["registered_domains"]]:
        print("警告：该域名出现在其他记录的登记域名中，请人工确认归属再继续（--force 跳过）")
        if not args.force:
            sys.exit(1)
    r.setdefault("alt_domains", []).append(d)
    today = date.today().isoformat()
    method = args.method or "人工核验"
    note = args.note or (f"官方名单登记 {'、'.join(r['registered_domains'])}；"
                         f"该媒体现实际使用 {d}（{method}，{today} 核验）。"
                         "登记域名照抄官方名单原文，不随实际使用变更。")
    r["alt_domains_note"] = note
    show(r)
    if not args.write:
        print("\n（预览模式，未写盘；确认无误后加 --write）")
        return
    save(data)


def cmd_set_domain(args):
    data, _ = load()
    r = find_record(data, args.rid)
    d = norm_domain(args.domain)
    if not args.note:
        sys.exit("set-domain 是对名单转录的修正，必须用 --note 写明核验依据（如：原图放大复读确认）")
    old = {"domains": r["registered_domains"], "raw": r.get("registered_addresses_raw")}
    r["registered_domains"] = [d] if len(r["registered_domains"]) <= 1 else (
        [d] + r["registered_domains"][1:])
    if r.get("registered_addresses_raw") and len(r["registered_domains"]) == 1:
        r["registered_addresses_raw"] = re.sub(
            r"[a-z0-9.-]+\.[a-z.]{2,}", d, r["registered_addresses_raw"], flags=re.I)
    r.setdefault("domain_correction", []).append({
        "old": old, "new": r["registered_domains"],
        "note": args.note, "date": date.today().isoformat()})
    show(r)
    if not args.write:
        print("\n（预览模式，未写盘；确认无误后加 --write）")
        return
    save(data)


def main():
    ap = argparse.ArgumentParser(description="单媒体记录查找与域名修正")
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("find", help="按关键词查找记录")
    f.add_argument("query")
    a = sub.add_parser("add-alt", help="登记域名不变，补记实际使用域名（媒体换域）")
    a.add_argument("--rid", required=True)
    a.add_argument("--domain", required=True)
    a.add_argument("--method", help="核验方式，如：首页标题+301跳转核验")
    a.add_argument("--note", help="自定义变更说明（默认自动生成）")
    a.add_argument("--force", action="store_true")
    a.add_argument("--write", action="store_true", help="真正写盘")
    s = sub.add_parser("set-domain", help="修正名单转录错误（须 --note 留痕）")
    s.add_argument("--rid", required=True)
    s.add_argument("--domain", required=True)
    s.add_argument("--note", required=True)
    s.add_argument("--write", action="store_true")
    args = ap.parse_args()
    {"find": cmd_find, "add-alt": cmd_add_alt, "set-domain": cmd_set_domain}[args.cmd](args)


if __name__ == "__main__":
    main()
