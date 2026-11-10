#!/usr/bin/env python3
"""生成媒体域名资质索引，供外部（如暗传播媒体报价页）按域名快速判定新闻资质。

输出：
  docs/data/domain-index.json    主索引（按主域 apex 聚合 + 名称别名索引 + 覆盖等级）
  docs/data/coverage-levels.json 省份覆盖等级（机器可读）
  data/domain-index.json         同内容副本，供本地脚本引用

判定口径：
  qualified=true  该主域已列入官方许可名单（互联网新闻信息服务许可，任一服务形式）
  categories      采编发布服务 / 转载服务 / 传播平台服务 / 未载明（该省名单未列类别）
  未命中          不等于无资质，须结合 coverage 字段：full 才可视为"该版本内未列入"

用法：python3 build_domain_index.py
"""
import json
import re
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "docs" / "data"

CN_SECOND_LEVEL = {
    "com.cn", "net.cn", "org.cn", "gov.cn", "edu.cn", "ac.cn", "mil.cn",
    "ah.cn", "bj.cn", "cq.cn", "fj.cn", "gd.cn", "gs.cn", "gx.cn", "gz.cn",
    "ha.cn", "hb.cn", "he.cn", "hi.cn", "hk.cn", "hl.cn", "hn.cn", "jl.cn",
    "js.cn", "jx.cn", "ln.cn", "mo.cn", "nm.cn", "nx.cn", "qh.cn", "sc.cn",
    "sd.cn", "sh.cn", "sn.cn", "sx.cn", "tj.cn", "tw.cn", "xj.cn", "xz.cn",
    "yn.cn", "zj.cn",
}

# 覆盖等级：full=最新版全部分项全量；near_full=个别分项缺；partial=官方原件缺陷缺行；outdated=仅旧版
COVERAGE_LEVEL = {p: "full" for p in (
    "北京 天津 河北 山西 内蒙古 辽宁 吉林 黑龙江 上海 江苏 浙江 安徽 福建 江西 "
    "河南 湖北 湖南 广东 广西 海南 重庆 四川 贵州 云南 西藏 陕西 甘肃 新疆 中央").split()}
COVERAGE_LEVEL.update({
    "山东": "near_full",
    "青海": "partial",
    "宁夏": "outdated",
})

CAT_RULES = [
    ("采编", "采编发布服务"),
    ("转载", "转载服务"),
    ("传播平台", "传播平台服务"),
    ("平台", "传播平台服务"),
]


def apex_of(domain: str) -> str:
    d = domain.strip().lower().rstrip(".")
    d = re.sub(r"^https?://", "", d).split("/")[0].split(":")[0]
    labels = d.split(".")
    if len(labels) <= 2:
        return d
    if ".".join(labels[-2:]) in CN_SECOND_LEVEL:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def norm_name(name: str) -> str:
    """名称归一：去空白/书名号/引号，统一"日报社/报社"等写法，供名称兜底匹配。"""
    s = re.sub(r"[\s“”\"'《》〈〉（）()·]", "", name or "")
    s = s.replace("日报社", "日报").replace("报社", "日报").replace("广播电视台", "广电")
    s = s.replace("融媒体中心", "融媒").replace("新闻中心", "新闻")
    return s.lower()


