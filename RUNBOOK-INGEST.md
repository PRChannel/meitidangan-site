# 名单改版操作手册（RUNBOOK）

政策改版、省份发新名单时的固定动作。目标：**拿到新公告 → 当天出数据 → 可核验、可回滚**。
动手前先读 `DATA-SCHEMA.md`。

## 0. 先做差异基线

```bash
git pull
python3 tools/diff_versions.py --base HEAD --head WORKTREE   # 确认当前工作区与上一版一致
```

改完数据后再跑一次同样的命令，用报告核对：新增/移除数是否与公告口径一致、域名有无意外增减。

## 1. 找最新一期名单（而不是最新公告）

- 入口：`data/sources_32.json` 里各省 `source_url`（**会过时**，部分省份正文被就地更新到新版）。
- 正确找法：省网信办"许可信息"列表页翻页，找标题含「许可信息（截至 YYYY-MM-DD）」的那条；拿不到就查省委宣传部/政府网转载。
- 认版本：以**正文统计截止日期**为准，不是公告发布日期。
- 记三样：公告 URL、发布日期、公告自报口径（如"31 家单位 / 265 项服务"）。

## 2. 判形态，选通道（从省力到费力）

| 形态 | 通道 | 备注 |
|---|---|---|
| xlsx / docx / doc / PDF 附件 | 直提表格 | doc 用 `textutil -convert txt`（macOS）；xlsx 用 openpyxl；PDF 用 pdfplumber（跨页续表可无表头合并） |
| 正文 HTML 表格 | 直提 `td/tr`，还原 rowspan | 最快，零转写风险 |
| 正文由 JS 渲染（静态抓取乱码） | Chrome 无头 `--dump-dom` 后取 DOM | 河北范式 |
| 长图（JPG/PNG） | 边框网格 OCR（`rowocr6`：`run(img, out_json, 180, 0.55)`） | 主通道，见第 3 节 |
| 公众号文章 | 桌面 Chrome UA 直连 `/s/短链`；正文可能只有二维码 | 长图再走 OCR |
| 页面 WAF 拦 curl | 换 WebFetch 或找 PDF 直链 | 青海 qhcac、宁夏 nxnews 都遇到过 |

## 3. 长图 OCR 要点（踩过的坑）

> 现状：核心 OCR 管线（rowocr5/rowocr6、各省装配脚本）此前放在临时目录、**未入库**；仓库里只有 `tools/ocr_table.py`（带坐标 OCR 结果→表格）、`tools/ocr_fix_cells.py`、`tools/ocr_image.swift` 等半套。下次改版前应先把管线固化为 `tools/pipeline/`，否则要从零重写。

- **边框网格法**：暗像素统计（阈值 >0.55）检出横竖分隔线 → 按格裁剪 OCR；逐行裁剪 + 放大 3 倍，优于整图 tile（tile 重叠会把同一串读两遍）。
- **竖线不贯通**时改用逐行带检测（每行带内独立检测竖线），全图均值法会漏检。
- **跨竖线的 token 必须对两侧单元格单独复 OCR**，否则会融合两列文本丢字。
- **换行感知拼接**：格内 token 按 y 聚类（>13px 视为新行），行内按 x 排序。
- 低清图（600px 级）与碎片图（20–90px 高）会漏行，**必须目视补录**，不能只信 OCR 行数。
- 官方原件自身有错（重复图、漏印证号、单位名写法不一、重复登记）→ **如实保留并写 `notes`**，不要"修正"。

## 4. 装配与入库

1. 装配成 `rows_final.json`（按分项：网站/应用/论坛/账号/直播/其他/主体），逐项与公告自报数核对。
2. 入库：
   ```bash
   python3 tools/ingest_province_rows.py <rows.json> \
       --province <省> --prefix CN-XX-YYYYMMDD-WEB \
       --source-url <公告URL> --list-as-of <YYYY-MM-DD> --source-published-at <YYYY-MM-DD> \
       --issuing <发证机关> --evidence-method <提取方式> \
       --evidence-id <证据编号> --evidence-sha256 <哈希> \
       --coverage-status "<覆盖状态>" --coverage-note "<问题与后续>" --write
   ```
   - 列名可用 `--name-column` / `--domain-column` / `--operator-column` / `--license-column` 指定，默认是 `网站名称`/`域名`/`单位名称`/`许可证编号`。
   - **`--prefix` 必须带分项后缀**（`-WEB`/`-APP`/`-ACC`/`-FORUM`/`-LIVE`/`-OTHER`），否则与主体表撞号，表现为"已导入"假跳过或吞号。
   - 别忘 `--write`；`--evidence-sha256` 缺失会导致后续校验崩溃。
3. 入库后**立刻核对"预期新增数 vs 实际增量"**，不符就回滚重来。
4. 主体类别（采编/转载/传播平台）只在主体表，网站记录靠证号关联，别指望网站表带类别。

## 5. 元数据三件套（缺一个就会口径不一致）

- `data/coverage.json`：中文键，逐省写「已提取版本统计截至 / 覆盖状态 / 问题与后续 / 当前完整有效性结论」
- `data/sources_32.json`：`region` 键，登记 `source_url` / `index_page` / `published_count_reference` / `fetch_status`
- `data/official-sources.csv`：utf-8-sig，写入时 `extrasaction='ignore'`，避免双 BOM（先 `lstrip('\ufeff')`）

## 6. 构建与发布

```bash
python3 build_site.py && python3 build_domain_index.py && python3 tools/validate_site.py
```

三关全绿再提交。`validate_site.py` 会断言：record_id 唯一、每页单 h1、无断链、每页含证号/版本/证据哈希、service 记录不带域名、页面数与记录数一致。

提交并推送后，CI 会重建并部署；**推送若被拒先 `git pull --rebase`**。

## 7. 发布后检查

- 线上抽查：首页、`/directory/`、3 条新记录详情页、`/data/domain-index.json`
- CI 是否真的跑过（本仓库有并发队列卡死的前科）：
  ```bash
  curl -s "https://api.github.com/repos/PRChannel/meitidangan-site/actions/runs?per_page=3"
  ```
  若有 run 长时间 `pending` 且 `jobs=0`，取消占位 run 即可解锁，不要改 Pages 配置。

## 8. 对外表述红线

- 只声明"截至某日期版本的名单记录"，不声明"当前有效持证"。
- 未命中的资源只能说"本站未收录"，不得说"无资质"（青海 partial、宁夏 outdated、山东 near_full）。
- 覆盖不全的省份，引用时必须带覆盖等级说明。
