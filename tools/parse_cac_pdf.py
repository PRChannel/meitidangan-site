#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从国家网信办（cac.gov.cn）官方 PDF 名单中提取网站服务记录。

用法：
    python3 tools/parse_cac_pdf.py <pdf路径> [--out 输出json]

PDF 版式：序号 / 服务名称 / 服务地址 / 许可证编号 四列。
服务地址列可能包含多个域名，以中文分号「；」或换行分隔。
"""

import argparse
import json
import re
import sys

try:
    import pymupdf
except ImportError:
    try:
        import fitz as pymupdf
    except ImportError:
        sys.exit("缺少 PDF 解析库，请先执行：pip3 install --user pymupdf")

LICENSE_RE = re.compile(r"^\d{11,12}$")
SEQ_RE = re.compile(r"^\d{1,3}$")
DOMAIN_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?[A-Za-z0-9](?:[A-Za-z0-9\-]*[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9\-]+)+(?::\d+)?(?:/\S*)?$"
)


def normalize_domain(raw):
    """把服务地址原文规整为纯域名，保留原始写法。"""
    s = raw.strip().strip("；;，,、 ")
    s = re.sub(r"^https?://", "", s, flags=re.I)
    s = s.rstrip("/")
    return s


def extract_lines(pdf_path):
    doc = pymupdf.open(pdf_path)
    lines = []
    for page in doc:
        text = page.get_text()
        for line in text.splitlines():
            line = line.strip()
            if line:
                lines.append(line)
    return stitch_wrapped_domains(lines), doc.page_count


def stitch_wrapped_domains(lines):
    """修复 PDF 折行把一个域名拆成两行的情况。

    例：`www.chinadevelopment.com.c` + `n` -> `www.chinadevelopment.com.cn`
    判定：当前行是 1-4 个纯小写字母，且上一行以 `.xx`（1-3 位字母）结尾。
    """
    out = []
    for line in lines:
        if (
            out
            and re.fullmatch(r"[a-z]{1,4}", line)
            and re.search(r"\.[a-z]{1,3}$", out[-1])
            and re.fullmatch(r"[A-Za-z0-9.\-/]+", out[-1])
        ):
            out[-1] = out[-1] + line
            continue
        out.append(line)
    return out


def is_domain_like(s):
    """判断一行是否为服务地址（可能是多个域名用分号连接）。"""
    if not s:
        return False
    if DOMAIN_RE.match(s):
        return True
    if re.search(r"[；;]", s):
        parts = [p.strip() for p in re.split(r"[；;]", s) if p.strip()]
        return bool(parts) and all(DOMAIN_RE.match(p) for p in parts)
    return False


def parse(lines):
    """按 序号 / 服务名称 / 服务地址 / 许可证编号 的顺序解析。

    名称与服务地址都可能被 PDF 折成多行，因此不按固定行数取值，
    而是用「序号行」「许可证行」「地址行」三类特征切分数据块。
    """
    records = []
    i = 0
    total = len(lines)
    while i < total:
        if not SEQ_RE.match(lines[i]):
            i += 1
            continue
        seq = int(lines[i])
        i += 1

        # 1) 服务名称：连续的非序号、非许可证、非地址行
        name_parts = []
        while i < total:
            cur = lines[i]
            if SEQ_RE.match(cur) or LICENSE_RE.match(cur) or is_domain_like(cur):
                break
            name_parts.append(cur)
            i += 1

        # 2) 服务地址：连续的地址行
        addrs = []
        while i < total and is_domain_like(lines[i]):
            addrs.append(lines[i])
            i += 1

        # 3) 许可证编号
        license_no = None
        if i < total and LICENSE_RE.match(lines[i]):
            license_no = lines[i]
            i += 1

        if not name_parts or not addrs:
            continue

        raw_addr = "；".join(addrs)
        # PDF 换行前的分号会与拼接分隔符连成「；；」，统一归一
        raw_addr = re.sub(r"[；;]{2,}", "；", raw_addr).strip("；;")
        domains = []
        for part in re.split(r"[；;，,\s]+", raw_addr):
            part = part.strip()
            if not part:
                continue
            d = normalize_domain(part)
            if d and DOMAIN_RE.match(d) and d not in domains:
                domains.append(d)

        records.append(
            {
                "seq": seq,
                "name": "".join(name_parts),
                "registered_addresses_raw": raw_addr,
                "registered_domains": domains,
                "license_number": license_no,
            }
        )
    return records


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    lines, pages = extract_lines(args.pdf)
    records = parse(lines)

    # 校验序号连续性
    seqs = [r["seq"] for r in records]
    expected = list(range(1, len(records) + 1))
    contiguous = seqs == expected
    no_license = [r["seq"] for r in records if not r["license_number"]]
    no_domain = [r["seq"] for r in records if not r["registered_domains"]]

    print(f"PDF 页数：{pages}")
    print(f"提取记录：{len(records)}")
    print(f"序号连续：{'是' if contiguous else '否（前20个：%s）' % seqs[:20]}")
    print(f"缺许可证号：{len(no_license)} 条 {no_license[:10]}")
    print(f"缺域名：{len(no_domain)} 条 {no_domain[:10]}")

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
        print(f"已写出：{args.out}")

    return 0 if contiguous and not no_license and not no_domain else 1


if __name__ == "__main__":
    sys.exit(main())
