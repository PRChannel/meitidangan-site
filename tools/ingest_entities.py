#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把省级名单里的「服务主体」行（单位+性质+服务类别+证号，无域名）注入公开记录。

服务主体与网站服务是两类记录：主体是许可持有单位，网站是其许可下的具体服务项。
同一许可证号下可以既有主体记录又有若干网站记录，两者不互相替代。

用法（预览）：
    python3 tools/ingest_entities.py rows.json --province 山西 \
        --prefix CN-SX-202609-ORG --source-url https://... --list-as-of 2026-09-30 \
        --issuing 山西省互联网信息办公室 \
        --evidence-method official_attachment_text_extraction \
        --evidence-id ESX-ORG-20260930 --evidence-sha256 <sha256>

加 --write 才写盘。校验：单位名称非空、证号 11 位、与现有主体记录零重复。
"""
import argparse
import json
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "public-records.json"
COVERAGE = ROOT / "data" / "coverage.json"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rows")
    ap.add_argument("--province", required=True)
    ap.add_argument("--prefix", required=True)
    ap.add_argument("--source-url", required=True)
    ap.add_argument("--list-as-of", required=True)
    ap.add_argument("--source-published-at", default="")
    ap.add_argument("--issuing", required=True)
    ap.add_argument("--evidence-method", required=True)
    ap.add_argument("--evidence-id", required=True)
    ap.add_argument("--evidence-sha256", required=True)
    ap.add_argument("--name-column", default="单位名称")
    ap.add_argument("--nature-column", default="单位性质")
    ap.add_argument("--category-column", default="服务类别")
    ap.add_argument("--license-column", default="许可证编号")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    payload = json.loads(DATA.read_text(encoding="utf-8"))
    records = payload["records"]
    rows = json.loads(Path(args.rows).read_text(encoding="utf-8"))

    existing = {
        (r["name"], r["license_number"])
        for r in records
        if r.get("record_kind") == "entity"
    }
    existing_ids = {r["record_id"] for r in records}

    new, problems = [], []
    for r in rows:
        name = re.sub(r"\s+", "", (r.get(args.name_column) or "")).strip()
        lic = re.sub(r"\D", "", str(r.get(args.license_column) or ""))
        nature = re.sub(r"\s+", "", (r.get(args.nature_column) or "")).strip()
        cats = [
            c.strip()
            for c in re.split(r"[、,，;；]+", r.get(args.category_column) or "")
            if c.strip()
        ]
        seq = int(re.sub(r"\D", "", str(r.get("序号", ""))) or 0)

        if not name:
            problems.append(("名称缺失", r))
            continue
        if not re.fullmatch(r"\d{11}", lic):
            problems.append((f"证号异常 {lic!r}", r))
            continue
        if (name, lic) in existing:
            problems.append((f"主体重复 {name}", r))
            continue
        rid = f"{args.prefix}-{seq:03d}" if seq else f"{args.prefix}-X{len(new)+1:03d}"
        while rid in existing_ids:
            rid += "b"
        existing_ids.add(rid)
        existing.add((name, lic))

        new.append({
            "record_id": rid,
            "record_kind": "entity",
            "name": name,
            "region": args.province,
            "license_number": lic,
            "entity_nature": nature or None,
            "service_categories": cats,
            "registered_addresses_raw": None,
            "registered_domains": [],
            "operator_name": None,
            "service_type": "许可主体",
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

    print(f"待注入 {len(new)} 条主体 / 候选 {len(rows)} 条 / 跳过 {len(problems)} 条")
    for why, r in problems[:15]:
        print(f"  跳过：{why} | {r.get(args.name_column)}")
    for r in new[:3]:
        print(f"  {r['record_id']} | {r['name']} | {r['license_number']} | {r['entity_nature']}")

    if args.write and new:
        records.extend(new)
        if args.province != "中央":
            for c in json.loads(COVERAGE.read_text(encoding="utf-8")):
                pass  # coverage 由调用方按需更新，工具不擅自改文案
        DATA.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"已写入：记录 {len(records) - len(new)} → {len(records)}")
    elif not args.write:
        print("预览模式，未写盘。确认无误后加 --write。")


if __name__ == "__main__":
    main()
