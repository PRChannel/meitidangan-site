#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把省级名单里的「其他服务形式」行注入公开记录。

这类记录既不是网站（没有登记域名），也不是许可主体（不是持证单位），
而是名单里按服务形式列出的具体服务项：应用程序、公众账号、论坛、博客、
微博客、即时通信工具、网络直播、其他服务形式。

记录形态：record_kind='service'，service_form 标明具体形式，
name 是服务名称（如「黄河Plus」「“山西新闻网”腾讯微信公众账号」），
operator_name 是名单标注的单位名称，没有域名与地址。

用法（预览）：
    python3 tools/ingest_services.py rows.json --province 山西 \
        --prefix CN-SX-202609-APP --service-form 应用程序 \
        --source-url https://... --list-as-of 2026-09-30 \
        --issuing 山西省互联网信息办公室 \
        --evidence-method official_attachment_text_extraction \
        --evidence-id ESX-APP-20260930 --evidence-sha256 <sha256>

加 --write 才写盘。校验：服务名称非空、证号 11 位、与本批次及库内零重复。
"""
import argparse
import json
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "public-records.json"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rows")
    ap.add_argument("--province", required=True)
    ap.add_argument("--prefix", required=True)
    ap.add_argument("--service-form", required=True, help="应用程序 / 公众账号 / 论坛 / 网络直播 …")
    ap.add_argument("--source-url", required=True)
    ap.add_argument("--list-as-of", required=True)
    ap.add_argument("--source-published-at", default="")
    ap.add_argument("--issuing", required=True)
    ap.add_argument("--evidence-method", required=True)
    ap.add_argument("--evidence-id", required=True)
    ap.add_argument("--evidence-sha256", required=True)
    ap.add_argument("--name-column", default="服务名称")
    ap.add_argument("--operator-column", default="单位名称")
    ap.add_argument("--license-column", default="许可证编号")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    payload = json.loads(DATA.read_text(encoding="utf-8"))
    records = payload["records"]
    rows = json.loads(Path(args.rows).read_text(encoding="utf-8"))

    # 名单里可能同名同证号重复登记（官方原件如此），因此去重只按 record_id，
    # 保证重复执行幂等，同时不吞掉原件中的重复行。
    existing = {
        (r["name"], r["license_number"], r.get("service_form") or "")
        for r in records
        if r.get("record_kind") == "service"
    }
    existing_ids = {r["record_id"] for r in records}

    new, problems = [], []
    for r in rows:
        name = re.sub(r"\s+", "", (r.get(args.name_column) or "")).strip()
        lic = re.sub(r"\D", "", str(r.get(args.license_column) or ""))
        op = re.sub(r"\s+", "", (r.get(args.operator_column) or "")).strip()
        seq = int(re.sub(r"\D", "", str(r.get("序号", ""))) or 0)

        if not name:
            problems.append(("名称缺失", r))
            continue
        if not re.fullmatch(r"\d{11}", lic):
            problems.append((f"证号异常 {lic!r}", r))
            continue
        rid = f"{args.prefix}-{seq:03d}" if seq else f"{args.prefix}-X{len(new)+1:03d}"
        if rid in existing_ids:
            problems.append((f"已导入 {rid}", r))
            continue
        if (name, lic, args.service_form) in existing:
            print(f"  提示：{name} / {lic} 在库内已有同证号记录，原件重复登记，仍按序号 {seq} 收录")
        existing_ids.add(rid)
        existing.add((name, lic, args.service_form))

        new.append({
            "record_id": rid,
            "record_kind": "service",
            "service_form": args.service_form,
            "name": name,
            "region": args.province,
            "license_number": lic,
            "entity_nature": None,
            "service_categories": [args.service_form],
            "registered_addresses_raw": None,
            "registered_domains": [],
            "operator_name": op or None,
            "service_type": args.service_form,
            "source_url": args.source_url,
            "source_published_at": args.source_published_at or None,
            "list_as_of": args.list_as_of,
            "verified_at": str(date.today()),
            "evidence_id": args.evidence_id,
            "evidence_sha256": args.evidence_sha256,
            "evidence_method": args.evidence_method,
            "issuing_authority": args.issuing,
            "review_status": "verified_dated_official_record",
            "current_license_validity": "not_independently_confirmed",
        })

    print(f"待注入 {len(new)} 条{args.service_form} / 候选 {len(rows)} 条 / 跳过 {len(problems)} 条")
    for why, r in problems[:15]:
        print(f"  跳过：{why} | {r.get(args.name_column)}")
    for r in new[:3]:
        print(f"  {r['record_id']} | {r['name']} | {r['operator_name']} | {r['license_number']}")

    if args.write and new:
        records.extend(new)
        DATA.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"已写入：记录 {len(records) - len(new)} → {len(records)}")
    elif not args.write:
        print("预览模式，未写盘。确认无误后加 --write。")


if __name__ == "__main__":
    main()
