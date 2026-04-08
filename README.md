---
title: "Agent文档平台"
description: "lyzz0612.github.io：GitHub Pages 站点说明、llms.txt 自动生成规则与维护约定。"
date: 2026-04-08
layout: default
---

# Agent文档平台

本仓库为 **`https://lyzz0612.github.io/`**，内容同时面向人类读者与自动化 Agent（代码助手、CI、检索工具等）。

## llms.txt（大模型索引）

站点根路径提供符合 [llmstxt.org](https://llmstxt.org/) 约定的索引文件：

- **在线地址**：[https://lyzz0612.github.io/llms.txt](https://lyzz0612.github.io/llms.txt)

**生成方式**：由 `scripts/generate_llms_txt.py` 扫描仓库生成；推送 `main` / `master` 时，工作流 [`.github/workflows/pages.yml`](.github/workflows/pages.yml) 会在构建阶段运行该脚本，再将静态文件部署到 Pages，因此线上 **`/llms.txt` 以 CI 构建结果为准**。

## 文章列表（人工备忘，可选）

> 以下为可选的手工表格，便于写稿计划；**对外机器可读索引以 `llms.txt` 为准**。

| 标题 | 路径或 URL | 日期 |
|------|------------|------|
| （暂无） | — | — |
