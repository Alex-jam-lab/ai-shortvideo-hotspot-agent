"""输入预处理：清洗、去重、按信息密度截断。

目的：
- 去零宽/控制字符与高频乱码，降低对模型注意力的干扰
- 去除刷屏式重复评论，保留高信息密度内容
- 按字符上限截断，避免 Token 浪费
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

# 零宽字符、BOM、软连字符等
_ZERO_WIDTH = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2060\ufeff\u00ad]")
# 连续同类符号（如 !!!!!!、哈哈哈哈）折叠为最多 3 个
_REPEAT_SYMBOL = re.compile(r"([^\w\s])\1{3,}")
_REPEAT_CHAR = re.compile(r"(\w)\1{5,}")
# 连续空白
_MULTI_SPACE = re.compile(r"[ \t\u3000]{2,}")
# 连续空行
_MULTI_NEWLINE = re.compile(r"\n{3,}")


@dataclass
class PreprocessResult:
    """预处理结果与统计。"""

    text: str
    original_chars: int
    cleaned_chars: int
    truncated: bool
    deduped_lines: int
    kept_lines: int
    notes: list[str] = field(default_factory=list)


def clean_text(text: str) -> str:
    """基础清洗：去零宽/控制字符、折叠重复符号、规范空白。"""
    if not text:
        return ""
    # 保留换行，去除其他控制字符
    chars: list[str] = []
    for ch in text:
        if ch in "\n\r\t":
            chars.append("\n" if ch in "\r\n" else "\t")
            continue
        category = unicodedata.category(ch)
        if category in {"Cc", "Cf"}:
            continue
        chars.append(ch)
    cleaned = "".join(chars)

    cleaned = _ZERO_WIDTH.sub("", cleaned)
    cleaned = _REPEAT_SYMBOL.sub(r"\1\1\1", cleaned)
    cleaned = _REPEAT_CHAR.sub(r"\1\1\1", cleaned)
    cleaned = _MULTI_SPACE.sub(" ", cleaned)
    return cleaned


def dedupe_lines(text: str) -> tuple[str, int]:
    """按行去重（忽略空白与大小写差异），保留首次出现顺序。"""
    seen: set[str] = set()
    kept: list[str] = []
    removed = 0
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        key = re.sub(r"\s+", "", line).lower()
        if key in seen:
            removed += 1
            continue
        seen.add(key)
        kept.append(line)
    return "\n".join(kept), removed


def rank_lines_by_density(text: str) -> str:
    """按信息密度重排评论行：字符数越多越靠前（更可能为高赞长评）。

    保留原顺序作为同长度时的稳定次序。
    """
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if len(lines) <= 1:
        return text
    indexed = list(enumerate(lines))
    # 稳定排序：先按长度降序，再按原索引升序
    indexed.sort(key=lambda pair: (-len(pair[1]), pair[0]))
    return "\n".join(line for _, line in indexed)


def truncate_text(text: str, max_chars: int) -> tuple[str, bool]:
    """按字符上限截断，尽量在换行处断开。"""
    if max_chars <= 0 or len(text) <= max_chars:
        return text, False
    window = text[:max_chars]
    newline_idx = window.rfind("\n")
    if newline_idx > max_chars * 0.6:
        window = window[:newline_idx]
    return window.rstrip() + "\n…（内容过长，已截断）", True


def preprocess_raw_text(
    raw_text: str,
    max_chars: int = 3000,
    *,
    dedupe: bool = True,
    reorder_by_density: bool = True,
) -> PreprocessResult:
    """对评论原文执行完整预处理流水线。"""
    original_chars = len(raw_text or "")
    notes: list[str] = []

    cleaned = clean_text(raw_text or "")
    if original_chars and len(cleaned) != original_chars:
        notes.append("已清洗零宽/控制字符与重复符号")

    deduped = 0
    if dedupe:
        cleaned, deduped = dedupe_lines(cleaned)
        if deduped:
            notes.append(f"已去除 {deduped} 条重复评论")

    if reorder_by_density:
        cleaned = rank_lines_by_density(cleaned)

    truncated_text, truncated = truncate_text(cleaned, max_chars)
    if truncated:
        notes.append(f"已按上限 {max_chars} 字符截断")

    return PreprocessResult(
        text=truncated_text,
        original_chars=original_chars,
        cleaned_chars=len(truncated_text),
        truncated=truncated,
        deduped_lines=deduped,
        kept_lines=len([ln for ln in truncated_text.splitlines() if ln.strip()]),
        notes=notes,
    )
