# -*- coding: utf-8 -*-
"""OCR 编排：把 tools/ocr_image.swift 编译为本地二进制并按格调用，带结果缓存。

- 编译产物与缓存放仓库根 `.build/`（已 gitignore），不进版本库；
- 单元格识别 = PIL 裁剪落盘 + 放大 scale 倍 + Vision OCR；
- swift 自带的 --crop 有镜像 bug，一律用 PIL 裁剪（历史教训）；
- 格内多 token 按 y 聚类成行、行内按 x 排序，逐行拼接（换行感知）。
"""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
SWIFT = ROOT / "tools" / "ocr_image.swift"
BUILD = ROOT / ".build"
BIN = BUILD / "ocr"
CACHE = BUILD / "cache" / "ocr"


def ensure_binary() -> Path:
    BUILD.mkdir(parents=True, exist_ok=True)
    if not BIN.exists():
        subprocess.run(["swiftc", "-O", str(SWIFT), "-o", str(BIN)], check=True)
    return BIN


def _tokens(path: Path) -> list[dict]:
    out = subprocess.run([str(BIN), str(path), "--box"],
                         capture_output=True, text=True, timeout=120)
    toks = []
    for line in out.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) == 5:
            t, x, y, w, h = parts
            toks.append({"t": t, "x": int(x), "y": int(y), "w": int(w), "h": int(h)})
    return toks


def _join(tokens: list[dict]) -> str:
    """token 按 y 聚类成行（>13px 新行），行内按 x 排序，逐行拼接。"""
    if not tokens:
        return ""
    tokens = sorted(tokens, key=lambda t: (t["y"], t["x"]))
    lines: list[list[dict]] = []
    for t in tokens:
        if lines and t["y"] - lines[-1][-1]["y"] <= 13:
            lines[-1].append(t)
        else:
            lines.append([t])
    parts = []
    for line in lines:
        line.sort(key=lambda t: t["x"])
        s = ""
        for t in line:
            if s and _needs_space(s[-1], t["t"][0]):
                s += " "
            s += t["t"]
        parts.append(s)
    return "".join(parts)


def _needs_space(a: str, b: str) -> bool:
    latin = lambda c: c.isascii() and (c.isalnum() or c in ".-_/@:")
    return latin(a) and latin(b)


def ocr_region(img_path: str, rect: dict, scale: int = 3, cache: bool = True,
               trim: bool = True) -> str:
    """识别图中 rect 区域。缓存键 = 图片内容哈希 + 区域 + 放大倍数。

    trim=True 时先按暗像素外接框收紧裁剪（留 8px 边距）：
    孤立小字符（如序号「1」）在大片留白里 Vision 经常漏检，收紧后可解决。
    """
    ensure_binary()
    digest = hashlib.sha256(Path(img_path).read_bytes()).hexdigest()[:16]
    key = f"{digest}-{rect['x0']}-{rect['y0']}-{rect['x1']}-{rect['y1']}-s{scale}-t{int(trim)}"
    cache_file = CACHE / f"{key}.txt"
    if cache and cache_file.exists():
        return cache_file.read_text(encoding="utf-8")
    img = Image.open(img_path).convert("RGB")
    cell = img.crop((rect["x0"], rect["y0"], rect["x1"], rect["y1"]))
    if trim:
        import numpy as np
        g = np.asarray(cell.convert("L"))
        ys, xs = np.where(g < 180)
        if ys.size:
            m = 8
            y0, y1 = max(0, ys.min() - m), min(cell.height, ys.max() + m + 1)
            x0, x1 = max(0, xs.min() - m), min(cell.width, xs.max() + m + 1)
            if (y1 - y0) * (x1 - x0) < cell.width * cell.height * 0.92:
                cell = cell.crop((x0, y0, x1, y1))
    if scale != 1:
        cell = cell.resize((cell.width * scale, cell.height * scale), Image.LANCZOS)
    BUILD.joinpath("tmp").mkdir(parents=True, exist_ok=True)
    tmp = BUILD / "tmp" / "cell.png"   # 固定文件名覆写复用，不删临时文件
    cell.save(tmp)
    text = _join(_tokens(tmp))
    if cache:
        CACHE.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(text, encoding="utf-8")
    return text
