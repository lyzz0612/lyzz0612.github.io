---
name: PSD切图的技能
description: 使用内置 psd_slicing_tools.py 从 PSD 导出可复用 UI 素材。适用于用户提供 PSD、要求切图或按图层拆图/批量导出、导出按钮/背景/图标等素材，或需要「图层-功能-切图」对应表等场景。
---

# PSD 切图工作流

基于 skill 内置的 `scripts/psd_slicing_tools.py`，从 PSD 导出可复用 UI 素材。命令与子命令说明见 [reference/tool-usage.md](./reference/tool-usage.md)。

## 何时使用

- 用户提供 PSD 路径并要求切图、导出素材、按图层拆图、批量导出
- 需要按钮、背景、图标、装饰等 UI 资源
- 需要「图层 / 功能 / 切图」对应表

## 工作流程

- 任务全程维护**运行时清单**（资源名、用途、路径、使用/隐藏图层、失败与重导原因），**不要**事后扫目录代替。

### 1. 检测工具是否可用、是否安装依赖

- 见 [tool-usage.md § 环境与依赖](./reference/tool-usage.md#环境与依赖)；能跑通 `--help` 或只读子命令即视为可用。不能跑通不能进行下一步

### 2. 决定哪些图层要导出、怎么导出

- 严格按照[layer-export-planning.md](./reference/layer-export-planning.md)规划导出图层和导出方案。
- 正式导出前必须先列导出计划；所有显隐调整输出到**临时 PSD**，不覆盖原 PSD。

### 3. 执行工具导出

- 必须严格按照**2**的导出方案来执行
- 子命令、参数、示例见 [tool-usage.md](./reference/tool-usage.md)。

### 4. 复检与后处理

- 每张导出结果**必须**做**观感**与用途检查：误带文字、夹带无关层、白边/残片、缺失内容等；有异常则分析显隐或图层组合后必须重新导出；循环复检直到没有问题或决定放弃。
- **2**步骤判断是列表的项，需要**统一画布尺寸**（`get_image_size` + `resize_image_canvas` 扩画布、不拉伸内容；示例见 [tool-usage.md](./reference/tool-usage.md)）。
- 输出目录：用户指定则遵从；否则默认 `PSD 所在目录/<feature_en>/`（`feature_en` 小写+下划线；无法判断语义时用 `ui_assets`）；临时 PSD 放在同目录。
- 删除临时文件

### 5. 生成导出记录

- 最终用简洁中文回复，含：`图层 | 功能 | 切图` 表格、失败/放弃项及原因。
- 同步写入 Markdown：默认 `docs/<feature_en>_slice_result.md`（无法判定功能名时用 `ui_assets_slice_result.md`）；用户指定路径则按用户路径。回复末尾给出结果文件绝对路径。

## 参考

- 工具使用说明（依赖、子命令、示例）：[reference/tool-usage.md](./reference/tool-usage.md)
- 导出范围与合并/命名判定：[reference/layer-export-planning.md](./reference/layer-export-planning.md)
- 源码：`scripts/psd_slicing_tools.py`
