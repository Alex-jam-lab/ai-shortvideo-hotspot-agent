"""成本估算、Mock 模式与日志测试（离线）。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hotspot_analysis.analyzer import HotspotAnalyzer  # noqa: E402
from hotspot_analysis.config import (  # noqa: E402
    Settings,
    load_settings,
    resolve_price,
)
from hotspot_analysis.logging_config import setup_logging  # noqa: E402
from hotspot_analysis.prompts import build_fewshot_messages  # noqa: E402


def _settings(**overrides) -> Settings:
    base = dict(
        base_url="https://api.deepseek.com/v1",
        api_key="sk-test-1234567890abcd",
        model="deepseek-flash",
        temperature=0.3,
        timeout=30.0,
        max_retries=1,
        use_json_mode=True,
        mock_mode=True,
        mock_file=str(ROOT / "examples" / "sample_output.json"),
        max_raw_text_chars=3000,
        log_level="WARNING",
        log_dir=str(ROOT / "logs"),
        price_input_per_1m=0.10,
        price_output_per_1m=0.30,
    )
    base.update(overrides)
    return Settings(**base)


def test_estimate_cost() -> None:
    s = _settings()
    # 1M 输入 + 1M 输出 = 0.10 + 0.30
    assert s.estimate_cost(1_000_000, 1_000_000) == pytest.approx(0.40)
    # 1000 / 500 tokens
    cost = s.estimate_cost(1000, 500)
    assert cost == pytest.approx(0.10 * 1000 / 1e6 + 0.30 * 500 / 1e6)


def test_resolve_price_known_and_prefix() -> None:
    assert resolve_price("deepseek-flash") == (0.10, 0.30)
    assert resolve_price("gpt-4o-mini") == (0.15, 0.60)
    # 前缀匹配
    assert resolve_price("deepseek-chat-0324") == (0.27, 1.10)
    # 未知模型
    assert resolve_price("unknown-model") == (0.0, 0.0)


def test_load_settings_reads_new_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOCK_MODE", "true")
    monkeypatch.setenv("MAX_RAW_TEXT_CHARS", "1234")
    monkeypatch.setenv("LOG_LEVEL", "debug")
    monkeypatch.setenv("OPENAI_MODEL", "deepseek-flash")
    s = load_settings()
    assert s.mock_mode is True
    assert s.max_raw_text_chars == 1234
    assert s.log_level == "DEBUG"
    # 单价应从内置表自动解析
    assert s.price_input_per_1m == 0.10
    assert s.price_output_per_1m == 0.30


def test_mock_mode_returns_report_without_api() -> None:
    analyzer = HotspotAnalyzer(_settings(mock_mode=True))
    report = analyzer.analyze("测试词条", "评论A\n评论A\n评论B")
    assert report.meta.mock is True
    assert report.meta.keyword == "测试词条"
    assert report.meta.deduped_lines == 1
    assert report.is_valuable is True


def test_mock_mode_missing_file_raises() -> None:
    analyzer = HotspotAnalyzer(_settings(mock_file=str(ROOT / "not_exist.json")))
    with pytest.raises(Exception):
        analyzer.analyze("测试词条", "评论")


def test_fewshot_messages_structure() -> None:
    msgs = build_fewshot_messages()
    assert len(msgs) == 4
    assert [m["role"] for m in msgs] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    # assistant 内容必须是合法 JSON
    for m in msgs:
        if m["role"] == "assistant":
            json.loads(m["content"])


def test_logging_setup_creates_file(tmp_path: Path) -> None:
    # 使用独立目录避免与其他测试共享状态（_CONFIGURED 为模块级）
    import logging

    import hotspot_analysis.logging_config as lc

    lc._CONFIGURED = False
    root = logging.getLogger("hotspot_analysis")
    for h in list(root.handlers):
        root.removeHandler(h)

    # 先显式初始化到临时目录，再获取子级 logger
    setup_logging(level="INFO", log_dir=str(tmp_path))
    logger = lc.get_logger("hotspot_analysis.test")
    lc.log_event(logger, "测试事件", event="unit_test", value=1)
    for handler in root.handlers:
        handler.flush()

    log_file = tmp_path / "hotspot_analysis.log"
    assert log_file.exists()
    content = log_file.read_text(encoding="utf-8")
    assert "unit_test" in content
