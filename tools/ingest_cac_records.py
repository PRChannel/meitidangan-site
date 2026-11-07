#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把国家网信办两份 PDF 名单（中央新闻单位 194 个 / 其他单位 27 个）注入公开记录。

用法：
    python3 tools/ingest_cac_records.py <194.pdf> <27.pdf> [--write]

不加 --write 时只做校验与预览，不修改任何数据文件。
"""
import argparse
import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "public-records.json"
COVERAGE = ROOT / "data" / "coverage.json"
SOURCES_CSV = ROOT / "data" / "official-sources.csv"

sys.path.insert(0, str(ROOT / "tools"))
from parse_cac_pdf import extract_lines, parse  # noqa: E402

SOURCES = {
    "central": {
        "url": "https://www.cac.gov.cn/2026-07/22/c_1786465606229121.htm",
        "title": "获得互联网新闻信息服务许可的互联网站名单（共194个）",
        "prefix": "CN-CENTRAL-202607-WEB",
        "evidence_prefix": "ECAC194",
        "issuing": "中央新闻单位",
        "expected": 194,
    },
    "other": {
        "url": "https://www.cac.gov.cn/2026-07/22/c_1786464870990651.htm",
        "title": "获得互联网新闻信息服务许可的互联网站名单（共27个）",
        "prefix": "CN-OTHER-202607-WEB",
        "evidence_prefix": "ECAC027",
        "issuing": "国家网信办许可的其他单位",
        "expected": 27,
    },
}


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_records(pdf_path, meta, verified_at):
    lines, pages = extract_lines(str(pdf_path))
    rows = parse(lines)

    # 完整性校验：条数、序号连续、字段齐全、证号格式
    assert len(rows) == meta["expected"], (
        f"{meta['issuing']} 解析条数 {len(rows)} != 名单标注 {meta['expected']}"
    )
    seqs = [r["seq"] for r in rows]
    assert seqs == list(range(1, meta["expected"] + 1)), f"{meta['issuing']} 序号不连续"
    bad = [r for r in rows if not r["license_number"] or not r["registered_domains"]]
    assert not bad, f"{meta['issuing']} 字段缺失：{bad[:3]}"
    assert all(re.fullmatch(r"\d{11}", r["license_number"]) for r in rows), "许可证号格式异常"

    digest = sha256_of(pdf_path)
    out = []
    for r in rows:
        out.append(
            {
                "record_id": f"{meta['prefix']}-{r['seq']:03d}",
                "name": r["name"],
                "region": "中央",
                "license_number": r["license_number"],
                "registered_addresses_raw": r["registered_addresses_raw"],
                "registered_domains": r["registered_domains"],
                "operator_name": None,
                "service_type": "互联网站",
                "source_url": meta["url"],
                "source_published_at": "2026-07-22",
                "list_as_of": "2026-07-22",
                "verified_at": verified_at,
                "evidence_id": f"{meta['evidence_prefix']}-{r['seq']:03d}",
                "evidence_sha256": digest,
                "evidence_method": "pdf_text_extraction_sequential_check",
                "issuing_authority": meta["issuing"],
                "review_status": "verified_dated_official_record",
                "current_license_validity": "not_independently_confirmed",
            }
        )
    return out, digest, pages


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf194")
    ap.add_argument("pdf27")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--date", default=date.today().isoformat())
    args = ap.parse_args()

    payload = json.loads(DATA.read_text(encoding="utf-8"))
    existing = payload["records"]
    existing_ids = {r["record_id"] for r in existing}

    central, d1, p1 = build_records(args.pdf194, SOURCES["central"], args.date)
    other, d2, p2 = build_records(args.pdf27, SOURCES["other"], args.date)
    new = central + other

    # 去重：编号、名称、域名三个维度都不能与既有记录冲突
    old_lic = {r["license_number"] for r in existing if r.get("license_number")}
    old_name = {r["name"] for r in existing}
    old_dom = {d.lower() for r in existing for d in (r.get("registered_domains") or [])}
    dup = [
        r["record_id"]
        for r in new
        if r["license_number"] in old_lic
        or r["name"] in old_name
        or any(d.lower() in old_dom for d in r["registered_domains"])
        or r["record_id"] in existing_ids
    ]
    assert not dup, f"与既有记录冲突：{dup[:5]}"

    print(f"中央新闻单位：{len(central)} 条（PDF {p1} 页，SHA256 {d1[:16]}…）")
    print(f"其他单位　　：{len(other)} 条（PDF {p2} 页，SHA256 {d2[:16]}…）")
    print(f"新增合计　　：{len(new)} 条；既有 {len(existing)} 条 → 合并后 {len(existing) + len(new)} 条")
    dom_total = sum(len(r["registered_domains"]) for r in new)
    print(f"新增登记域名：{dom_total} 个")

    if not args.write:
        print("\n[预览模式] 未写入。加 --write 执行写入。")
        return 0

    merged = existing + new
    merged.sort(key=lambda r: (r["region"], r["record_id"]))
    payload["records"] = merged
    payload["generated_at"] = args.date
    payload["central_records"] = len(new)
    DATA.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n已写入 {DATA}")

    # coverage 追加中央条目。必须追加到末尾：地区页 URL 由 coverage 顺序决定，
    # 插到前面会让所有已上线的 regions/xx/ 地址整体位移并 404。
    cov = json.loads(COVERAGE.read_text(encoding="utf-8"))
    cov = [c for c in cov if c["省份"] != "中央"]
    cov.append(
        {
            "省份": "中央",
            "累计工作候选数": str(len(new)),
            "本轮来源名单已提取行数": str(len(new)),
            "已提取版本统计截至": "2026-07-22",
            "对应核对阶段": "阶段18",
            "覆盖状态": "国家网信办PDF原件文本提取已校验",
            "问题与后续": "条数与序号连续性已程序校验；PDF版面逐行目视复核未完成",
            "当前完整有效性结论": "未确认，不得据候选数宣称全部现行许可",
        },
    )
    COVERAGE.write_text(json.dumps(cov, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"已更新 {COVERAGE}（新增「中央」覆盖条目）")

    # 来源索引表回填两行实际条数
    text = SOURCES_CSV.read_text(encoding="utf-8-sig")
    text = text.replace(
        "中央新闻单位,2026-07-22,https://www.cac.gov.cn/2026-07/22/c_1786465606229121.htm,,0,另行核对,194项仅文本提取，原PDF版面未复核",
        f"中央新闻单位,2026-07-22,https://www.cac.gov.cn/2026-07/22/c_1786465606229121.htm,https://www.cac.gov.cn/2026-07/22/c_1786465606229121.htm,{len(central)},PDF文本提取已校验,194项条数与序号连续性已程序校验；版面目视复核未完成",
    )
    text = text.replace(
        "国家网信办其他单位,2026-07-22,https://www.cac.gov.cn/2026-07/22/c_1786464870990651.htm,,0,另行核对,27项PDF文本待原件复核，实际入口以证据索引为准",
        f"国家网信办其他单位,2026-07-22,https://www.cac.gov.cn/2026-07/22/c_1786464870990651.htm,https://www.cac.gov.cn/2026-07/22/c_1786464870990651.htm,{len(other)},PDF文本提取已校验,27项条数与序号连续性已程序校验；版面目视复核未完成",
    )
    SOURCES_CSV.write_text(text, encoding="utf-8-sig")
    print(f"已更新 {SOURCES_CSV}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
