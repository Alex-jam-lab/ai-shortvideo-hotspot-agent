"""基础测试：模型校验、JSON 提取、渲染输出。

不依赖网络与大模型，可离线运行。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# 允许直接以 `pytest` 从项目根运行
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hotspot_analysis.analyzer import _extract_json  # noqa: E402
from hotspot_analysis.models import TrendReport  # noqa: E402
from hotspot_analysis.renderers import render_json, render_markdown  # noqa: E402


def _valuable_fixture() -> dict:
    return {
        "meta": {
            "keyword": "年轻人开始流行反向消费",
            "model": "deepseek-chat",
            "base_url": "https://api.deepseek.com/v1",
            "created_at": "2026-09-23T19:46:00+08:00",
            "elapsed_seconds": 12.34,
            "prompt_tokens": 1820,
            "completion_tokens": 960,
            "total_tokens": 2780,
            "repair_attempts": 0,
        },
        "noise_filtering": {
            "is_valuable_trend": True,
            "is_noise": False,
            "noise_type": "有效话题",
            "noise_reason": "评论呈现真实共鸣与对立讨论。",
            "value_score": 82,
        },
        "emotion_decoding": {
            "status": "done",
            "pain_points": ["消费降级焦虑", "被消费主义裹挟"],
            "core_emotions": ["共鸣", "焦虑", "自嘲"],
            "collective_unconscious": ["身份认同", "抱团取暖"],
            "emotion_intensity": 78,
            "summary": "消费降级焦虑转化为清醒人设。",
        },
        "viral_mechanism": {
            "status": "done",
            "triggers": ["高共鸣情绪", "观点争议", "低成本模仿"],
            "visual_conflict": "无明显视觉冲突",
            "controversy_level": 65,
            "rarity": "中等",
            "secondary_creation_potential": "高",
            "summary": "情绪共振 + 低门槛模仿。",
        },
        "actionable_insights": [
            {
                "angle_title": "反向消费避坑清单",
                "target_audience": "18-30 岁用户",
                "hook": "这 5 样东西，我劝你别再买贵的",
                "content_outline": ["钩子", "平替实测", "判断标准"],
                "execution_steps": ["选品", "拍对比", "引导互动"],
                "monetization": "挂车低价好物",
                "risk_notes": "避免贬低他人消费选择",
            }
        ],
        "conclusion": "跟进。",
    }


def _noise_fixture() -> dict:
    return {
        "meta": {"keyword": "某地发布道路结冰黄色预警"},
        "noise_filtering": {
            "is_valuable_trend": False,
            "is_noise": True,
            "noise_type": "政务通报",
            "noise_reason": "严肃政务信息，无二次创作空间。",
            "value_score": 12,
        },
        "emotion_decoding": {"status": "skipped"},
        "viral_mechanism": {"status": "skipped"},
        "actionable_insights": [],
        "conclusion": "放弃。",
    }


def test_valuable_report_validates_and_renders() -> None:
    report = TrendReport.model_validate(_valuable_fixture())
    assert report.is_valuable is True
    assert report.noise_filtering.value_score == 82

    md = render_markdown(report)
    assert "# 抖音热点分析报告" in md
    assert "噪声过滤" in md and "情绪解构" in md
    assert "传播引爆点" in md and "行动落地" in md
    assert "反向消费避坑清单" in md


def test_noise_report_validates_and_skips_steps() -> None:
    report = TrendReport.model_validate(_noise_fixture())
    assert report.is_valuable is False
    assert report.emotion_decoding.status == "skipped"
    assert report.actionable_insights == []

    md = render_markdown(report)
    assert "噪声话题" in md
    assert "已跳过情绪解构" in md


def test_actionable_insights_capped_at_three() -> None:
    data = _valuable_fixture()
    item = data["actionable_insights"][0]
    data["actionable_insights"] = [dict(item, angle_title=f"角度{i}") for i in range(5)]
    report = TrendReport.model_validate(data)
    assert len(report.actionable_insights) == 3


def test_render_json_is_valid_json() -> None:
    report = TrendReport.model_validate(_valuable_fixture())
    payload = json.loads(render_json(report))
    assert payload["meta"]["keyword"] == "年轻人开始流行反向消费"


@pytest.mark.parametrize(
    "raw,expected",
    [
        ('{"a": 1}', '{"a": 1}'),
        ('```json\n{"a": 1}\n```', '{"a": 1}'),
        ('前言 {"a": 1} 后语', '{"a": 1}'),
        ('```\n{"a": {"b": 2}}\n```', '{"a": {"b": 2}}'),
    ],
)
def test_extract_json_variants(raw: str, expected: str) -> None:
    assert _extract_json(raw) == expected


def test_score_range_validation() -> None:
    data = _valuable_fixture()
    data["noise_filtering"]["value_score"] = 150
    with pytest.raises(Exception):
        TrendReport.model_validate(data)


# --------------------------------------------------------------------------- #
# 高阶功能：A/B 测试 Hook 矩阵 与 品牌合规风控
# --------------------------------------------------------------------------- #
def _insight_with_hooks(**kwargs):
    from hotspot_analysis.models import ActionableInsight, HookOption

    hooks = [
        HookOption(style="冲突对立型", script="贵的就一定好吗？", target_persona="价格敏感党"),
        HookOption(style="悬念好奇型", script="这 5 样东西先别买", target_persona="理性消费者"),
        HookOption(style="情绪共鸣型", script="不是买不起，是不想当冤种", target_persona="被裹挟者"),
    ]
    base = {"angle_title": "角度", "golden_hooks": hooks}
    base.update(kwargs)
    return ActionableInsight(**base)


def test_legacy_hook_str_migrates_into_golden_hooks() -> None:
    """旧字段 hook（单句 str）应自动包装为单套 golden_hooks，且 hook 属性可回读。"""
    from hotspot_analysis.models import ActionableInsight

    insight = ActionableInsight(angle_title="旧格式", hook="旧的单句钩子", target_audience="年轻人")
    assert len(insight.golden_hooks) == 1
    assert insight.golden_hooks[0].script == "旧的单句钩子"
    assert insight.hook == "旧的单句钩子"


def test_golden_hooks_style_lookup_and_property() -> None:
    insight = _insight_with_hooks()
    assert len(insight.golden_hooks) == 3
    assert insight.hook == "贵的就一定好吗？"
    assert insight.hook_by_style("悬念") == "这 5 样东西先别买"
    assert insight.hook_by_style("不存在") == ""


def test_risk_control_level_normalization_and_blocking() -> None:
    from hotspot_analysis.models import RiskControl, RiskLevel

    rc = RiskControl(risk_level="高风险", sensitive_words_found=["最"], compliance_suggestions="改写")
    assert rc.risk_level is RiskLevel.HIGH
    assert rc.is_blocking is True

    assert RiskControl(risk_level="低风险").risk_level is RiskLevel.LOW
    assert RiskControl(risk_level="Ban").risk_level is RiskLevel.BAN
    assert RiskControl().risk_level is RiskLevel.LOW
    assert RiskControl().is_blocking is False


def test_report_defaults_risk_control() -> None:
    report = TrendReport.model_validate(_valuable_fixture())
    # fixture 未显式给出 risk_control 时应回退为默认低风险
    assert report.risk_control.risk_level.value == "Low"
    assert report.risk_control.sensitive_words_found == []


def test_render_markdown_includes_hook_matrix_and_risk_section() -> None:
    data = _valuable_fixture()
    data["actionable_insights"][0].update(
        {
            "golden_hooks": [
                {"style": "冲突对立型", "script": "话术A", "target_persona": "人群A"},
                {"style": "悬念好奇型", "script": "话术B", "target_persona": "人群B"},
                {"style": "情绪共鸣型", "script": "话术C", "target_persona": "人群C"},
            ],
            "engagement_trigger": "你站哪一派？",
        }
    )
    data["risk_control"] = {
        "risk_level": "High",
        "sensitive_words_found": ["最", "第一"],
        "compliance_suggestions": "删除极限词。",
    }
    report = TrendReport.model_validate(data)
    md = render_markdown(report)

    assert "黄金 3 秒 Hook 矩阵（A/B 测试）" in md
    assert "冲突对立型" in md and "悬念好奇型" in md and "情绪共鸣型" in md
    assert "评论区互动引导" in md
    assert "品牌合规与风控评估" in md
    assert "High" in md
    assert "最、第一" in md
