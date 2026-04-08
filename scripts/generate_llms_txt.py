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
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(os.environ.get("LLMS_TXT_PATH", str(ROOT / "llms.txt")))

BASE_URL = "https://lyzz0612.github.io".rstrip("/")

SKIP_DIR_PARTS = frozenset({".git", "node_modules", "vendor", ".venv", "venv"})
DOC_SUFFIXES = {".md", ".html", ".htm"}


def has_front_matter_fence(text: str) -> bool:
    """页首存在成对的 `---` / `---`（YAML front matter 外壳）。"""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return False
    for line in lines[1:]:
        if line.strip() == "---":
            return True
    return False


def iter_doc_files(root: Path) -> list[Path]:
    found: list[Path] = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(root)
        if any(part in SKIP_DIR_PARTS for part in rel.parts):
            continue
        if p.name == "llms.txt":
            continue
        suf = p.suffix.lower()
        if suf not in DOC_SUFFIXES:
            continue
        if suf == ".md":
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if not has_front_matter_fence(text):
                continue
        found.append(p)
    return sorted(found, key=lambda x: x.as_posix().lower())


def top_level_dir_key(path: Path, root: Path) -> str:
    """
    仅按第一层目录分组：根下文件为 ''；`foo/a.md` 与 `foo/x/y.md` 的键均为 `foo`。
    """
    rel = path.relative_to(root)
    parts = rel.parts
    if len(parts) <= 1:
        return ""
    return parts[0]


def group_by_directory(files: list[Path]) -> list[tuple[str, list[Path]]]:
    """按第一层目录分组，返回 [(dir_key, paths), ...]，根目录键 '' 优先，其余按目录名排序。"""
    buckets: dict[str, list[Path]] = defaultdict(list)
    for f in files:
        buckets[top_level_dir_key(f, ROOT)].append(f)
    for k in buckets:
        buckets[k].sort(key=lambda p: p.as_posix().lower())
    keys = sorted(buckets.keys(), key=lambda s: ("\0" if s == "" else s))
    return [(k, buckets[k]) for k in keys]


def section_heading(dir_key: str) -> str:
    """用于 ## 标题：根目录显示为「根目录」，否则为 posix 路径。"""
    return "根目录" if dir_key in ("", ".") else dir_key


def _unquote_yaml_scalar(s: str) -> str:
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        inner = s[1:-1]
        if s[0] == '"':
            return inner.replace('\\"', '"').replace("\\\\", "\\")
        return inner.replace("\\'", "'")
    return s


def split_front_matter(text: str) -> tuple[dict[str, str], str]:
    """解析 `---` … `---` 块，返回 (键值对, 其后正文)。"""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    fm_lines: list[str] = []
    i = 1
    while i < len(lines):
        if lines[i].strip() == "---":
            rest = "\n".join(lines[i + 1 :])
            break
        fm_lines.append(lines[i])
        i += 1
    else:
        return {}, text
    fm: dict[str, str] = {}
    for line in fm_lines:
        m = re.match(r"^([a-zA-Z0-9_]+)\s*:\s*(.*)$", line.rstrip())
        if not m:
            continue
        k, v = m.group(1), _unquote_yaml_scalar(m.group(2))
        if v or k not in fm:
            fm[k] = v
    return fm, rest


def md_first_heading_in_body(body: str) -> str | None:
    for line in body.splitlines()[:120]:
        m = re.match(r"^#\s+(.+?)\s*$", line.strip())
        if m:
            return m.group(1).strip()
    return None


def page_title(path: Path) -> str:
    """
    仅解析用于链接文字的标题：Markdown 为 front matter `title` 或正文首个 `#`；
    HTML 为 front matter `title` 或 `<title>`。不使用 front matter 的 description。
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return path.name

    suf = path.suffix.lower()
    if suf == ".md":
        fm, body = split_front_matter(text)
        title = (fm.get("title") or "").strip()
        if title:
            return title
        return md_first_heading_in_body(body) or path.name

    if suf in {".html", ".htm"}:
        fm, after = split_front_matter(text)
        title = (fm.get("title") or "").strip()
        if title:
            return title
        m = re.search(r"<title[^>]*>\s*(.+?)\s*</title>", after, re.I | re.DOTALL)
        if m:
            return re.sub(r"\s+", " ", m.group(1)).strip()
        return path.name

    return path.name


def page_url(rel_posix: str) -> str:
    return f"{BASE_URL}/{rel_posix}"


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
                url = page_url(rel)
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
