"""分析器端到端测试：mock 大模型响应，验证完整链路（离线）。

覆盖：正常解析、JSON 代码块剥离、修复重试、缺 Key 报错。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hotspot_analysis.analyzer import AnalyzerError, HotspotAnalyzer  # noqa: E402
from hotspot_analysis.config import ConfigError, Settings  # noqa: E402

VALID_PAYLOAD: dict[str, Any] = {
    "meta": {},
    "noise_filtering": {
        "is_valuable_trend": True,
        "is_noise": False,
        "noise_type": "有效话题",
        "noise_reason": "真实共鸣。",
        "value_score": 80,
    },
    "emotion_decoding": {
        "status": "done",
        "pain_points": ["焦虑"],
        "core_emotions": ["共鸣"],
        "collective_unconscious": ["抱团"],
        "emotion_intensity": 70,
        "summary": "s",
    },
    "viral_mechanism": {
        "status": "done",
        "triggers": ["t1"],
        "visual_conflict": "无",
        "controversy_level": 60,
        "rarity": "低",
        "secondary_creation_potential": "高",
        "summary": "s",
    },
    "actionable_insights": [
        {
            "angle_title": "角度A",
            "target_audience": "青年",
            "hook": "钩子",
            "content_outline": ["a"],
            "execution_steps": ["b"],
            "monetization": "带货",
            "risk_notes": "合规",
        }
    ],
    "conclusion": "跟进。",
}


def _settings() -> Settings:
    return Settings(
        base_url="https://api.deepseek.com/v1",
        api_key="sk-test-1234567890abcd",
        model="deepseek-chat",
        temperature=0.3,
        timeout=30.0,
        max_retries=1,
        use_json_mode=True,
    )


def _completion(text: str) -> Any:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
        usage=SimpleNamespace(
            prompt_tokens=100, completion_tokens=50, total_tokens=150
        ),
    )


def test_analyze_success_fills_meta(monkeypatch: pytest.MonkeyPatch) -> None:
    analyzer = HotspotAnalyzer(_settings())
    monkeypatch.setattr(
        analyzer, "_chat", lambda messages, use_json_mode: _completion(
            json.dumps(VALID_PAYLOAD, ensure_ascii=False)
        )
    )
    report = analyzer.analyze("测试词条", "评论")
    assert report.is_valuable is True
    assert report.meta.keyword == "测试词条"
    assert report.meta.model == "deepseek-chat"
    assert report.meta.total_tokens == 150
    assert report.meta.repair_attempts == 0
    assert report.actionable_insights[0].angle_title == "角度A"


def test_analyze_handles_code_fence(monkeypatch: pytest.MonkeyPatch) -> None:
    analyzer = HotspotAnalyzer(_settings())
    fenced = "```json\n" + json.dumps(VALID_PAYLOAD, ensure_ascii=False) + "\n```"
    monkeypatch.setattr(
        analyzer, "_chat", lambda messages, use_json_mode: _completion(fenced)
    )
    report = analyzer.analyze("测试词条", "评论")
    assert report.is_valuable is True


def test_analyze_repairs_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    analyzer = HotspotAnalyzer(_settings())
    calls = {"n": 0}

    def fake_chat(messages, use_json_mode):  # noqa: ANN001
        calls["n"] += 1
        if calls["n"] == 1:
            return _completion("这不是 JSON")
        return _completion(json.dumps(VALID_PAYLOAD, ensure_ascii=False))

    monkeypatch.setattr(analyzer, "_chat", fake_chat)
    report = analyzer.analyze("测试词条", "评论")
    assert calls["n"] == 2
    assert report.meta.repair_attempts == 1


def test_analyze_raises_after_exhausting_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analyzer = HotspotAnalyzer(_settings())
    monkeypatch.setattr(
        analyzer, "_chat", lambda messages, use_json_mode: _completion("坏数据")
    )
    with pytest.raises(AnalyzerError):
        analyzer.analyze("测试词条", "评论")


def test_missing_api_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    bad = Settings(
        base_url="https://api.deepseek.com/v1",
        api_key="",
        model="deepseek-chat",
        temperature=0.3,
        timeout=30.0,
        max_retries=1,
        use_json_mode=True,
    )
    analyzer = HotspotAnalyzer(bad)
    with pytest.raises(ConfigError):
        analyzer.analyze("测试词条", "评论")


def test_empty_keyword_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    analyzer = HotspotAnalyzer(_settings())
    with pytest.raises(AnalyzerError):
        analyzer.analyze("   ", "评论")
