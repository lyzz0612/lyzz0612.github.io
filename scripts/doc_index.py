#!/usr/bin/env python3
"""
与 llms.txt / README 文章表共享：扫描仓库内带 front matter 的文档、解析标题与日期。
"""

from __future__ import annotations

import os
import re
from collections import defaultdict
from pathlib import Path

# 站点在浏览器中的根 URL（自定义域名或 *.github.io），供 llms / README 表格链接使用
DEFAULT_SITE_BASE_URL = os.environ.get(
    "SITE_BASE_URL", "https://agent-doc.skyup.top"
).rstrip("/")

ROOT = Path(__file__).resolve().parents[1]

SKIP_DIR_PARTS = frozenset({".git", "node_modules", "vendor", ".venv", "venv"})
DOC_SUFFIXES = {".md", ".html", ".htm"}


def has_front_matter_fence(text: str) -> bool:
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
        # 站点入口页，不参与 llms.txt / README 文章表
        if rel.as_posix() == "index.html":
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
    rel = path.relative_to(root)
    parts = rel.parts
    if len(parts) <= 1:
        return ""
    return parts[0]


def group_by_directory(files: list[Path]) -> list[tuple[str, list[Path]]]:
    buckets: dict[str, list[Path]] = defaultdict(list)
    for f in files:
        buckets[top_level_dir_key(f, ROOT)].append(f)
    for k in buckets:
        buckets[k].sort(key=lambda p: p.as_posix().lower())
    keys = sorted(buckets.keys(), key=lambda s: ("\0" if s == "" else s))
    return [(k, buckets[k]) for k in keys]


def section_heading(dir_key: str) -> str:
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


def _fm_field(path: Path, key: str) -> str:
    """读取 front matter 中指定字段，无则返回「—」。"""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "—"
    suf = path.suffix.lower()
    if suf in (".md", ".html", ".htm"):
        fm, _ = split_front_matter(text)
        v = (fm.get(key) or "").strip()
        return v if v else "—"
    return "—"


def page_date(path: Path) -> str:
    """front matter 的 date 字段。"""
    return _fm_field(path, "date")


def page_last_modified(path: Path) -> str:
    """front matter 的 last_modified 字段。"""
    return _fm_field(path, "last_modified")


def page_url(rel_posix: str, base_url: str) -> str:
    """仓库内相对路径对应的「源文件」URL（仍以 .md 结尾）。"""
    return f"{base_url.rstrip('/')}/{rel_posix}"


def site_page_url(rel_posix: str, base_url: str | None = None) -> str:
    """
    Jekyll 构建后用于浏览器访问的 URL：`.md` → `.html`；
    根目录 `README.md` 使用站点首页 `/`（permalink）。
    """
    base = (base_url or DEFAULT_SITE_BASE_URL).rstrip("/")
    rel = rel_posix.replace("\\", "/").strip("/")
    parts = rel.split("/")
    if parts and parts[-1].lower() == "readme.md":
        return f"{base}/"
    if rel.lower().endswith(".md"):
        rel = rel[:-3] + ".html"
    return f"{base}/{rel}"