def main():
    data = json.load(open(ROOT / "data" / "public-records.json"))
    records = data["records"]

    # 证号 → 主体登记的服务类别（多数省份只在主体表列类别，网站表不列）
    cats_by_license = defaultdict(set)
    for r in records:
        if r.get("record_kind") == "entity":
            for c in r.get("service_categories") or []:
                for key, label in CAT_RULES:
                    if key in c:
                        cats_by_license[r["license_number"]].add(label)

    # 证号 → 主体名称（用于缺 operator 的记录回填运营单位）
    oper_by_license = {}
    for r in records:
        if r.get("record_kind") == "entity":
            oper_by_license.setdefault(r["license_number"], r.get("name") or "")

    web = [r for r in records if r.get("registered_domains")]
    index = {}

    def page_of(record_id):
        return f"https://meitidangan.com/media/{record_id.lower()}/"

    for r in web:
        lic = r.get("license_number") or ""
        cats = sorted(cats_by_license.get(lic, []))
        for d in r["registered_domains"]:
            apex = apex_of(d)
            entry = index.setdefault(apex, {
                "apex": apex, "live": "", "records": [],
            })
            entry["records"].append({
                "id": r["record_id"],
                "name": r.get("name") or "",
                "license": lic,
                "region": r.get("region") or "",
                "operator": r.get("operator_name") or oper_by_license.get(lic, ""),
                "form": r.get("service_type") or r.get("service_form") or "互联网站",
                "cats": cats,
                "as_of": r.get("list_as_of") or "",
                "authority": r.get("issuing_authority") or "",
                "src": r.get("source_url") or "",
                "listed_domain": d,
                "page": page_of(r["record_id"]),
            })

    order = {"full": 0, "near_full": 1, "partial": 2, "outdated": 3, "unknown": 4}
    for apex, entry in index.items():
        recs = entry["records"]
        cats = {c for r in recs for c in r["cats"]}
        entry["qualified"] = True
        entry["categories"] = sorted(cats) if cats else ["未载明"]
        entry["editing"] = ("采编发布服务" in cats) if cats else None   # None=该省名单未列类别
        entry["provinces"] = sorted({r["region"] for r in recs})
        entry["as_of"] = max(r["as_of"] for r in recs)
        entry["coverage"] = max(
            (COVERAGE_LEVEL.get(r["region"], "unknown") for r in recs),
            key=lambda x: order.get(x, 4))
        # 名单登记的全部完整主机名（含子域），供前端区分"精确命中"与"主域继承"
        entry["hosts"] = sorted({r["listed_domain"].lower() for r in recs})
        # 标签点击打开的详情页：优先取登记域名恰为主域/主站 www 的记录，否则取名单日期最新的一条
        def pick_rank(r):
            host = r["listed_domain"].lower()
            if host == apex:
                return 0
            if host == "www." + apex:
                return 1
            return 2
        pick = sorted(recs, key=lambda r: (-int(r["as_of"].replace("-", "") or 0), pick_rank(r)))[0]
        entry["page"] = pick["page"]
        entry["page_id"] = pick["id"]
        entry["page_name"] = pick["name"]

    # 名称索引：归一名称 → 主域列表（报价页常只有媒体名，没有域名）
    name_index = defaultdict(set)
    for apex, entry in index.items():
        for r in entry["records"]:
            for cand in (r["name"], r["operator"]):
                if cand:
                    name_index[norm_name(cand)].add(apex)
            # 去掉"网站/网/在线"等后缀的短名也建一份
            short = re.sub(r"(新闻网|网站|网|在线)$", "", r["name"])
            if short and short != r["name"]:
                name_index[norm_name(short)].add(apex)

    payload = {
        "schema": "media-domain-index/1",
        "generated_at": date.today().isoformat(),
        "basis": {
            "source": "中国媒体身份资料库 meitidangan.com",
            "record_count": len(web),
            "domain_count": len(index),
            "name_key_count": len(name_index),
            "note": "仅收录经省级网信办公告原件核对的互联网新闻信息服务许可记录。"
                    "未命中不等于无资质：须结合该省 coverage 等级（full 才可视为该版本内未列入）。"
                    "categories 为'未载明'时，表示该省名单未列服务类别，不代表无采编资质。",
        },
        "coverage_legend": {
            "full": "该省最新版公告全部分项已全量提取，可据以判定未列入",
            "near_full": "仅个别分项缺行（山东直播/其他），判定结果基本可信",
            "partial": "官方页面缺陷导致缺行（青海账号 29 行），未命中可能因缺行",
            "outdated": "仅有旧版名单（宁夏 2025-09-30），新取得许可的媒体可能未收录",
            "unknown": "无覆盖信息",
        },
        "coverage_levels": COVERAGE_LEVEL,
        "domains": dict(sorted(index.items())),
        "names": {k: sorted(v) for k, v in sorted(name_index.items())},
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    blob = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    (OUT_DIR / "domain-index.json").write_text(blob, encoding="utf-8")
    (ROOT / "data" / "domain-index.json").write_text(blob, encoding="utf-8")
    (OUT_DIR / "coverage-levels.json").write_text(
        json.dumps({"generated_at": payload["generated_at"],
                    "levels": COVERAGE_LEVEL,
                    "legend": payload["coverage_legend"]},
                   ensure_ascii=False, indent=1), encoding="utf-8")

    multi = sum(1 for v in index.values() if len(v["records"]) > 1)
    print(json.dumps({
        "domains": len(index),
        "records": len(web),
        "multi_record_apex": multi,
        "with_editing": sum(1 for v in index.values() if v["editing"] is True),
        "cats_unknown": sum(1 for v in index.values() if v["editing"] is None),
        "name_keys": len(name_index),
        "kb": round(len(blob.encode()) / 1024),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
