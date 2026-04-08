#!/usr/bin/env python3
"""
扫描仓库内文档文件，生成根目录 llms.txt。

版式遵循 https://llmstxt.org/ ：H1、引用摘要、若干 ## 小节，小节内为
`- [链接文字](URL): 可选说明` 列表。

**分区规则**：只按**第一层目录**分组——根目录文件一节「根目录」，`foo/bar/b.md` 与 `foo/x/y.md` 同属 `## foo`。

**Markdown**：必须带页首 YAML front matter（`---` … `---`），否则忽略该 `.md`。

**标题**：`.md` 读 front matter `title`，缺省则用正文首个 `#`；`.html` / `.htm` 仍收录，标题为 front matter `title` 或 `<title>`。

列表项只输出 `- [标题](URL)`，无 description。

环境变量：
  LLMS_TXT_PATH   输出路径，默认仓库根目录 llms.txt
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_scripts_dir = Path(__file__).resolve().parent
if str(_scripts_dir) not in sys.path:
    sys.path.insert(0, str(_scripts_dir))

from doc_index import (
    DEFAULT_SITE_BASE_URL,
    ROOT,
    group_by_directory,
    iter_doc_files,
    page_title,
    section_heading,
    site_page_url,
)

OUT = Path(os.environ.get("LLMS_TXT_PATH", str(ROOT / "llms.txt")))
BASE_URL = DEFAULT_SITE_BASE_URL


def build_llms_text(grouped: list[tuple[str, list[Path]]]) -> str:
    lines = [
        "# lyzz0612.github.io",
        "",
        "> GitHub Pages 站点。按 llmstxt.org 约定：每个 `##` 对应**第一层目录**（或根目录）；`.md` 须含 YAML front matter，否则不收录。",
        "",
    ]
    if not grouped:
        lines.extend(
            [
                "## 根目录",
                "",
                "- （当前仓库未发现符合条件的文档：`.md` 需含 front matter；或均被排除规则跳过。）",
                "",
            ]
        )
    else:
        for dir_key, paths in grouped:
            lines.append(f"## {section_heading(dir_key)}")
            lines.append("")
            for f in paths:
                rel = f.relative_to(ROOT).as_posix()
                label = page_title(f)
                url = site_page_url(rel, BASE_URL)
                lines.append(f"- [{label}]({url})")
            lines.append("")
    return "\n".join(lines)


def main() -> None:
    files = iter_doc_files(ROOT)
    grouped = group_by_directory(files)
    out = build_llms_text(grouped)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(out, encoding="utf-8", newline="\n")
    n_dirs = len(grouped)
    print(f"Wrote {OUT} ({len(files)} file(s), {n_dirs} director{'y' if n_dirs == 1 else 'ies'})")


if __name__ == "__main__":
    main()
