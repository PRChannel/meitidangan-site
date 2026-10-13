# 中国媒体身份资料库 GitHub Pages 上传包

正式域名：meitidangan.com。静态网站已经生成，可从 `docs` 目录直接发布，无需 Node、数据库或 PHP。

本次公开898条已核对名单版本记录，保留统计截止日期、公告发布日期、原始来源和证据编号。记录不代表实时许可有效性。22省取得网站行表，9省仍缺原件，覆盖页面如实列示。428条待审完整明细只在另外的审核交付包中，不载入本站公开数据。

## 上传并发布

1. 使用 GitHub Desktop 克隆你的仓库；将本包文件复制到仓库根目录。目录结构应当是 `仓库/docs/index.html`，不能多套一层文件夹。
2. 如果替换现有站点，先备份原仓库，再以本包 `docs` 整个目录替换旧 `docs`，避免旧400条预览页面残留。原始审核交付包另存，不能直接当作网站数据上传。
3. Commit 后 Push 到 GitHub。
4. 在仓库 Settings → Pages 中，Source 选择 Deploy from a branch，选择实际上传分支（通常 main），文件夹选 `/docs`，然后 Save。
5. 等 Pages 发布完成后，检查首页、媒体查询和一条媒体详情页。包内链接使用相对路径，也可在 GitHub 项目页面的子路径下工作。
6. 设置正式域名时，在 Pages 的 Custom domain 填 `meitidangan.com` 并按 GitHub 指引完成 DNS 和域名验证。本包包含对应 CNAME，但文件本身不替代仓库域名设置与DNS操作。HTTPS 就绪后启用 Enforce HTTPS。

GitHub 官方发布说明：https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site

由于生成了898个独立详情页，建议 GitHub Desktop 或 Git 提交整个目录，避免网页上传文件数量限制。

## 目录

- `docs/`：已经生成的可发布页面、公开JSON、站点地图、robots、CNAME。
- `data/public-records.json`：898条通过审核的对应版本记录，保留原ID。
- `data/coverage.json`：31省来源覆盖状态与缺口。
- `data/official-sources.csv`：各许可范围的来源入口索引。
- `data/articles.json`：保留原站三篇核验与实务研究文章。
- `site/`：样式与查询脚本，深蓝灰、直角风格。
- `build_site.py`：仅用Python标准库重新生成站点。
- `tools/validate_site.py`：检查所有页面、内部链接、数据范围和站点地图。

## 后续更新

审核通过后才能修改 `data/public-records.json`。不要把1326条候选总表或428条待审清单直接替换公开JSON。重新生成时，`docs` 是构建产物目录，会被完整重建，手工页面修改应在生成脚本或 `site` 中完成。

```bash
python3 build_site.py
python3 tools/validate_site.py
python3 -m http.server 8000 --directory docs
```

本地访问 http://localhost:8000/ 检查后再提交。构建当前固定为898条审核快照，未来调整条数时也要更新构建断言、首页统计、方法页和校验口径，不能只改一个显示数字。

## SEO与事实边界

每条媒体记录有独立静态URL、标题、描述、canonical及WebPage结构化数据，内容不依赖浏览器渲染。首页有Dataset结构化数据。站点地图不纳入404页。永久URL基于原记录ID，同证不同服务项不自动合并。

当前发布渠道尚未配置公开反馈受理地址，页面没有虚构邮箱、提交表单或备案号码。运营主体如实披露为荆门暗猫网络科技有限公司，与暗传播的业务关联及数据支持只在关于页面说明。

构建不会抓取或自动发布未经审核的新数据，也不会修改GitHub仓库设置。部署成功、域名解析和HTTPS状态须在实际仓库上确认，本包不代表网站已经上线。

## 与原仓库的兼容及验证范围

请先阅读 `上传说明.md`。本包保留原采集脚本、手动工作流与历史审核文件，旧说明归档在 `legacy-notes/`。旧工作流的外部历史产物依赖未验证。网站静态校验已通过；浏览器交互、移动端视觉和线上部署未验证。
