# 数据结构与字段约定（DATA-SCHEMA）

本文件是 `data/public-records.json` 的字段字典与改版规则。政策或公告口径调整时，**先看这里再动数据**：
新增字段只增不删、删改字段必须升 `schema_version` 并同步本文件与消费方（如暗传播报价页）。

- 当前版本：`schema_version = "1.0"`
- 主文件：`data/public-records.json`（约 23MB，25,967 条）
- 生成链路：抓取/OCR → `tools/ingest_*.py` 写入 → `build_site.py` 出页面 → `build_domain_index.py` 出对外索引
- 校验关卡：`tools/validate_site.py`（CI 每次构建必跑，断言失败即中止部署）

---

## 1. 记录主键与编号规则

`record_id` 形如 `CN-<省/中央简称>-<名单日期>-<分项>-<三位序号>`，例：`CN-HB-20260930-WEB-007`。

| 分项后缀 | 含义 | 对应 `record_kind` |
|---|---|---|
| `WEB` | 互联网站（唯一带域名的分项） | 无该字段（默认 website） |
| `APP` | 应用程序 | `service` |
| `ACC` | 公众账号（微信/微博/抖音等） | `service` |
| `FORUM` | 论坛 | `service` |
| `LIVE` | 网络直播 | `service` |
| `OTHER` | 其他服务形式 | `service` |
| 无分项 | 许可主体 | `entity` |

**两条硬约束（踩过坑）**

1. 分项前缀必须带后缀（`CN-HB-20260930-APP`），不能与主体表共用 `CN-HB-20260930`——否则 rid 空间冲突，ingest 会误判"已导入"或吞号。
2. `record_kind = service` 的记录**不允许**带 `registered_domains`（`build_site.py` 有断言）；网站记录一律用无 `record_kind` 的默认 schema。

## 2. 字段字典（26 个）

| 字段 | 类型 | 说明 |
|---|---|---|
| `record_id` | str | 主键，规则见上节；全库唯一 |
| `name` | str | 媒体/账号/单位名称，**按原件写法保留**，不做规范化 |
| `region` | str | 省级行政区或 `中央`；共 32 个取值 |
| `license_number` | str | 许可证编号（10–11 位）。原件漏印时如实保留并加 `notes` |
| `registered_addresses_raw` | str | 原件"服务地址/域名"栏的原始文本，分号或换行分隔 |
| `registered_domains` | list[str] | 归一后的域名数组；**只网站记录非空**（1,786 条 / 1,878 个域名） |
| `operator_name` | str\|null | 运营单位（部分省份原件未列，主体表可补） |
| `service_type` | str\|null | 原件"服务类型"栏，如 `互联网站`；大量记录原件无此列 |
| `service_form` | str\|null | 服务形式：`公众账号`(18,517) / `应用程序`(3,045) / `论坛`(32) / `网络直播`(13) / `小程序`(8) / `微博客`(2) / `博客`(1) / `其他`(38) / `其他服务形式`(12) |
| `service_categories` | list[str] | 许可类别：`采编发布服务` / `转载服务` / `传播平台服务`；**仅主体记录有**，网站记录需按证号关联 |
| `entity_nature` | str\|null | 单位性质（`事业单位法人` / `企业法人` 等），仅主体记录 |
| `record_kind` | str\|null | `entity`(2,513) / `service`(21,668) / 空(1,786=网站) |
| `source_url` | str | 依据的官方公告页面地址 |
| `source_published_at` | str | 公告发布日期 `YYYY-MM-DD` |
| `list_as_of` | str | **名单统计截止日期**（不是抓取日期），页面展示与引用一律以此为准 |
| `verified_at` | str | 本站核对日期 |
| `issuing_authority` | str\|null | 发证机关 |
| `evidence_id` | str | 证据编号（按省+版本+分项），可回溯到原件 |
| `evidence_sha256` | str | 证据哈希：图片证据=按页面顺序逐字节串联的 sha256；HTML 直提省=页面 HTML 的 sha256 |
| `evidence_method` | str\|null | 提取方式，见第 3 节 |
| `review_status` | str | 目前恒为 `verified_dated_official_record`（已核对到带日期的官方记录） |
| `current_license_validity` | str | 目前恒为 `not_independently_confirmed`（**不宣称实时有效**，站点多处依赖此断言） |
| `domain_note` | str | 仅 19 条：域名非原件直接印出、经他版名单+HTTP 核验补录时的说明 |
| `domain_http_checked` | bool | 仅 19 条：是否已做 HTTP 可达性核验 |
| `notes` | str | 原件自身矛盾的如实记录（重复登记、证号不一致等） |

