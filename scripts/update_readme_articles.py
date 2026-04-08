#!/usr/bin/env python3
"""
根据与 llms.txt 相同的收录规则，更新 README.md 中「文章列表」表格（标记块内）。
排除仓库根目录的 README.md 自身。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# 与 generate_llms_txt 同目录，保证 `python3 scripts/update_readme_articles.py` 可导入 doc_index
sys.path.insert(0, str(Path(__file__).resolve().parent))

from doc_index import (  # noqa: E402
    DEFAULT_SITE_BASE_URL,
    ROOT,
    iter_doc_files,
    page_last_modified,
    page_title,
    site_page_url,
)

README_PATH = ROOT / "README.md"
BASE_URL = DEFAULT_SITE_BASE_URL

MARKER_START = "<!-- doc-index:article-table -->"
MARKER_END = "<!-- /doc-index:article-table -->"


def _escape_cell(s: str) -> str:
    return s.replace("|", "\\|").replace("\n", " ")


def build_table_markdown(files: list[Path]) -> str:
    lines = [
        "| 标题 | 页面地址 | 修改时间 |",
        "|------|----------|----------|",
    ]
    if not files:
        lines.append("| （暂无） | — | — |")
        return "\n".join(lines)

    # 按 last_modified 倒序，无日期的排最后
    files_sorted = sorted(files, key=lambda f: page_last_modified(f), reverse=True)
    for f in files_sorted:
        rel = f.relative_to(ROOT).as_posix()
        title = _escape_cell(page_title(f))
        url = site_page_url(rel, BASE_URL)
        link_label = rel[:-3] + ".html" if rel.lower().endswith(".md") else rel
        modified = _escape_cell(page_last_modified(f))
        lines.append(f"| {title} | [{_escape_cell(link_label)}]({url}) | {modified} |")
    return "\n".join(lines)


def replace_marked_block(readme_text: str, new_block_body: str) -> str:
    pattern = re.compile(
        re.escape(MARKER_START) + r"\s*.*?\s*" + re.escape(MARKER_END),
        re.DOTALL,
    )
    replacement = f"{MARKER_START}\n{new_block_body}\n{MARKER_END}"
    if not pattern.search(readme_text):
        raise ValueError(
            f"README 中未找到标记块 {MARKER_START!r} … {MARKER_END!r}"
        )
    return pattern.sub(replacement, readme_text, count=1)


def main() -> int:
    files = [
        f
        for f in iter_doc_files(ROOT)
        if f.resolve() != (ROOT / "README.md").resolve()
    ]
    table_md = build_table_markdown(files)
    text = README_PATH.read_text(encoding="utf-8")
    updated = replace_marked_block(text, table_md)
    if updated != text:
        README_PATH.write_text(updated, encoding="utf-8", newline="\n")
        print(f"Updated {README_PATH} ({len(files)} article(s))")
    else:
        print(f"No changes to {README_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
