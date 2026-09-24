"""输入预处理测试（离线）。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hotspot_analysis.preprocess import (  # noqa: E402
    clean_text,
    dedupe_lines,
    preprocess_raw_text,
    rank_lines_by_density,
    truncate_text,
)


def test_clean_text_removes_zero_width_and_control_chars() -> None:
    raw = "正常\u200b文本\ufeff带零宽\u0007控制符"
    assert clean_text(raw) == "正常文本带零宽控制符"


def test_clean_text_collapses_repeated_symbols() -> None:
    assert clean_text("太棒了!!!!!!!!") == "太棒了!!!"
    assert clean_text("哈哈哈哈哈哈哈哈哈") == "哈哈哈"


def test_clean_text_keeps_newlines() -> None:
    assert clean_text("第一行\n第二行").count("\n") == 1


def test_dedupe_lines_removes_duplicates() -> None:
    text = "评论A\n评论A\n评论B\n评论A "
    kept, removed = dedupe_lines(text)
    assert removed == 2
    assert kept == "评论A\n评论B"


def test_rank_lines_by_density_orders_long_first() -> None:
    text = "短\n这是一条很长的评论内容\n中等的评论"
    ranked = rank_lines_by_density(text).splitlines()
    assert ranked[0] == "这是一条很长的评论内容"


def test_truncate_text_cuts_and_marks() -> None:
    text = "\n".join([f"第{i}条评论内容" for i in range(100)])
    out, truncated = truncate_text(text, 50)
    assert truncated is True
    assert "已截断" in out
    assert len(out) <= 60


def test_truncate_no_op_when_short() -> None:
    out, truncated = truncate_text("很短", 100)
    assert out == "很短"
    assert truncated is False


def test_preprocess_pipeline_stats() -> None:
    # 使用互不相同的长文本，避免被「重复字符折叠」规则压缩
    long_lines = [f"第{i}条很长的评论内容用来触发截断逻辑" for i in range(50)]
    raw = "评论A\n评论A\n评论B\n" + "\n".join(long_lines)
    result = preprocess_raw_text(raw, max_chars=200)
    assert result.deduped_lines == 1
    assert result.truncated is True
    assert result.original_chars == len(raw)
    assert result.cleaned_chars <= 200 + 30
    assert any("重复" in n for n in result.notes)
    assert any("截断" in n for n in result.notes)


def test_preprocess_collapses_long_repeated_char_run() -> None:
    # 刷屏式重复字符会被折叠，从而降低 Token 消耗
    result = preprocess_raw_text("刷屏" + "x" * 5000, max_chars=3000)
    assert result.cleaned_chars < 20
    assert result.truncated is False
