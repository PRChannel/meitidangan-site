# tools/pipeline —— 公告长图 → 结构化行

政策改版/省份发新名单时，把公告长图转成可入库行数据的完整管线。
设计文档见仓库根 `RUNBOOK-INGEST.md`（操作流程）与 `DATA-SCHEMA.md`（字段口径）。

## 组成

| 文件 | 职责 |
|---|---|
| `grid.py` | 边框网格检测：横线（暗像素占比 >0.55）→ 行带 → 带内竖线 → 单元格；**按列布局分组对齐**（一张图多张表、列宽不同时各自成组），缺线自动合并单元格 |
| `ocr.py` | Vision OCR 编排：自动编译 `tools/ocr_image.swift` → `.build/ocr`；格级裁剪 + 内容收紧（孤立小字防漏检）+ 放大 + 结果缓存（`.build/cache/ocr/`，键=图片哈希+区域+参数） |
| `rows.py` | 行装配（表头剔除、分段标题过滤、合并格归位）+ 三类校验（序号连续性、许可证 10–11 位、域名格式）+ 口径比对 |
| `__main__.py` | CLI：`extract` / `check` |

## 用法

```bash
# 提取（在仓库根目录）
python3 -m tools.pipeline extract pending/<省>_m01.png pending/<省>_m02.png \
    --cols 序号,服务名称,服务地址,许可证编号 --out /tmp/rows.json

# 口径与格式校验（公告自报行数）
python3 -m tools.pipeline check /tmp/rows.json --expect 网站表=10
```

调参（都是 `extract` 的选项，一般不用动）：
- `--thresh 180 --dark-frac 0.55`：横竖线的暗像素判定（浅灰横线图曾把阈值降到 160 一类，按需调）
- `--scale 3`：格级放大倍数；小字表格可试 4
- `--keep-header`：保留表头行（默认剔除）

## 已知边界（务必读）

1. **序号列以位置为准**：孤立小数字 Vision 会偶发漏检/误读（如 6→9），`check` 的序号连续性会标出；入库时按行序位置回填，这是既定口径（历史：河南应用表"00"、湖北碎片行均如此处理）。
2. **格级误字走定点复 OCR**：域名/证号类格式错误用 `tools/ocr_fix_cells.py`（按 pattern 逐格放大重识别），顽固的单字误读裁原图目视定案。
3. **负结果不可信，正结果才采信**：OCR 漏行 ≠ 原件没有；跨图序号连续性回核是终检利器（恒定偏移=缺行）。
4. 多域名、rowspan、跨页续表：跨页续表若无表头也能按列宽分组接上（同一布局）；rowspan 合并格文本落在跨度首列。
5. 原件自身有错（重复登记、漏印、写法不一）**如实保留**并写 `notes`，不要在管线里"修"。

## 与入库的衔接

```
extract → rows.json（人工过一遍 check 报告）
        → tools/ingest_province_rows.py <rows.json> --province <省> \
              --prefix CN-XX-YYYYMMDD-WEB --source-url ... --list-as-of ... \
              --evidence-method ocr_image_recognition_table_rebuild \
              --evidence-id ... --evidence-sha256 ... --write
        → build_site.py → build_domain_index.py → tools/validate_site.py
        → tools/diff_versions.py --base HEAD~1 --head WORKTREE
```

## 回归基准

`pending/` 保留 16 省 552 张原图。改管线后必须重跑至少一个省并与
`data/public-records.json` 对应记录比对。`.build/` 不入版本库。

**基准一（2026-11-10 建立）：天津 2026-09-30 版 7 图 → 应有 103 行。**

| 指标 | 结果 |
|---|---|
| 提取行数 | 97（95 行四列整齐 + 2 行形状异常） |
| 证号覆盖 | 25/25 唯一证号全部命中，无多出 |
| 未全自动恢复 | 7 行，全部集中在公众账号表：带引号多行账号名导致列分裂（如"乐龄天淳公众账号"被引号断行拆散），需 `check` 报告定位后定点复 OCR / 目视补录 |
| 通道 | 网站表 10、应用表 17 全部整齐恢复；账号表 76 中 69 自动恢复 |

结论：管线把"逐行人工重建"压缩成"自动提取 + 7 行定点修复"，`check` 子命令的
证号级行数差异报告能精确指出缺哪几行（按证号分组比对公告自报口径）。
