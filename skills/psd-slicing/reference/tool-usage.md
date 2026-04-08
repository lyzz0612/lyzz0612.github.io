# `psd_slicing_tools.py` 使用说明

脚本路径（相对本 skill 根目录）：`scripts/psd_slicing_tools.py`。完整参数以 `python scripts/psd_slicing_tools.py <子命令> --help` 为准。

## 环境与依赖

- 使用本机 `python`（或项目约定解释器）调用脚本。
- 依赖：`psd-tools`、`Pillow`（`PIL`）。导入失败时先安装依赖，勿把「改提示词」当成「工具已可用」。
- 可选：设置环境变量 `PSD_SLICING_LOG_FILE` 为路径时，会向该文件写调试日志；默认不写盘，避免只读调用产生副作用。

## 标准输出与写盘

- **`list_layers`、`get_layer_info`、`get_image_size` 等只读类命令不要重定向到文件**（不要用 `> 文件`）：直接执行，从标准输出读取；重定向易多余写盘或触发权限确认。
- 仅**最终切图结果表**等业务文档写入项目 `docs/` 等约定路径；中间分析输出一律用 stdout。

## 子命令一览

| 子命令 | 用途 |
|--------|------|
| `list_layers` | 列出 PSD 图层树 |
| `get_layer_info` | 单个图层详情 |
| `set_layer_visibility` | 显隐图层并保存 PSD |
| `isolate_layers` | 只保留指定层可见/或隐藏指定层 |
| `export_layer` | 导出图层或整 PSD 合成为图片 |
| `get_image_size` | 读图片宽高 |
| `resize_image_canvas` | 扩画布（透明填充），用于统一尺寸 |
| `scale_image` | 按比例缩放整张图 |
| `crop_image` | 按区域或内容裁剪 |

## 常用约定

- **`--file-path`**：PSD 或图片的绝对路径。
- **多图层 / 多显隐**：用**重复参数**，例如多次 `--layer-path`、`--hide-layer`、`--show-layer`，避免图层名含逗号时歧义。
- **临时 PSD**：改显隐时用 `set_layer_visibility` 或 `isolate_layers` 的 `--output-path` 写出临时文件，再对临时 PSD 调用 `export_layer`；不要覆盖用户原始 PSD。
- **`export_layer`**：临时 PSD 若可删，导出时可设 `--cleanup-psd true`（以 `--help` 为准）。需要全屏分析图时用 `--all` 导出整 PSD 合成（参数名以脚本为准）。

## 调用示例

以下路径请替换为实际绝对路径。

```text
python scripts/psd_slicing_tools.py list_layers --file-path "E:\ui.psd" --raw
python scripts/psd_slicing_tools.py get_layer_info --file-path "E:\ui.psd" --layer-path "Group/Button"
python scripts/psd_slicing_tools.py export_layer --file-path "E:\ui.psd" --layer-path "Group/Button" --output-path "E:\out\btn.png"
python scripts/psd_slicing_tools.py set_layer_visibility --file-path "E:\ui.psd" --hide-layer "文本" --output-path "E:\tmp\slice.psd"
python scripts/psd_slicing_tools.py isolate_layers --file-path "E:\ui.psd" --layer-path "Group/Button" --layer-path "Group/Glow" --output-path "E:\tmp\slice.psd"
python scripts/psd_slicing_tools.py resize_image_canvas --file-path "E:\out\icon.png" --output-path "E:\out\icon_128.png" --width 128 --height 128 --anchor center
```

## 与工作流程的对应关系

- **步骤 1**：能跑通 `--help` 或只读子命令即视为工具可用。
- **步骤 2**：规划阶段会用到 `list_layers`、`get_layer_info`；规则见 [layer-export-planning.md](./layer-export-planning.md)。
- **步骤 3–4**：显隐与导出用 `set_layer_visibility` / `isolate_layers` / `export_layer`；统一尺寸用 `get_image_size` + `resize_image_canvas`（扩画布、**不**用 `scale_image` 拉伸内容）。
- **统一尺寸策略（配合 `resize_image_canvas`）**：以该组资源最大边为基准定正方形边长；可优先取最小够用的 2 次幂（如 `128`、`256`）；若留白过大再退到不小于最大边长的整百尺寸；`anchor` 用 `center`。
