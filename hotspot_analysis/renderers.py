"""渲染器：把 TrendReport 输出为结构化 JSON 或中文 Markdown 报告。"""

from __future__ import annotations

import json
from typing import Any

from hotspot_analysis.models import TrendReport


def render_json(report: TrendReport, indent: int = 2) -> str:
    """渲染为结构化 JSON 字符串。"""
    return report.model_dump_json(indent=indent)


def to_dict(report: TrendReport) -> dict[str, Any]:
    """转为可序列化字典。"""
    return json.loads(render_json(report))


def _one_line(text: str) -> str:
    """把含换行的字段压成单行，避免破坏 Markdown 引用块 / 列表结构。"""
    return " ".join(str(text).split())


def _bullet_list(items: list[str], empty: str = "（无）") -> str:
    if not items:
        return f"- {empty}"
    return "\n".join(f"- {_one_line(i)}" for i in items)


def _ordered_list(items: list[str], empty: str = "（无）") -> str:
    if not items:
        return f"1. {empty}"
    return "\n".join(f"{n}. {_one_line(i)}" for n, i in enumerate(items, start=1))


def render_markdown(report: TrendReport) -> str:
    """渲染为中文 Markdown 报告。"""
    nf = report.noise_filtering
    meta = report.meta

    lines: list[str] = []
    lines.append(f"# 抖音热点分析报告：{meta.keyword}")
    lines.append("")
    verdict = "✅ 有效话题（可跟进）" if report.is_valuable else "⛔ 噪声话题（不建议跟）"
    lines.append(f"> **结论速览**：{verdict}｜内容价值 {nf.value_score}/100")
    if report.conclusion:
        lines.append(f"> **决策建议**：{_one_line(report.conclusion)}")
    if meta.mock:
        lines.append("> ⚠️ 本报告由 Mock 模式生成，数据为离线示例，非真实分析结果。")
    lines.append("")

    # Step 1
    lines.append("## 一、噪声过滤（Noise Filtering）")
    lines.append("")
    lines.append(f"- **是否为优质话题**：{'是' if nf.is_valuable_trend else '否'}")
    lines.append(f"- **话题分类**：{nf.noise_type.value}")
    lines.append(f"- **内容价值评分**：{nf.value_score}/100")
    lines.append(f"- **判定依据**：{_one_line(nf.noise_reason)}")
    lines.append("")

    # Step 2
    em = report.emotion_decoding
    lines.append("## 二、心理与情绪解构（Emotion Decoding）")
    lines.append("")
    if em.status == "skipped":
        lines.append("_（噪声话题，已跳过情绪解构）_")
    else:
        lines.append(f"- **情绪强度**：{em.emotion_intensity}/100")
        lines.append(f"- **核心情绪**：{'、'.join(em.core_emotions) or '（无）'}")
        lines.append("")
        lines.append("**戳中的痛点：**")
        lines.append(_bullet_list(em.pain_points))
        lines.append("")
        lines.append("**集体无意识 / 群体心理：**")
        lines.append(_bullet_list(em.collective_unconscious))
        if em.summary:
            lines.append("")
            lines.append(f"**小结**：{_one_line(em.summary)}")
    lines.append("")

    # Step 3
    vm = report.viral_mechanism
    lines.append("## 三、传播引爆点（Viral Mechanism）")
    lines.append("")
    if vm.status == "skipped":
        lines.append("_（噪声话题，已跳过传播机制分析）_")
    else:
        lines.append(f"- **争议指数**：{vm.controversy_level}/100")
        lines.append(f"- **强视觉冲突**：{_one_line(vm.visual_conflict) or '（无明显视觉冲突）'}")
        lines.append(f"- **信息稀缺度**：{_one_line(vm.rarity) or '（无）'}")
        lines.append(
            f"- **二次创作潜力**：{_one_line(vm.secondary_creation_potential) or '（无）'}"
        )
        lines.append("")
        lines.append("**引爆因子：**")
        lines.append(_bullet_list(vm.triggers))
        if vm.summary:
            lines.append("")
            lines.append(f"**小结**：{_one_line(vm.summary)}")
    lines.append("")

    # Step 4
    lines.append("## 四、行动落地（Actionable Insights）")
    lines.append("")
    if not report.actionable_insights:
        lines.append("_（噪声话题，无可执行切入角度）_")
        lines.append("")
    else:
        for idx, ins in enumerate(report.actionable_insights, start=1):
            lines.append(f"### 角度 {idx}：{_one_line(ins.angle_title)}")
            lines.append("")
            lines.append(f"- **目标人群**：{_one_line(ins.target_audience) or '（未指定）'}")
            lines.append(f"- **前 3 秒钩子**：{_one_line(ins.hook) or '（未指定）'}")
            lines.append(f"- **变现 / 引流路径**：{_one_line(ins.monetization) or '（未指定）'}")
            lines.append(f"- **风险提示**：{_one_line(ins.risk_notes) or '（无）'}")
            lines.append("")
            lines.append("**内容分镜提纲：**")
            lines.append(_ordered_list(ins.content_outline))
            lines.append("")
            lines.append("**执行步骤：**")
            lines.append(_ordered_list(ins.execution_steps))
            lines.append("")

    # Meta
    lines.append("---")
    lines.append("")
    lines.append("## 元信息")
    lines.append("")
    if meta.mock:
        lines.append("- 模式：**Mock（离线，未调用真实模型）**")
    lines.append(f"- 模型：`{meta.model}`")
    lines.append(f"- 接口：`{meta.base_url}`")
    lines.append(f"- 生成时间：{meta.created_at}")
    lines.append(f"- 端到端耗时：{meta.elapsed_seconds}s（API 延迟 {meta.latency_ms}ms）")
    lines.append(
        f"- Token：prompt={meta.prompt_tokens}, "
        f"completion={meta.completion_tokens}, total={meta.total_tokens}"
    )
    lines.append(f"- 预估成本：${meta.total_cost_usd:.6f}")
    lines.append(
        f"- 输入预处理：{meta.raw_text_chars} 字符"
        f"{'（已截断）' if meta.raw_text_truncated else ''}"
        f"，去重 {meta.deduped_lines} 条"
    )
    lines.append(f"- JSON 修复重试：{meta.repair_attempts} 次")
    lines.append("")

    return "\n".join(lines)


def render(report: TrendReport, fmt: str = "md") -> str:
    """统一渲染入口。fmt: json | md。"""
    fmt = fmt.lower()
    if fmt in {"json"}:
        return render_json(report)
    if fmt in {"md", "markdown"}:
        return render_markdown(report)
    raise ValueError(f"不支持的输出格式: {fmt}（可选 json / md）")
