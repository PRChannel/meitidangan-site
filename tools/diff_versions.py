#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""对比两版 public-records.json，输出名单改版带来的新增/移除/变更报告。

政策或公告口径调整后，第一件要知道的事是"这一版和上一版差在哪、影响了谁"，
本工具就是那一步。数据不必额外留快照——每一版都在 git 历史里。

用法：
    python3 tools/diff_versions.py                       # 上一提交 vs 工作区
    python3 tools/diff_versions.py --base 8a5e4703d --head 775cd2a13
    python3 tools/diff_versions.py --base HEAD~3 --head HEAD --md out/diff.md --json out/diff.json

--base / --head 接受 git 引用（rev[:path]）、分支名或本地文件路径。
"""
import json
import subprocess
import sys
from pathlib import Path
from collections import Counter, defaultdict
import argparse

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATH = "data/public-records.json"

WATCH_FIELDS = [
    ("name", "媒体名称"),
    ("registered_domains", "登记域名"),
    ("service_categories", "服务类别"),
    ("service_form", "服务形式"),
    ("service_type", "服务类型"),
    ("record_kind", "记录类型"),
    ("operator_name", "运营单位"),
    ("license_number", "许可证号"),
    ("list_as_of", "名单版本"),
    ("issuing_authority", "发证机关"),
]


def load(source, path=DEFAULT_PATH):
    """source 可为 WORKTREE、本地文件路径或 git 引用。"""
    if source.upper() == "WORKTREE":
        with open(ROOT / path, encoding="utf-8") as f:
            data = json.load(f)
        label = "工作区"
    elif Path(source).exists():
        with open(source, encoding="utf-8") as f:
            data = json.load(f)
        label = str(source)
    else:
        spec = source if ":" in source else f"{source}:{path}"
        out = subprocess.run(["git", "-C", str(ROOT), "show", spec],
                             capture_output=True)
        if out.returncode != 0:
            sys.exit(f"无法从 git 读取 {spec}: {out.stderr.decode()[:200]}")
        data = json.loads(out.stdout.decode("utf-8"))
        label = spec
    recs = data["records"] if isinstance(data, dict) else data
    return {r["record_id"]: r for r in recs}, label


def key_of(r):
    return (r.get("region") or "", r.get("record_id") or "")


def diff(base, head):
    added = [head[k] for k in head.keys() - base.keys()]
    removed = [base[k] for k in base.keys() - head.keys()]
    changed = []
    for k in base.keys() & head.keys():
        b, h = base[k], head[k]
        fields = []
        for f, cn in WATCH_FIELDS:
            if b.get(f) != h.get(f):
                fields.append({"field": f, "label": cn,
                               "base": b.get(f), "head": h.get(f)})
        if fields:
            changed.append({"record_id": k, "name": h.get("name") or b.get("name"),
                            "region": h.get("region") or b.get("region"),
                            "fields": fields})
    return added, removed, changed


def fmt_domains(v):
    if isinstance(v, list):
        return "、".join(v) if v else "（空）"
    return str(v) if v else "（空）"


def report(base, head, base_label, head_label, md_path=None, json_path=None):
    added, removed, changed = diff(base, head)
    delta = len(head) - len(base)

    lines = []
    lines.append("# 名单版本差异报告")
    lines.append("")
    lines.append(f"- 基线：`{base_label}`（{len(base)} 条）")
    lines.append(f"- 目标：`{head_label}`（{len(head)} 条）")
    lines.append(f"- 净增减：{delta:+d}　新增 {len(added)}　移除 {len(removed)}　字段变更 {len(changed)}")
    lines.append("")

    def region_summary(items):
        if not items:
            return
        dist = Counter((i.get("region") or "未标注") for i in items).most_common()
        lines.append("按省份分布：" + "、".join(f"{p} {n} 条" for p, n in dist))
        lines.append("")

    lines.append("## 新增记录")
    lines.append("")
    if added:
        region_summary(added)
        lines.append("| 记录ID | 媒体名称 | 域名 | 名单版本 |")
        lines.append("|---|---|---|---|")
        for r in sorted(added, key=key_of):
            lines.append(f"| {r['record_id']} | {r.get('name') or ''} | "
                         f"{fmt_domains(r.get('registered_domains'))} | {r.get('list_as_of') or ''} |")
    else:
        lines.append("无")
    lines.append("")

    lines.append("## 移除记录")
    lines.append("")
    if removed:
        region_summary(removed)
        lines.append("| 记录ID | 媒体名称 | 域名 | 名单版本 |")
        lines.append("|---|---|---|---|")
        for r in sorted(removed, key=key_of):
            lines.append(f"| {r['record_id']} | {r.get('name') or ''} | "
                         f"{fmt_domains(r.get('registered_domains'))} | {r.get('list_as_of') or ''} |")
        lines.append("")
        lines.append("> 移除不等于许可失效，可能是序号重排、合并登记或分项调整；需回溯原件确认。")
    else:
        lines.append("无")
    lines.append("")

    dom_changed = [c for c in changed if any(f["field"] == "registered_domains" for f in c["fields"])]
    lines.append("## 域名变化（直接影响域名比对与外部对接）")
    lines.append("")
    if dom_changed:
        lines.append("| 记录ID | 媒体名称 | 变更 |")
        lines.append("|---|---|---|")
        for c in sorted(dom_changed, key=lambda x: (x["region"] or "", x["record_id"])):
            f = next(f for f in c["fields"] if f["field"] == "registered_domains")
            lines.append(f"| {c['record_id']} | {c['name']} | "
                         f"{fmt_domains(f['base'])} → {fmt_domains(f['head'])} |")
    else:
        lines.append("无")
    lines.append("")

    other = [c for c in changed if not any(f["field"] == "registered_domains" for f in c["fields"])]
    lines.append("## 其他字段变化")
    lines.append("")
    if other:
        lines.append("| 记录ID | 媒体名称 | 字段 | 原值 | 新值 |")
        lines.append("|---|---|---|---|---|")
        for c in sorted(other, key=lambda x: (x["region"] or "", x["record_id"])):
            for f in c["fields"]:
                lines.append(f"| {c['record_id']} | {c['name']} | {f['label']} | "
                             f"{fmt_domains(f['base'])} | {fmt_domains(f['head'])} |")
    else:
        lines.append("无")
    lines.append("")

    by_field = Counter(f["label"] for c in changed for f in c["fields"])
    if by_field:
        lines.append("## 变化字段分布")
        lines.append("")
        for k, v in by_field.most_common():
            lines.append(f"- {k}：{v} 条")
        lines.append("")

    md = "\n".join(lines)
    print(md)

    if md_path:
        Path(md_path).parent.mkdir(parents=True, exist_ok=True)
        Path(md_path).write_text(md, encoding="utf-8")
    if json_path:
        Path(json_path).parent.mkdir(parents=True, exist_ok=True)
        Path(json_path).write_text(json.dumps({
            "base": base_label, "head": head_label,
            "counts": {"base": len(base), "head": len(head), "delta": delta,
                       "added": len(added), "removed": len(removed), "changed": len(changed)},
            "added": added, "removed": removed, "changed": changed,
        }, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"added": len(added), "removed": len(removed), "changed": len(changed)}


def main():
    ap = argparse.ArgumentParser(description="对比两版 public-records.json")
    ap.add_argument("--base", default="HEAD~1", help="基线：git 引用或文件路径")
    ap.add_argument("--head", default="WORKTREE", help="目标：git 引用、文件路径或 WORKTREE")
    ap.add_argument("--path", default=DEFAULT_PATH, help="记录文件路径（git 引用时生效）")
    ap.add_argument("--md", default="", help="Markdown 报告输出路径")
    ap.add_argument("--json", default="", help="JSON 明细输出路径")
    a = ap.parse_args()

    base, base_label = load(a.base, a.path)
    head, head_label = load(a.head, a.path)
    report(base, head, base_label, head_label, a.md or None, a.json or None)


if __name__ == "__main__":
    main()
