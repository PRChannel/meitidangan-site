# 全国来源集中采集 · GitHub 运行包

请把本包中以下四项复制到已有 **私有** GitHub 仓库，保持相对路径：

- `fasttrack_batch.py`（根目录，新文件）
- `fasttrack_attachments.py`（根目录，新文件）
- `official_sources_nationwide_32.json`（根目录，新文件）
- `.github/workflows/fasttrack.yml`（新增工作流）

不要覆盖现有 `national.yml`、`national_source_batch.py`、`docs/`、`.github/workflows/pilot.yml`、`official_sources_32.csv`。

使用 GitHub Desktop：Repository → Show in Finder，复制文件到对应位置，再 Changes → Commit to main → Push origin。

在 GitHub 网页进入 Actions → **National registry fast-track (manual)** → Run workflow (main)。应有5个 jobs：4个来源批次和1个附件任务。

完成后下载所有 `fasttrack-sources-*` 和 `fasttrack-attachment-review` Artifacts 发回分析。HTTP失败、格式异常均记录于报告，不代表非法或未获许可。

安全边界：程序只下载低频公共资料，不绕过访问控制，不修改生产库，不写入 docs 网站，不发布审核未通过记录；个别地方入口可能对应旧公告，结果必须审核。当前 31 个入口只是待确认来源，并非完成全国采集。
