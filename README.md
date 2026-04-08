---
title: "Agent文档平台"
description: "lyzz0612.github.io：GitHub Pages 站点说明、llms.txt 自动生成规则与维护约定。"
date: 2026-04-08
last_modified: 2026-04-08
layout: default
permalink: /
---

# Agent文档平台

本站（浏览器）：**[https://agent-doc.skyup.top/](https://agent-doc.skyup.top/)**。构建时除 `scripts/`、`.github/` 等工程目录外，仓库内源文件（各路径下的 `.md`、`llms.txt`、`CNAME` 等）会一并发布，可与 Jekyll 生成的 `.html` 同源访问；根目录 **[README.md](https://agent-doc.skyup.top/README.md)** 供 Agent / `llms.txt` 拉取。内容同时面向人类读者与自动化 Agent（代码助手、CI、检索工具等）。

## llms.txt（大模型索引）

站点根路径提供符合 [llmstxt.org](https://llmstxt.org/) 约定的索引文件：

- **在线地址**：[https://agent-doc.skyup.top/llms.txt](https://agent-doc.skyup.top/llms.txt)

**生成方式**：由 [`scripts/generate_llms_txt.py`](https://github.com/lyzz0612/lyzz0612.github.io/blob/master/scripts/generate_llms_txt.py) 扫描仓库生成；推送 `main` / `master` 时，工作流 [`.github/workflows/pages.yml`](https://github.com/lyzz0612/lyzz0612.github.io/blob/master/.github/workflows/pages.yml) 会在构建阶段运行该脚本，再将静态文件部署到 Pages，因此线上 **`/llms.txt` 以 CI 构建结果为准**。

## 文章列表（CI 自动同步）

> 下表由 [`scripts/update_readme_articles.py`](https://github.com/lyzz0612/lyzz0612.github.io/blob/master/scripts/update_readme_articles.py) 按与 `llms.txt` 相同的收录规则生成；推送 `main` / `master` 时由 [`.github/workflows/pages.yml`](https://github.com/lyzz0612/lyzz0612.github.io/blob/master/.github/workflows/pages.yml) 更新并提交。「页面地址」列为**站点上可打开的 URL**（对应 Jekyll 输出的 `.html`）。

<!-- doc-index:article-table -->

| 标题 | 页面地址 | 修改时间 |
|------|----------|----------|
| PSD 切图工作流 | [skills/psd-slicing/SKILL.html](https://agent-doc.skyup.top/skills/psd-slicing/SKILL.html) | 2026-04-08 |
<!-- /doc-index:article-table -->
