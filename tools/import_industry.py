#!/usr/bin/env python3
"""行业媒体收录：把调研批次合并进 data/industry-media.csv。

用法：
  python3 tools/import_industry.py 批次.json [--tier L2] [--source "..."] [--write]

批次 JSON 结构：{"meta":{...},"items":[{"name","sector","industry","domain","note",
                                        "http_status"(可选),"probe_url"(可选)}]}

规则：
- 主域归一后查重（apex 相同视为同一媒体），名称归一后二次查重（防同媒体换域名）；
- 编号按 tier 续号（IM-L2-083 之后继续），编号与域名解耦，媒体换域名只改 domain；
- sector 必须落在 16 类固定枚举内，否则报错（不静默写入）；
- 默认不落盘，加 --write 才写 CSV。
"""
import argparse
import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "data" / "industry-media.csv"
sys.path.insert(0, str(ROOT))
from build_domain_index import apex_of  # noqa: E402

SECTORS = {
    # 18 类对齐发稿平台常用行业树（2026-11-18 迁移，见 tools/migrate_sector_pr.py）
    "IT科技", "财经金融", "新闻资讯", "健康医疗", "汽车行业", "留学教育",
    "家装家居", "房产行业", "生活消费", "酒店旅游", "女性时尚", "游戏行业",
    "娱乐影视", "文化艺术", "亲子母婴", "贸易能源", "食品餐饮", "体育运动",
    # 7 个发稿树装不下的补充类
    "工业制造", "建筑基建", "交通物流", "农业养殖", "政务公益", "政法法治", "军事国防",
}
FIELDS = ["id", "tier", "name", "sector", "industry", "domain", "http_status", "licensed", "note", "source"]


def norm_name(name: str) -> str:
    s = re.sub(r"[\s《》“”\"'（）()·、，,。.\-—_]", "", name or "")
    for suf in ("股份有限公司", "有限责任公司", "有限公司", "报社", "社", "集团"):
        s = s.replace(suf, "")
    return s.lower()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("batch", nargs="+")
    ap.add_argument("--tier", default="L2")
    ap.add_argument("--source", default="行业垂直媒体（批次补充调研，公开信息整理）")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    rows = list(csv.DictReader(open(CSV_PATH, encoding="utf-8-sig")))
    by_apex = {apex_of(r["domain"]): r for r in rows if r["domain"]}
    by_name = {norm_name(r["name"]): r for r in rows}
    seq = {}
    for r in rows:
        m = re.fullmatch(r"IM-(L\d)-(\d{3})", r["id"])
        if m:
            seq[m.group(1)] = max(seq.get(m.group(1), 0), int(m.group(2)))

    added, skipped, bad_sector = [], [], []
    for path in args.batch:
        data = __import__("json").load(open(path, encoding="utf-8"))
        items = data["items"] if isinstance(data, dict) else data
        for it in items:
            name = (it.get("name") or "").strip()
            domain = (it.get("domain") or "").strip().lower().removeprefix("https://").removeprefix("http://").strip("/")
            domain = domain.removeprefix("www.")
            sector = (it.get("sector") or "").strip()
            if not name:
                continue
            if sector not in SECTORS:
                bad_sector.append((name, sector))
                continue
            if domain and apex_of(domain) in by_apex:
                skipped.append((name, domain, "主域已收录：" + by_apex[apex_of(domain)]["name"]))
                continue
            if norm_name(name) in by_name:
                skipped.append((name, domain, "名称已收录：" + by_name[norm_name(name)]["name"]))
                continue
            seq[args.tier] = seq.get(args.tier, 0) + 1
            rec = {
                "id": f"IM-{args.tier}-{seq[args.tier]:03d}",
                "tier": args.tier,
                "name": name,
                "sector": sector,
                "industry": (it.get("industry") or "").strip(),
                "domain": domain,
                "http_status": it.get("http_status") or "",
                "licensed": "",
                "note": (it.get("note") or "").strip(),
                "source": it.get("source") or args.source,
            }
            rows.append(rec)
            added.append(rec)
            if domain:
                by_apex[apex_of(domain)] = rec
            by_name[norm_name(name)] = rec

    print(f"新增 {len(added)} 条 / 跳过 {len(skipped)} 条 / 行业枚举错误 {len(bad_sector)} 条")
    for r in added:
        print(f"  + {r['id']} {r['name']:<28s} {r['domain'] or '-' :<28s} {r['sector']}/{r['industry']}")
    for n, d, why in skipped:
        print(f"  = 跳过 {n} ({d or '无域名'}) — {why}")
    for n, s in bad_sector:
        print(f"  ! 行业枚举错误 {n}: {s!r}")

    if args.write:
        with open(CSV_PATH, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            w.writeheader()
            w.writerows(rows)
        print(f"已写入 {CSV_PATH}（共 {len(rows)} 条）")
    else:
        print("未写入（加 --write 生效）")


if __name__ == "__main__":
    main()