顶层键：`schema_version`、`generated_at`、`scope`、`province_coverage_count`、`province_original_missing_count`、`central_records`、`records`。

> ⚠️ 已知陈旧项：`province_coverage_count = 22`、`province_original_missing_count = 9` 是早期值，与现状（31 省全覆盖、原件缺口 0）不符，且当前无代码读取。改版时应一并更新或删除，避免下游误读。

## 3. `evidence_method` 取值

| 值 | 含义 |
|---|---|
| `ocr_image_recognition_table_rebuild` | 公告长图边框网格 OCR 重建（17,205 条，主力） |
| `official_attachment_text_extraction` | 官方附件文本直提（doc/docx 等） |
| `html_table_text_extraction` | 公告正文 HTML 表格直提 |
| `official_attachment_xlsx_text_extraction` | 官方 xlsx 附件直提 |
| `official_page_rendered_dom_table_extraction` | 页面 JS 渲染后取 DOM（如河北） |
| `official_attachment_docx_table_extraction` | docx 表格直提 |
| `pdf_text_extraction_sequential_check` | PDF 文本层提取 + 序号连续性回核 |
| `ocr_image_recognition_domain_http_checked` | OCR 后域名逐个 HTTP 核验 |
| `ocr_image_recognition_address_print_confirmed` | OCR 后地址以原件印张确认 |
| `ocr_image_recognition_table_rebuild_domain_http_checked` | 上述两种组合 |

## 4. 域名约定

- `registered_domains` 保留**名单登记写法**（多为裸域，如 `bjd.com.cn`，站点常只在 `www.` 下服务）。
- 主域归一在 `build_domain_index.py` 内完成，**不在源数据里改**：`.com.cn` / `.gov.cn` / `.org.cn` 等按中国二级后缀表处理，避免把 `bjd.com.cn` 截成 `com.cn`。
- 中文域名（`.公益` 等，3 条）按原件保留，不转 punycode。
- 同一域名可对应多条记录（如 `xfjw.net` 3 条），**不合并**。
- `meitidangan.com` 自身不入库、不入索引。

## 5. 覆盖口径（`data/coverage.json`）

逐省一条，中文键（`省份` / `覆盖状态` / `问题与后续` / `当前完整有效性结论` 等）。机读版本在 `build_domain_index.py` 内映射为四档：

| 档位 | 含义 | 对外含义 |
|---|---|---|
| `full` | 全分项与公告口径一致 | 未命中≈未列入 |
| `near_full` | 某分项缺行（如山东缺直播 2+其他 1） | 未命中需提示可能有缺 |
| `partial` | 官方页面缺行（青海 445/474） | 不可下"无资质"结论 |
| `outdated` | 名单版本旧（宁夏 2025-09-30） | 需注明版本 |

## 6. 改版规则

1. **只增字段不删**；必须删改时 `schema_version` 升次版本（1.0 → 1.1），并在本文件"变更记录"登记。
2. 改前先跑 `python3 tools/diff_versions.py --base HEAD~1 --head WORKTREE`，确认差异符合预期（新增/移除/域名变化/字段变化），再入库。
3. 改后必须过三关：`build_site.py` → `build_domain_index.py` → `tools/validate_site.py`。
4. 对外接口（`docs/data/domain-index.json`）字段**只增不改名**；新增字段一律可选、缺省不影响旧消费方。
5. 任何"口径"层面的变化（谁能算、算什么、按哪一版），同步更新 `coverage.json` 的 `当前完整有效性结论` 与页面文案，不能只改数据。

## 变更记录

| 版本 | 日期 | 内容 |
|---|---|---|
| 1.0 | 2026-10 | 初始 schema：主体/服务/网站三类记录，含证据哈希与版本日期 |
| — | 2026-11-10 | 补全域名（西藏 19 条）、网站记录 100% 含域名；本文件建立 |
