"""内置演示数据与 CLI 输出链路测试（离线）。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hotspot_analysis.demo_data import build_demo_report  # noqa: E402
from hotspot_analysis.renderers import render_json, render_markdown  # noqa: E402


def test_demo_report_is_valid_and_valuable() -> None:
    report = build_demo_report()
    assert report.is_valuable is True
    assert report.noise_filtering.value_score == 82
    assert len(report.actionable_insights) == 2


def test_demo_report_renders_both_formats() -> None:
    report = build_demo_report("自定义词条")
    md = render_markdown(report)
    js = render_json(report)
    assert "自定义词条" in md
    assert "自定义词条" in js
    assert "## 四、行动落地" in md
