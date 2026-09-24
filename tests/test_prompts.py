"""提示词组装测试（离线）。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hotspot_analysis.prompts import (  # noqa: E402
    SYSTEM_PROMPT,
    build_repair_prompt,
    build_user_prompt,
)


def test_system_prompt_covers_four_steps() -> None:
    for token in ["噪声过滤", "情绪解构", "传播引爆点", "行动落地"]:
        assert token in SYSTEM_PROMPT


def test_user_prompt_embeds_keyword_and_schema() -> None:
    prompt = build_user_prompt("测试词条", "评论内容")
    assert "测试词条" in prompt
    assert "评论内容" in prompt
    assert "is_valuable_trend" in prompt


def test_user_prompt_handles_empty_text() -> None:
    prompt = build_user_prompt("测试词条", "")
    assert "暂无评论文本" in prompt


def test_repair_prompt_truncates_long_output() -> None:
    raw = "x" * 10000
    prompt = build_repair_prompt(raw, "boom")
    assert "已截断" in prompt
    assert "boom" in prompt
