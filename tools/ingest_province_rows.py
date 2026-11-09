#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把已核验的省级名单行注入公开记录。

用法（预览）：
    python3 tools/ingest_province_rows.py rows.json --province 河南 \
        --prefix CN-HN-202603-WEB --source-url https://... --list-as-of 2026-03-31 \
        --source-published-at 2026-04-22 --issuing 河南省互联网信息办公室 \
        --evidence-method ocr_image_recognition_domain_http_checked

加 --write 才写盘。默认只处理 _状态 为「已核验」的行。

校验项：
- 许可证号 11 位；域名非空且格式合法
- 与现有记录（名称 + 证号 + 域名）零重复
- 记录编号唯一
"""
import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "public-records.json"
COVERAGE = ROOT / "data" / "coverage.json"

DOMAIN_RE = re.compile(r"^[a-z0-9][a-z0-9.\-]*\.[a-z]{2,}$", re.I)


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rows")
    ap.add_argument("--province", required=True)
    ap.add_argument("--prefix", required=True, help="记录编号前缀，如 CN-HN-202603-WEB")
    ap.add_argument("--source-url", required=True)
    ap.add_argument("--list-as-of", required=True)
    ap.add_argument("--source-published-at", default="")
    ap.add_argument("--issuing", required=True)
    ap.add_argument("--evidence-method", required=True)
    ap.add_argument("--evidence-id", default="", help="默认用记录编号")
    ap.add_argument("--evidence-sha256", default="")
    ap.add_argument("--name-column", default="网站名称")
    ap.add_argument("--domain-column", default="域名")
    ap.add_argument("--operator-column", default="单位名称")
    ap.add_argument("--license-column", default="许可证编号")
    ap.add_argument("--coverage-status", default="")
    ap.add_argument("--coverage-note", default="")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    payload = load(DATA)
    records = payload["records"]
    rows = [r for r in load(args.rows) if r.get("_状态", "已核验") == "已核验"]

    existing_lic = {r["license_number"] for r in records if r.get("license_number")}
    existing_name = {(r["name"], r["region"]) for r in records}
    existing_dom = {d.lower() for r in records for d in (r.get("registered_domains") or [])}
    existing_ids = {r["record_id"] for r in records}

    new = []
    problems = []
    for r in rows:
        name = re.sub(r"\s+", "", (r.get(args.name_column) or "")).strip()
        raw_addr = (r.get(args.domain_column) or "").strip()
        lic = (r.get(args.license_column) or "").strip()
        op = re.sub(r"\s+", "", (r.get(args.operator_column) or "")).strip()
        seq = int(re.sub(r"\D", "", str(r.get("序号", ""))) or 0)

        # 一行可含多个地址（、分隔），地址可带路径；域名取路径前的主机部分
        domains = []
        for part in re.split(r"[、,，]+", raw_addr):
            part = part.strip().lower()
            if not part:
                continue
            host = part.split("/", 1)[0].strip(".")
            if DOMAIN_RE.match(host) and host not in domains:
                domains.append(host)
        if not domains:
            problems.append((f"域名异常 {raw_addr!r}", r))
            continue

        if not name:
            problems.append(("名称缺失", r))
            continue
        if not re.fullmatch(r"\d{11}", lic):
            problems.append((f"证号异常 {lic!r}", r))
            continue
        if (name, args.province) in existing_name:
            problems.append((f"名称重复 {name}", r))
            continue
        clash = [d for d in domains if d in existing_dom]
        if clash:
            problems.append((f"域名重复 {'、'.join(clash)}", r))
            continue

        rid = f"{args.prefix}-{seq:03d}" if seq else f"{args.prefix}-X{len(new)+1:03d}"
        while rid in existing_ids:
            rid += "b"
        existing_ids.add(rid)

        # 每行可带 _证据 覆盖默认证据方式（如同批中"经首页标题核验"与"仅原图复读确认"并存）
        method = (r.get("_证据") or args.evidence_method).strip()

        new.append({
            "record_id": rid,
            "name": name,
            "region": args.province,
            "license_number": lic,
            "registered_addresses_raw": raw_addr,
            "registered_domains": domains,
            "operator_name": op or None,
            "service_type": "互联网站",
            "source_url": args.source_url,
            "source_published_at": args.source_published_at or None,
            "list_as_of": args.list_as_of,
            "verified_at": str(date.today()),
            "evidence_id": args.evidence_id or rid,
            "evidence_sha256": args.evidence_sha256 or None,
            "evidence_method": method,
            "issuing_authority": args.issuing,
            "review_status": "verified_dated_official_record",
            "current_license_validity": "not_independently_confirmed",
        })

    print(f"待注入 {len(new)} 条 / 候选 {len(rows)} 条 / 跳过 {len(problems)} 条")
    for why, r in problems[:15]:
        print(f"  跳过：{why} | {r.get(args.name_column)}")
    if new:
        print("样例：")
        for r in new[:3]:
            print(f"  {r['record_id']} | {r['name']} | {r['registered_domains'][0]} | {r['license_number']} | {r['operator_name']}")

    # 证号在本批次内应唯一（同一单位多个网站时允许重复，但要能解释）
    lic_count = {}
    for r in new:
        lic_count[r["license_number"]] = lic_count.get(r["license_number"], 0) + 1
    dup = {k: v for k, v in lic_count.items() if v > 1}
    if dup:
        print(f"提示：批次内证号重复 {dup}（同一单位多站点时正常）")

    if not args.write:
        print("\n预览模式，未写盘。确认无误后加 --write。")
        return

    payload["records"] = records + new
    payload["generated_at"] = str(date.today())
    DATA.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    cov = load(COVERAGE)
    for c in cov:
        if c["省份"] == args.province:
            c["累计工作候选数"] = str(len(rows))
            c["本轮来源名单已提取行数"] = str(len(rows))
            c["已提取版本统计截至"] = args.list_as_of
            c["对应核对阶段"] = "图片名单OCR提取+域名可访问性核验"
            if args.coverage_status:
                c["覆盖状态"] = args.coverage_status
            if args.coverage_note:
                c["问题与后续"] = args.coverage_note
            break
    COVERAGE.write_text(json.dumps(cov, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"已写入：记录 {len(records)} → {len(payload['records'])}；coverage 已更新")


if __name__ == "__main__":
    main()
