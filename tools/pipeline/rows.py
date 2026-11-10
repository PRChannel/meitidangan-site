# -*- coding: utf-8 -*-
"""行装配与校验：单元格矩阵 → 行记录；口径、序号、格式三类检查。"""
from __future__ import annotations

import re

LICENSE_RE = re.compile(r"\d{10,11}")
DOMAIN_RE = re.compile(r"^[a-zA-Z0-9.\-]+$|^[\u4e00-\u9fff][\u4e00-\u9fff.\-]*\.(公益|中国|公司|网络)$")


def assemble_rows(cells_by_band: list[list[dict]], skip_header: bool = True) -> list[list[str]]:
    """每个行带的单元格文本 → 一行字符串数组。

    cells_by_band: [band][col] = {"col": int, "text": str}
    - 空文本格保留为 ""，保证列位对齐；
    - skip_header: 含「序号/名称/编号」等词的首带视为表头剔除。
    """
    rows: list[list[str]] = []
    header_words = ("序号", "名称", "许可证", "地址", "单位", "账号", "域名")
    title_re = re.compile(r"名单（共\s*\d+\s*个）|获得互联网新闻信息服务许可")
    for band in cells_by_band:
        if not band:
            continue
        ncols = max(c.get("ncols", (c.get("cols") or (c.get("col", 0),))[0] + 1) for c in band)
        row = [""] * ncols
        for c in band:
            i = (c.get("cols") or (c.get("col", 0),))[0]
            row[i] = c["text"].strip()
        joined = "".join(row)
        if not joined:
            continue
        if title_re.search(joined):
            continue  # 分段标题混入（无表头行带的兜底）
        if skip_header and any(w in joined for w in header_words) and len(rows) == 0:
            continue
        if skip_header and joined.count("许可证") and "序号" in joined:
            continue  # 后续表格的表头行
        rows.append(row)
    return rows


def to_dicts(rows: list[list[str]], columns: list[str]) -> list[dict]:
    out = []
    for r in rows:
        d = {c: (r[i] if i < len(r) else "") for i, c in enumerate(columns)}
        d["_extra"] = r[len(columns):] if len(r) > len(columns) else []
        out.append(d)
    return out


def check_sequence(values: list[str], start: int = 1) -> list[str]:
    """序号连续性：恒定偏移=缺行；返回问题列表。"""
    problems = []
    nums = []
    for i, v in enumerate(values):
        m = re.fullmatch(r"\d{1,4}", (v or "").strip())
        nums.append(int(m.group(0)) if m else None)
    missing = [n for n, got in zip(range(start, start + len(nums)), nums) if got is None]
    if missing:
        problems.append(f"序号缺失/非数字：第 {missing[0]} 行附近（共 {len(missing)} 处）")
    for i in range(1, len(nums)):
        if nums[i] is None or nums[i - 1] is None:
            continue
        if nums[i] != nums[i - 1] + 1:
            problems.append(f"序号跳变 {nums[i-1]} → {nums[i]}（第 {i+1} 行）")
    return problems


def check_licenses(values: list[str]) -> list[str]:
    bad = [(i + 1, v) for i, v in enumerate(values)
           if v and not LICENSE_RE.fullmatch((v or "").strip())]
    return [f"许可证号格式异常（第 {i} 行）：{v}" for i, v in bad]


def check_domains(values: list[str]) -> list[str]:
    bad = []
    for i, v in enumerate(values):
        for d in re.split(r"[、；;，,/\s]+", v or ""):
            if d and not DOMAIN_RE.fullmatch(d):
                bad.append(f"第 {i+1} 行域名可疑：{d}")
    return bad


def check_counts(rows: list[dict], expect: dict[str, int] | None = None) -> list[str]:
    if not expect:
        return []
    problems = []
    for name, n in expect.items():
        got = len(rows)
        if got != n:
            problems.append(f"{name}：提取 {got} 行，公告口径 {n} 行，差 {got - n}")
    return problems


def run_checks(rows: list[dict], columns: list[str], expect: dict | None = None) -> dict:
    def col(name):
        return [r.get(name, "") for r in rows]

    problems: dict[str, list[str]] = {}
    seq_col = next((c for c in columns if "序" in c), None)
    if seq_col:
        problems["序号"] = check_sequence(col(seq_col))
    lic_col = next((c for c in columns if "许可证" in c), None)
    if lic_col:
        problems["许可证号"] = check_licenses(col(lic_col))
    dom_col = next((c for c in columns if "域名" in c or "地址" in c), None)
    if dom_col:
        problems["域名"] = check_domains(col(dom_col))
    problems["口径"] = check_counts(rows, expect)
    return {k: v for k, v in problems.items() if v}
