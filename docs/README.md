# docs/ — 文档来源

这个目录是站点的**权威数据**：每份 markdown 会由 `tools/build_site.py` 渲染成站内页面 `d/**/*.html`，
并自动出现在首页 `index.html` 的索引里（日期倒序）。构建在 GitHub Actions 里跑，提交后约一分钟生效。

## 写一份文档

新建 `docs/年份/标题.md`，开头可选写 front matter：

```markdown
---
title: 矩阵分解与推荐系统 · 读书笔记
type: 笔记
date: 2026-09-28
summary: 一句话摘要，用于页面 description
---

正文从这里开始，正常写 markdown（标题、列表、代码块、表格、图片都支持）。
```

| 字段 | 作用 | 省略时 |
|---|---|---|
| `title` | 索引与文档页显示的标题 | 用文件名 |
| `type` | 右侧类型标签：笔记 / 论文 / 项目 … | 显示「—」 |
| `date` | 索引排序用的日期，`YYYY-MM-DD` | 用文件最后修改时间 |
| `slug` | 自定义输出路径（不含 `.html`） | 沿用 `docs/` 下的相对路径 |
| `summary` | 页面 `<meta name="description">` | 留空 |
| `draft` | 写 `true` 则跳过：不渲染、不进索引 | 正常发布 |

## 约定

- 文件名以 `_` 开头、或名为 `README.md` 的文件**不进索引**（本文件、模板、草稿都用这个规则）。
- 图片等附件直接放在 `docs/` 里，用相对路径引用，例如 `![](img/图.png)`；构建时按原路径复制到 `d/`，链接照常可用。
- `d/` 与 `index.html` 的索引区块**都是生成物，不要手改**：`d/` 下不再属于任何文档的文件会在下次构建时被删除。
- 本地预览：`pip install -r tools/requirements.txt && python3 tools/build_site.py --root .`，
  然后在仓库根目录起个静态服务器（`python3 -m http.server`）打开 `index.html`。
