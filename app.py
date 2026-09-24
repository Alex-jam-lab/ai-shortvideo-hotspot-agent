"""Streamlit 前端：抖音热点深度分析（产品化界面）。

三种交互：
1. **手动动态分析**：预设爆款案例下拉（一键填充）或自由输入词条 + 粘贴评论。
2. **实时热榜抓取**：抓取抖音热榜 → 下拉选择 → 自动抓评论 / 源视频并分析。
3. **视觉化看板**：封面卡片墙 + 4 张彩色指标卡；Token / 耗时 / 成本下沉到折叠面板。

复用后端：HotspotAnalyzer、renderers、fetcher —— 本文件只做 UI 编排。

启动：
    pip install -r requirements-ui.txt
    streamlit run app.py
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from html import escape as _html_escape

import streamlit as st

from hotspot_analysis.analyzer import AnalyzerError, HotspotAnalyzer
from hotspot_analysis.config import (
    KNOWN_PRICES,
    ConfigError,
    Settings,
    load_settings,
    resolve_price,
)
from hotspot_analysis.fetcher import (
    FetchError,
    VideoItem,
    douyin_search_url,
    get_source,
)
from hotspot_analysis.models import (
    HookOption,
    RiskControl,
    RiskLevel,
    TrendReport,
)
from hotspot_analysis.renderers import render_json, render_markdown

CUSTOM_MODEL = "自定义…"
MANUAL_PRESET = "（不选择，手动输入）"

# --------------------------------------------------------------------------- #
# 预设爆款案例：一键填充输入框，方便快速体验
# --------------------------------------------------------------------------- #
PRESETS: dict[str, dict[str, str] | None] = {
    MANUAL_PRESET: None,
    "🔁 反向消费 · 消费降级自嘲": {
        "keyword": "年轻人开始流行反向消费",
        "raw_text": (
            "不是不想买，是真买不起\n"
            "以前买东西看牌子，现在只看有没有券\n"
            "连反向消费我都要分期了\n"
            "省钱的尽头是穷，穷的尽头是清醒\n"
            "我妈说我抠，我说我在清醒\n"
            "不是消费降级，是终于不被消费主义骗了\n"
            "买之前先问自己：不买会死吗\n"
            "别人晒包我晒记账本"
        ),
    },
    "🧊 情绪价值 · 一个人也要好好过": {
        "keyword": "一个人也要好好过",
        "raw_text": (
            "一个人吃饭也要摆盘，这是我的仪式感\n"
            "独居第三年，我学会了给自己过生日\n"
            "不是孤僻，是不想再委屈自己\n"
            "给自己买花，比等别人送更靠谱\n"
            "独处不是孤独，是终于不用演了\n"
            "一个人住的房间，是我唯一能做主的地方\n"
        ),
    },
    "💼 职场整顿 · 拒绝无效加班": {
        "keyword": "00后整顿职场拒绝无效加班",
        "raw_text": (
            "下班时间到了，我准时关电脑有什么问题\n"
            "加班可以，加班费呢\n"
            "领导画饼我不吃了，我只认合同\n"
            "不是我们难管，是以前太惯着了\n"
            "下班后的消息，第二天上班再回\n"
            "整顿职场的代价是被优化，但我不后悔\n"
        ),
    },
}


# --------------------------------------------------------------------------- #
# 全局样式注入（科技感卡片 / 暗色边界 / 按钮动效）
# --------------------------------------------------------------------------- #
GLOBAL_CSS = """
<style>
/* ---------- 布局与留白 ---------- */
.block-container { padding-top: 2.2rem; padding-bottom: 4rem; max-width: 1180px; }

/* ---------- 标题层级与间距 ---------- */
h1 {
    font-size: 2.05rem !important;
    font-weight: 800 !important;
    letter-spacing: -0.02em !important;
    margin-bottom: 0.25rem !important;
    background: linear-gradient(120deg, #3b82f6 0%, #8b5cf6 55%, #ec4899 100%);
    -webkit-background-clip: text;
    background-clip: text;
    -webkit-text-fill-color: transparent;
}
h2 { font-size: 1.45rem !important; margin-top: 1.5rem !important; }
h3 { font-size: 1.18rem !important; margin-top: 1.15rem !important; }
h5 { letter-spacing: 0.01em; margin-top: 0.4rem !important; }

/* ---------- 卡片包裹感（st.container(border=True)） ---------- */
div[data-testid="stVerticalBlockBorderWrapper"] {
    border-radius: 14px !important;
    border: 1px solid rgba(148, 163, 184, 0.28) !important;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.06);
    background: rgba(148, 163, 184, 0.04);
    transition: box-shadow .2s ease, border-color .2s ease, transform .2s ease;
}
div[data-testid="stVerticalBlockBorderWrapper"]:hover {
    border-color: rgba(59, 130, 246, 0.45) !important;
    box-shadow: 0 8px 24px rgba(59, 130, 246, 0.14);
}

/* ---------- Tab 胶囊化 ---------- */
button[data-baseweb="tab"] { border-radius: 10px 10px 0 0; }

/* ---------- 按钮 / 下载 / 链接：hover 渐变 + 微阴影 ---------- */
.stButton > button,
.stDownloadButton > button,
.stLinkButton > a {
    border-radius: 10px !important;
    font-weight: 600 !important;
    transition: all .18s ease !important;
}
.stButton > button:hover,
.stDownloadButton > button:hover,
.stLinkButton > a:hover {
    background-image: linear-gradient(135deg, #6366f1 0%, #3b82f6 60%, #0ea5e9 100%) !important;
    color: #ffffff !important;
    border-color: transparent !important;
    box-shadow: 0 8px 20px rgba(59, 130, 246, 0.38) !important;
    transform: translateY(-1px);
}
.stButton > button[kind="primary"] {
    background-image: linear-gradient(135deg, #3b82f6 0%, #8b5cf6 100%) !important;
    border: none !important;
}
.stButton > button[kind="primary"]:hover {
    background-image: linear-gradient(135deg, #4f46e5 0%, #a855f7 100%) !important;
    box-shadow: 0 10px 24px rgba(139, 92, 246, 0.45) !important;
}

/* ---------- 指标与折叠面板 ---------- */
div[data-testid="stMetric"] {
    border-radius: 12px;
    padding: 10px 12px;
    background: rgba(148, 163, 184, 0.06);
}
div[data-testid="stExpander"] {
    border-radius: 12px !important;
    border: 1px solid rgba(148, 163, 184, 0.25) !important;
}

/* ---------- 暗色主题：精致的卡片边界感 ---------- */
@media (prefers-color-scheme: dark) {
    div[data-testid="stVerticalBlockBorderWrapper"] {
        border-color: rgba(148, 163, 184, 0.30) !important;
        background: rgba(30, 41, 59, 0.45);
        box-shadow: 0 1px 2px rgba(0, 0, 0, 0.45);
    }
    div[data-testid="stVerticalBlockBorderWrapper"]:hover {
        border-color: rgba(96, 165, 250, 0.55) !important;
        box-shadow: 0 10px 26px rgba(37, 99, 235, 0.28);
    }
    div[data-testid="stMetric"] { background: rgba(51, 65, 85, 0.45); }
    div[data-testid="stExpander"] { border-color: rgba(148, 163, 184, 0.3) !important; }
}

/* Streamlit 主题属性兜底 */
[data-theme="dark"] div[data-testid="stVerticalBlockBorderWrapper"] {
    border-color: rgba(148, 163, 184, 0.30) !important;
    background: rgba(30, 41, 59, 0.45);
}
</style>
"""


def inject_global_css() -> None:
    """注入全局自定义 CSS：卡片包裹感 / 按钮渐变动效 / 标题层级 / 暗色边界。"""
    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)


def _playwright_ready() -> bool:
    """探测 Playwright 是否可用（用于顶部环境状态标签）。"""
    try:
        import importlib.util

        return importlib.util.find_spec("playwright") is not None
    except Exception:  # noqa: BLE001 - 环境探测失败不应影响页面渲染
        return False


def render_env_status(has_api_key: bool) -> None:
    """顶部全局环境状态指示标签。"""
    pw = _playwright_ready()
    pw_text = (
        "支持 Playwright 实时采掘 + Top 爆款对标 ✅"
        if pw
        else "Playwright 未安装 ⚠️（实时热榜采集不可用）"
    )
    key_text = "API Key 已配置 ✅" if has_api_key else "API Key 未配置 ⚠️（Mock 模式可体验）"
    st.caption(f"🟢 系统环境已就绪 ｜ {pw_text} ｜ {key_text}")


# --------------------------------------------------------------------------- #
# 分析结果封装
# --------------------------------------------------------------------------- #
@dataclass
class AnalysisResult:
    """一次分析的完整产物：报告 + 源视频（可选）+ 来源信息。"""

    report: TrendReport
    videos: list[VideoItem] = field(default_factory=list)
    source_url: str = ""
    source_label: str = "manual"


# --------------------------------------------------------------------------- #
# 工具函数
# --------------------------------------------------------------------------- #
def _safe_filename(keyword: str) -> str:
    invalid = '<>:"/\\|?*'
    name = "".join("_" if c in invalid else c for c in keyword).strip()
    return (name or "report")[:60]


def _has_api_key(settings: Settings) -> bool:
    return bool(settings.api_key) and not settings.api_key.startswith("sk-your")


def _score_color(score: int) -> str:
    """通用分数配色：越高越绿。"""
    if score >= 70:
        return "#16a34a"
    if score >= 40:
        return "#f59e0b"
    return "#dc2626"


def _heat_color(level: int) -> str:
    """争议 / 热度配色：越高越红。"""
    if level >= 70:
        return "#dc2626"
    if level >= 40:
        return "#f97316"
    return "#0ea5e9"


def _kpi_card(
    label: str, value: str, sub: str, color: str, *, pct: int | None = None
) -> str:
    """生成一张彩色高亮指标卡的 HTML。"""
    bar = ""
    if pct is not None:
        width = max(0, min(100, int(pct)))
        bar = (
            '<div style="height:6px;background:#e5e7eb;border-radius:4px;margin-top:10px;">'
            f'<div style="width:{width}%;height:6px;background:{color};border-radius:4px;"></div>'
            "</div>"
        )
    return (
        '<div style="background:#ffffff;border:1px solid #e5e7eb;'
        f"border-left:6px solid {color};border-radius:10px;padding:14px 16px;"
        'box-shadow:0 1px 3px rgba(0,0,0,0.06);min-height:120px;">'
        f'<div style="font-size:13px;color:#6b7280;">{label}</div>'
        f'<div style="font-size:22px;font-weight:700;color:{color};'
        f'line-height:1.3;margin-top:6px;word-break:break-word;">{value}</div>'
        f'<div style="font-size:12px;color:#9ca3af;margin-top:6px;">{sub}</div>{bar}'
        "</div>"
    )


def _follow_metric(report: TrendReport) -> tuple[str, str, str, int]:
    """由报告推导「跟风推荐度」：(文案, 说明, 颜色, 进度)。"""
    if not report.is_valuable:
        return "不建议跟", "噪声话题，避开为妙", "#dc2626", 12
    score = report.noise_filtering.value_score
    if score >= 85:
        return "强烈推荐", "高价值 + 易复制，建议尽快切入", "#16a34a", score
    if score >= 70:
        return "推荐跟进", "把握情绪窗口期", "#22c55e", score
    return "谨慎尝试", "价值中等，需差异化切入", "#f59e0b", score


def _risk_style(level: RiskLevel) -> tuple[str, str]:
    """风险等级 → (主色, 中文标签)。绿 / 黄 / 红 / 深红。"""
    mapping = {
        RiskLevel.LOW: ("#16a34a", "低风险 · 可放心发布"),
        RiskLevel.MEDIUM: ("#f59e0b", "中风险 · 建议改写"),
        RiskLevel.HIGH: ("#dc2626", "高风险 · 需整改"),
        RiskLevel.BAN: ("#7f1d1d", "封禁级 · 禁止发布"),
    }
    return mapping.get(level, ("#6b7280", str(level)))


def render_risk_assessment(report: TrendReport) -> None:
    """「🛡️ 品牌合规与风控评估」卡片：按风险等级绿 / 黄 / 红高亮。"""
    rc: RiskControl = report.risk_control
    color, label = _risk_style(rc.risk_level)
    words = "、".join(_html_escape(w) for w in rc.sensitive_words_found) or "未命中敏感词 ✅"
    suggestion = _html_escape(rc.compliance_suggestions) or "（暂无合规建议）"

    st.markdown("#### 🛡️ 品牌合规与风控评估")
    st.markdown(
        '<div style="border-left:6px solid %s;background:rgba(148,163,184,0.06);'
        'border-radius:12px;padding:14px 18px;">'
        '<div style="font-size:15px;font-weight:700;color:%s;">%s</div>'
        '<div style="margin-top:8px;font-size:13px;color:#6b7280;">命中敏感词 / 极限词</div>'
        '<div style="font-size:14px;font-weight:600;color:#111827;word-break:break-word;">%s</div>'
        '<div style="margin-top:10px;font-size:13px;color:#6b7280;">合规替换建议</div>'
        '<div style="font-size:14px;color:#374151;line-height:1.6;">%s</div>'
        "</div>" % (color, color, label, words, suggestion),
        unsafe_allow_html=True,
    )
    if rc.is_blocking:
        st.error("⚠️ 该话题命中高风险表述，请先按上述建议整改后再发布。")


def render_hook_matrix(insight, *, key_prefix: str, index: int) -> None:
    """「A/B 测试 Hook 矩阵」：st.columns(3) 并排展示 3 套 Hook + 一键复制。"""
    if not insight.golden_hooks:
        st.info("（模型未给出 Hook 方案）")
        return

    st.markdown("**🧪 A/B 测试 Hook 矩阵（3 套风格）**")
    hooks: list[HookOption] = insight.golden_hooks
    cols = st.columns(len(hooks))
    for pos, hook in enumerate(hooks):
        with cols[pos]:
            with st.container(border=True):
                st.markdown(f"**{hook.style}**")
                st.caption(f"👤 主打人群：{hook.target_persona or '—'}")
                st.info(hook.script or "（空）")
                st.code(hook.script or "", language=None)
                st.caption("⬆️ 终端图标一键复制脚本话术")


def render_pitfall_warnings(report: TrendReport) -> None:
    """「⚠️ 舆情雷区与避坑预警」卡片：高亮评论区负面声音与禁止触碰的雷区。"""
    em = report.emotion_decoding
    if em.status == "skipped" or not (em.top_controversies or em.pitfall_warnings):
        return

    st.markdown("#### ⚠️ 舆情雷区与避坑预警")
    left, right = st.columns(2)
    with left:
        st.markdown("**🗣️ 评论区核心争议 / 负面声音**")
        if em.top_controversies:
            for item in em.top_controversies:
                st.markdown(
                    '<div style="border-left:4px solid #ef4444;background:rgba(239,68,68,0.08);'
                    'border-radius:8px;padding:8px 12px;margin-bottom:6px;font-size:14px;'
                    'color:#b91c1c;">%s</div>' % _html_escape(item),
                    unsafe_allow_html=True,
                )
        else:
            st.caption("（未捕捉到明显负面声音）")
    with right:
        st.markdown("**🚫 拍摄避坑雷区（禁止触碰）**")
        if em.pitfall_warnings:
            for item in em.pitfall_warnings:
                st.markdown(
                    '<div style="border-left:4px solid #f59e0b;background:rgba(245,158,11,0.08);'
                    'border-radius:8px;padding:8px 12px;margin-bottom:6px;font-size:14px;'
                    'color:#b45309;">%s</div>' % _html_escape(item),
                    unsafe_allow_html=True,
                )
        else:
            st.caption("（暂无避坑提示）")


def render_angle_comparison(insight, *, index: int) -> None:
    """「💡 差异化/反常识切入视角」对比卡片：同质化角度 vs 蓝海切入提案。"""
    if not (insight.mainstream_angles or insight.differentiated_angle):
        return

    st.markdown("**💡 差异化 / 反常识切入视角**")
    col_a, col_b = st.columns(2)
    with col_a:
        with st.container(border=True):
            st.markdown("**🟥 同质化常规角度（红海）**")
            if insight.mainstream_angles:
                for item in insight.mainstream_angles:
                    st.markdown(f"- {item}")
            else:
                st.caption("（未识别到明显同质化角度）")
    with col_b:
        with st.container(border=True):
            st.markdown("**🟦 蓝海 / 反常识切入提案**")
            if insight.differentiated_angle:
                st.success(insight.differentiated_angle)
            else:
                st.caption("（模型未给出差异化视角）")


def _cell(text: str) -> str:
    """转义 Markdown 表格单元格中的竖线。"""
    return " ".join(str(text).split()).replace("|", "\\|")


def _storyboard_table(items: list[str]) -> str:
    """把「内容分镜提纲」渲染为专业 Markdown 表格。"""
    if not items:
        return "_（模型未给出分镜提纲）_"
    lines = ["| 序号 | 画面 / 步骤 | 核心台词 / Hook |", "| :--: | --- | --- |"]
    for idx, raw in enumerate(items, start=1):
        text = _cell(raw)
        for sep in ("：", ":"):
            if sep in text:
                head, tail = text.split(sep, 1)
                break
        else:
            head, tail = text, "—"
        lines.append(f"| {idx} | {head} | {tail} |")
    return "\n".join(lines)


def _steps_table(items: list[str]) -> str:
    """把「可执行步骤」渲染为 Markdown 表格。"""
    if not items:
        return "_（模型未给出执行步骤）_"
    lines = ["| 步骤 | 操作说明 |", "| :--: | --- |"]
    for idx, raw in enumerate(items, start=1):
        lines.append(f"| {idx} | {_cell(raw)} |")
    return "\n".join(lines)


def _build_storyboard_markdown(report: TrendReport) -> str:
    """把「决策建议 + 黄金 3 秒 Hook + 分镜表格」导出为标准 Markdown 拍摄脚本。

    输出可直接交给编导 / 摄影团队落地的脚本文档，包含：
    一句话决策建议、逐角度的 3 秒 Hook、内容分镜表格、执行步骤、变现与合规。
    """
    meta = report.meta
    lines = [
        f"# 🎬 短视频拍摄脚本：{meta.keyword}",
        "",
        f"> 生成时间：{meta.created_at or '—'} ｜ 模型：`{meta.model or '—'}`",
        "",
        "## 🎯 决策建议",
        "",
        _cell(report.conclusion) if report.conclusion else "_（模型未给出决策建议）_",
        "",
    ]

    if not report.actionable_insights:
        lines += ["## 🎞️ 分镜剧本", "", "_（本次报告未产出可执行切入点，可能为噪声话题）_", ""]
        return "\n".join(lines).rstrip() + "\n"

    rc = report.risk_control
    lines += [
        "## 🛡️ 品牌合规与风控评估",
        "",
        f"- **风险等级**：{rc.risk_level.value}",
        f"- **命中敏感词**：{'、'.join(rc.sensitive_words_found) or '（未命中）'}",
        f"- **合规建议**：{_cell(rc.compliance_suggestions) or '（无）'}",
        "",
    ]

    for idx, insight in enumerate(report.actionable_insights, start=1):
        lines += [f"## 角度 {idx}：{insight.angle_title}", ""]
        if insight.target_audience:
            lines += [f"**🎯 目标人群**：{_cell(insight.target_audience)}", ""]
        lines += [
            "**🧪 A/B 测试 Hook 矩阵（3 套风格）**",
            "",
        ]
        if insight.golden_hooks:
            lines += ["| 风格 | 钩子话术 | 主打人群 |", "| --- | --- | --- |"]
            for hook in insight.golden_hooks:
                lines.append(
                    f"| {_cell(hook.style)} | {_cell(hook.script)} "
                    f"| {_cell(hook.target_persona) or '—'} |"
                )
            lines.append("")
        else:
            lines += ["_（模型未给出 Hook 方案）_", ""]
        lines += [
            "**🎞️ 内容分镜提纲**",
            "",
            _storyboard_table(insight.content_outline),
            "",
            "**✅ 执行步骤**",
            "",
            _steps_table(insight.execution_steps),
            "",
        ]
        if insight.engagement_trigger:
            lines += [
                "**💬 评论区互动引导点**",
                "",
                f"> {_cell(insight.engagement_trigger)}",
                "",
            ]
        lines += [
            "| 维度 | 说明 |",
            "| --- | --- |",
            f"| 💰 变现 / 引流 | {_cell(insight.monetization or '（未给出）')} |",
            f"| ⚠️ 合规风险 | {_cell(insight.risk_notes or '（未给出）')} |",
            "",
        ]
    return "\n".join(lines).rstrip() + "\n"


def _shot_size(text: str) -> str:
    """依据分镜内容推断景别（用于 CSV 分镜表）。"""
    rules = (
        ("钩子", "近景"),
        ("开场", "近景"),
        ("特写", "特写"),
        ("细节", "特写"),
        ("对比", "特写"),
        ("价格", "特写"),
        ("展示", "中景"),
        ("实测", "中景"),
        ("引导", "全景"),
        ("总结", "近景"),
    )
    for keyword, size in rules:
        if keyword in text:
            return size
    return "中景"


def _shot_sfx(text: str) -> str:
    """依据分镜内容给出一条音效 / BGM 建议。"""
    if any(k in text for k in ("钩子", "开场")):
        return "重音鼓点 / 卡点 BGM 起"
    if any(k in text for k in ("对比", "价格", "特写")):
        return "叮·价格反差音效"
    if any(k in text for k in ("引导", "总结")):
        return "BGM 渐弱 + 提示音"
    return "轻快 BGM 铺底"


def _build_storyboard_csv(report: TrendReport) -> str:
    """把分镜提纲导出为 CSV（镜号 / 景别 / 台词 / 音效 / 互动点），便于导入 Excel / 飞书。"""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["角度", "镜号", "景别", "台词", "音效", "互动点"])

    for angle_idx, insight in enumerate(report.actionable_insights, start=1):
        outline = insight.content_outline or ["（未给出分镜提纲）"]
        last = len(outline)
        for shot_idx, raw in enumerate(outline, start=1):
            text = " ".join(str(raw).split())
            for sep in ("：", ":"):
                if sep in text:
                    _head, tail = text.split(sep, 1)
                    break
            else:
                tail = text
            interaction = insight.engagement_trigger if shot_idx == last else ""
            writer.writerow(
                [
                    f"角度{angle_idx}：{insight.angle_title}",
                    shot_idx,
                    _shot_size(text),
                    tail,
                    _shot_sfx(text),
                    interaction,
                ]
            )

    return buffer.getvalue()


def _storyboard_download(report: TrendReport, *, key_prefix: str) -> None:
    """「🎬 拍摄分镜剧本」Tab 底部的一键导出按钮（Markdown + CSV）。"""
    st.download_button(
        "⬇️ 下载短视频拍摄脚本（Markdown）",
        data=_build_storyboard_markdown(report),
        file_name=f"{_safe_filename(report.meta.keyword)}_短视频拍摄脚本.md",
        mime="text/markdown",
        help="导出「决策建议 + 黄金 3 秒 Hook + 分镜表格」为标准 Markdown 脚本文档。",
        key=f"{key_prefix}_dl_story",
    )
    st.download_button(
        "📊 下载分镜表格（CSV，可直接导入 Excel / 飞书）",
        data=_build_storyboard_csv(report),
        file_name=f"{_safe_filename(report.meta.keyword)}_分镜表.csv",
        mime="text/csv",
        help="列：角度 / 镜号 / 景别 / 台词 / 音效 / 互动点，UTF-8 编码，可直接导入 Excel 或飞书多维表格。",
        key=f"{key_prefix}_dl_csv",
    )


# --------------------------------------------------------------------------- #
# 侧边栏
# --------------------------------------------------------------------------- #
def build_sidebar(base: Settings) -> Settings:
    """侧边栏：顶部仅保留核心项（模型 / Mock / Key 状态），开发者参数收纳折叠。"""
    st.sidebar.header("⚙️ 运行配置")

    # —— 顶部：仅保留三大核心项，保持清爽 ——
    mock = st.sidebar.toggle(
        "🧪 Mock 模式（离线零成本）",
        value=base.mock_mode,
        help="勾选后不调用真实模型，直接读取 examples/sample_output.json，适合 UI 联调。",
    )

    presets = list(KNOWN_PRICES.keys())
    options = presets + [CUSTOM_MODEL]
    default_model = base.model or presets[0]
    try:
        default_index = options.index(default_model)
    except ValueError:
        default_index = len(options) - 1
    choice = st.sidebar.selectbox("🤖 模型", options, index=default_index)
    if choice == CUSTOM_MODEL:
        model = st.sidebar.text_input("自定义模型名", value=default_model)
    else:
        model = choice

    # 有效 Key：优先使用界面覆盖值（session_state），否则回退到虚拟环境 / .env
    effective_key = (st.session_state.get("api_key_input") or base.api_key or "").strip()
    api_ok = bool(effective_key) and not effective_key.startswith("sk-your")
    (st.sidebar.success if api_ok else st.sidebar.warning)(
        "🔑 API Key：已配置 ✅" if api_ok else "🔑 API Key：未配置 ⚠️（可在高级配置填写或开启 Mock）"
    )

    price_in, price_out = resolve_price(model)
    if price_in or price_out:
        st.sidebar.caption(f"💸 单价估算：输入 ${price_in}/M ｜ 输出 ${price_out}/M")
    else:
        st.sidebar.caption("💸 该模型未收录单价，成本展示为 $0（可在 .env 配置）")

    # —— 折叠区：开发者 / 调试参数统一收纳 ——
    with st.sidebar.expander("⚙️ 高级调试配置", expanded=False):
        api_key = st.text_input(
            "🔑 API Key（可修改）",
            value=base.api_key,
            type="password",
            key="api_key_input",
            placeholder="sk-...（留空则读取虚拟环境 / .env）",
            help="默认读取虚拟环境 / .env 的 OPENAI_API_KEY；此处填写将仅在本会话内临时覆盖。",
        )
        entered_key = (api_key or "").strip()
        if not api_ok and not entered_key:
            st.caption("⚠️ 未检测到可用 API Key，请在此填写后重试（或开启 Mock 模式）。")
        elif entered_key and entered_key != (base.api_key or "").strip():
            st.caption("✅ 已使用界面填写的 API Key（临时覆盖环境变量）。")
        else:
            st.caption("✅ 正在使用虚拟环境 / .env 中的 API Key。")

        base_url = st.text_input("接口地址（Base URL）", value=base.base_url)
        temperature = st.slider(
            "采样温度", 0.0, 1.0, float(base.temperature), 0.05,
            help="分析类任务建议 0.2-0.5。",
        )
        max_chars = st.number_input(
            "raw_text 最大字符数", min_value=500, max_value=20000,
            value=int(base.max_raw_text_chars), step=500,
        )
        max_retries = st.number_input(
            "JSON 修复重试次数", min_value=0, max_value=5, value=int(base.max_retries)
        )

    from dataclasses import replace

    return replace(
        base,
        mock_mode=mock,
        model=model,
        api_key=entered_key or base.api_key,
        base_url=base_url,
        temperature=float(temperature),
        max_raw_text_chars=int(max_chars),
        max_retries=int(max_retries),
        price_input_per_1m=price_in,
        price_output_per_1m=price_out,
    )


# --------------------------------------------------------------------------- #
# 分析执行
# --------------------------------------------------------------------------- #
def run_analysis(
    keyword: str,
    raw_text: str,
    settings: Settings,
    *,
    store_key: str,
    videos: list[VideoItem] | None = None,
    source_url: str = "",
    source_label: str = "manual",
) -> AnalysisResult | None:
    """调用后端分析器并把结果（含源视频）写入 session_state。"""
    if not keyword.strip():
        st.warning("请先填写热点词条。")
        return None

    if not settings.mock_mode and not _has_api_key(settings):
        st.error("未配置 API Key，无法真实调用。请勾选「Mock 模式」或配置 .env。")
        return None

    try:
        analyzer = HotspotAnalyzer(settings)
        with st.spinner("正在调用大模型进行四步分析…"):
            report = analyzer.analyze(keyword, raw_text)
    except (AnalyzerError, ConfigError) as exc:
        st.error(f"分析失败：{exc}")
        return None

    result = AnalysisResult(
        report=report,
        videos=list(videos or []),
        source_url=source_url,
        source_label=source_label,
    )
    st.session_state[store_key] = result
    return result


# --------------------------------------------------------------------------- #
# 报告渲染
# --------------------------------------------------------------------------- #
def _pick_source_videos(result: AnalysisResult, limit: int = 3) -> list[VideoItem]:
    """挑选头部爆款视频（``/video/`` 形态），按点赞量降序取 Top N。

    跳过「搜索页兜底链接」（非 ``/video/`` 形态），它们由区块底部按钮承担。
    """
    videos = [v for v in result.videos if v.video_url and "/video/" in v.video_url]
    return sorted(videos, key=lambda v: v.like_count, reverse=True)[:limit]


def _cover_placeholder(text: str) -> str:
    """封面缺失 / 加载失败时的占位块 HTML。"""
    return (
        '<div style="height:160px;background:#f1f5f9;border-radius:8px;'
        'display:flex;align-items:center;justify-content:center;'
        f'color:#94a3b8;">{text}</div>'
    )


def _like_badge(video: VideoItem, *, is_top: bool) -> str:
    """点赞高亮标签：Top1 标注「最高热度」，其余展示点赞量。"""
    if is_top:
        return f"🔥 点赞量最高 ｜ ❤️ {video.like_text}"
    return f"❤️ 点赞 {video.like_text}"


def render_video_wall(result: AnalysisResult, *, key_prefix: str) -> None:
    """【🔥 该热点最高热度/点赞爆款对标】区块。

    - 抓到头部视频（``/video/`` 形态）：展示 Top1~Top3 卡片，含封面 / 作者 /
      点赞数高亮，Top1 额外标注「🔥 点赞量最高」；
    - 无论是否抓到：**始终**渲染「最多点赞」搜索页直达按钮，保证界面永远
      有明确的最高热度视频入口。
    """
    keyword = result.report.meta.keyword
    search_url = douyin_search_url(keyword, sort_by_like=True)
    videos = _pick_source_videos(result)

    st.markdown("#### 🔥 该热点最高热度/点赞爆款对标")
    if videos:
        top = videos[0]
        st.markdown(
            f"##### 🏆 爆款代表视频 ｜ ❤️ {top.like_text} 点赞"
            f" ｜ {top.author_name or '未知作者'}"
        )
        cols = st.columns(len(videos))
        for idx, (col, video) in enumerate(zip(cols, videos)):
            with col:
                if video.has_cover:
                    try:
                        st.image(video.cover_url, use_container_width=True)
                    except Exception:  # noqa: BLE001 - 封面加载失败不应影响报告
                        st.markdown(_cover_placeholder("封面加载失败"), unsafe_allow_html=True)
                else:
                    st.markdown(_cover_placeholder("暂无封面"), unsafe_allow_html=True)
                st.markdown(
                    f"**{_like_badge(video, is_top=idx == 0)}**"
                )
                st.caption(f"{video.author_name or '未知作者'} ｜ {video.title or '（无标题）'}")
                st.link_button(
                    "🔗 直达抖音观看原视频",
                    video.video_url,
                    use_container_width=True,
                    key=f"{key_prefix}_video_{idx}",
                )
    else:
        st.caption("已按「最多点赞」为你定位该热点的头部爆款视频。")

    st.link_button(
        "🔥 查看该热点『最多点赞/播放』视频列表",
        search_url,
        use_container_width=True,
        key=f"{key_prefix}_search",
    )
    st.divider()


def render_kpi(report: TrendReport) -> None:
    """中层：4 张彩色指标卡。"""
    noise = report.noise_filtering
    emotion = report.emotion_decoding
    viral = report.viral_mechanism

    emotions = "、".join(emotion.core_emotions[:3]) or "—"
    follow_text, follow_sub, follow_color, follow_pct = _follow_metric(report)

    cards = [
        _kpi_card(
            "📈 内容价值分",
            f"{noise.value_score}",
            f"满分 100 ｜ {noise.noise_type.value}",
            _score_color(noise.value_score),
            pct=noise.value_score,
        ),
        _kpi_card(
            "💗 核心情绪",
            emotions,
            f"情绪强度 {emotion.emotion_intensity}/100",
            "#7c3aed",
            pct=emotion.emotion_intensity,
        ),
        _kpi_card(
            "🔥 争议指数",
            f"{viral.controversy_level}",
            "越高越容易站队引爆" if viral.controversy_level >= 50 else "争议温和，共鸣为主",
            _heat_color(viral.controversy_level),
            pct=viral.controversy_level,
        ),
        _kpi_card("🎯 跟风推荐度", follow_text, follow_sub, follow_color, pct=follow_pct),
    ]

    cols = st.columns(4)
    for col, html in zip(cols, cards):
        with col:
            st.markdown(html, unsafe_allow_html=True)


def render_run_metrics(report: TrendReport) -> None:
    """把 Token / 耗时 / 成本等调试指标下沉到折叠面板。"""
    meta = report.meta
    with st.expander("🛠️ 运行耗时与 Token 成本明细", expanded=False):
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("端到端耗时", f"{meta.elapsed_seconds:.2f} s")
        c2.metric("API 延迟", f"{meta.latency_ms} ms")
        c3.metric("Token 合计", f"{meta.total_tokens:,}")
        c4.metric("预估成本", f"${meta.total_cost_usd:.6f}")

        st.caption(
            f"prompt={meta.prompt_tokens:,} ｜ completion={meta.completion_tokens:,} "
            f"｜ 模型 `{meta.model}` ｜ 修复重试 {meta.repair_attempts} 次 "
            f"｜ 输入 {meta.raw_text_chars} 字符"
            f"{'（已截断）' if meta.raw_text_truncated else ''}"
            f"｜ 去重 {meta.deduped_lines} 条"
        )
        if meta.mock:
            st.info("当前为 Mock 模式，指标来自离线样例数据。")


def render_storyboard(report: TrendReport, *, key_prefix: str = "story") -> None:
    """拍摄分镜剧本：Hook 高亮 + 分镜 / 步骤表格 + 一键导出 Markdown。"""
    if not report.actionable_insights:
        st.info("本次报告未产出可执行切入点（可能为噪声话题）。")
        st.divider()
        _storyboard_download(report, key_prefix=key_prefix)
        return

    for idx, insight in enumerate(report.actionable_insights, start=1):
        st.markdown(f"### 🎬 角度 {idx}：{insight.angle_title}")
        if insight.target_audience:
            st.caption(f"🎯 目标人群：{insight.target_audience}")

        render_angle_comparison(insight, index=idx)

        render_hook_matrix(insight, key_prefix=key_prefix, index=idx)

        if insight.engagement_trigger:
            st.markdown("**💬 评论区互动引导点**")
            st.info(insight.engagement_trigger)

        st.markdown("**🎞️ 内容分镜提纲**")
        st.markdown(_storyboard_table(insight.content_outline))

        st.markdown("**✅ 执行步骤**")
        st.markdown(_steps_table(insight.execution_steps))

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**💰 变现 / 引流**")
            st.success(insight.monetization or "（未给出）")
        with c2:
            st.markdown("**⚠️ 合规风险**")
            st.warning(insight.risk_notes or "（未给出）")

        if idx < len(report.actionable_insights):
            st.divider()

    st.divider()
    _storyboard_download(report, key_prefix=key_prefix)


def render_result(result: AnalysisResult, *, key_prefix: str) -> None:
    """渲染完整结果：封面墙 → 结论 → 指标卡 → 指标明细 → 三 Tab。"""
    report = result.report
    meta = report.meta

    if meta.mock:
        st.warning("⚠️ 当前为 Mock 模式，报告为离线样例数据，非真实分析结果。")

    verdict = (
        f"✅ 有效话题（可跟进）｜内容价值 {report.noise_filtering.value_score}/100"
        if report.is_valuable
        else f"⛔ 噪声话题（不建议跟）｜内容价值 {report.noise_filtering.value_score}/100"
    )
    (st.success if report.is_valuable else st.error)(verdict)
    if result.source_url:
        st.caption(f"来源：{result.source_label} ｜ {result.source_url}")

    st.divider()
    render_kpi(report)
    st.write("")
    render_run_metrics(report)

    st.divider()
    # 「卡片看板」下方、「报告正文」上方 —— 最高热度/点赞爆款对标
    render_video_wall(result, key_prefix=key_prefix)

    tab_insight, tab_story, tab_json = st.tabs(
        ["💡 核心洞察", "🎬 拍摄分镜剧本", "⚙️ JSON 源码"]
    )

    markdown = render_markdown(report)
    with tab_insight:
        render_risk_assessment(report)
        st.divider()
        render_pitfall_warnings(report)
        st.markdown(markdown)
        st.download_button(
            "⬇️ 下载 Markdown 报告",
            data=markdown,
            file_name=f"{_safe_filename(meta.keyword)}.md",
            mime="text/markdown",
            key=f"{key_prefix}_dl_md",
        )

    with tab_story:
        render_storyboard(report, key_prefix=key_prefix)

    with tab_json:
        json_text = render_json(report)
        st.code(json_text, language="json")
        st.download_button(
            "⬇️ 下载 JSON 报告",
            data=json_text,
            file_name=f"{_safe_filename(meta.keyword)}.json",
            mime="application/json",
            key=f"{key_prefix}_dl_json",
        )


# --------------------------------------------------------------------------- #
# 页面：手动分析
# --------------------------------------------------------------------------- #
def apply_preset() -> None:
    """预设下拉回调：把案例填入输入框（仅在切换预设时覆盖）。"""
    preset = PRESETS.get(st.session_state.get("manual_preset", MANUAL_PRESET))
    if preset is None:
        return
    st.session_state["manual_keyword"] = preset["keyword"]
    st.session_state["manual_text"] = preset["raw_text"]


def run_demo(keyword: str, raw_text: str, settings: Settings) -> None:
    """Demo 按钮的 ``on_click`` 回调：填入预设词条与评论并直接触发分析。

    作为回调执行（先于控件重渲染），因此在输入框实例化前写入 ``session_state``，
    既能让输入框回填预设内容，也能立即产出并渲染分析面板。
    """
    st.session_state["manual_keyword"] = keyword
    st.session_state["manual_text"] = raw_text
    run_analysis(
        keyword,
        raw_text,
        settings,
        store_key="manual_result",
        source_label="demo",
    )


def render_demo_shortcuts(settings: Settings) -> None:
    """空状态填充：「💡 或选择以下预设爆款热点秒级体验」3 个 Demo 快捷按钮。"""
    demos = [(name, data) for name, data in PRESETS.items() if data is not None]
    if not demos:
        return

    st.markdown("#### 💡 或选择以下预设爆款热点秒级体验")
    with st.container(border=True):
        cols = st.columns(len(demos))
        for col, (name, data) in zip(cols, demos):
            with col:
                st.button(
                    name,
                    key=f"demo_{data['keyword']}",
                    use_container_width=True,
                    help=f"一键填入并分析：{data['keyword']}",
                    on_click=run_demo,
                    args=(data["keyword"], data["raw_text"], settings),
                )


def page_manual(settings: Settings) -> None:
    st.subheader("✍️ 手动动态分析")
    st.caption("填入词条与高赞评论，或点击下方 Demo 卡片，立即生成四步结构化报告。")

    with st.container(border=True):
        keyword = st.text_input(
            "热点词条（keyword）",
            key="manual_keyword",
            placeholder="例如：年轻人开始流行反向消费",
        )
        raw_text = st.text_area(
            "相关内容 / 高赞评论（raw_text）",
            key="manual_text",
            height=220,
            placeholder="每行一条评论，例如：\n不是不想买，是真买不起\n连反向消费我都要分期了",
        )

        st.selectbox(
            "🎯 选择预设爆款案例（自动填充输入框）",
            list(PRESETS.keys()),
            key="manual_preset",
            on_change=apply_preset,
        )

        if st.button(
            "🚀 开始分析", type="primary", key="manual_run", use_container_width=True
        ):
            run_analysis(
                keyword,
                raw_text,
                settings,
                store_key="manual_result",
                source_label="manual",
            )

    result = st.session_state.get("manual_result")
    if result is None:
        st.write("")
        render_demo_shortcuts(settings)
    else:
        st.divider()
        render_result(result, key_prefix="manual")


# --------------------------------------------------------------------------- #
# 页面：实时热榜
# --------------------------------------------------------------------------- #
def page_hot(settings: Settings) -> None:
    st.subheader("🔥 实时热榜抓取")
    st.caption("点击抓取抖音热榜 → 下拉选择词条 → 自动抓取评论与 Top 爆款视频并触发四步分析。")

    with st.container(border=True):
        st.markdown("##### 🛰️ 采集参数配置")
        col1, col2 = st.columns(2)
        hot_limit = col1.slider("热榜条数", 5, 50, 15, step=5)
        comments_per = col2.slider("每条评论数", 5, 100, 30, step=5)
        fetch_clicked = st.button(
            "🔃 抓取热榜", type="primary", key="hot_fetch", use_container_width=True
        )

    if fetch_clicked:
        try:
            with st.spinner("正在启动浏览器抓取抖音热榜…"):
                source = get_source("douyin", headless=True)
                spots = source.list_hotspots(limit=int(hot_limit))
            st.session_state["hot_source"] = source
            st.session_state["hotspots"] = spots
            st.session_state.pop("hot_result", None)
            st.success(f"抓取到 {len(spots)} 条热点。")
        except FetchError as exc:
            st.error(f"抓取失败：{exc}")

    hotspots = st.session_state.get("hotspots") or []
    if not hotspots:
        return

    labels = [f"{i + 1}. {h.title}" for i, h in enumerate(hotspots)]
    picked = st.selectbox(
        "选择热点词条", range(len(labels)), format_func=lambda i: labels[i], key="hot_pick"
    )
    hotspot = hotspots[picked]
    if hotspot.url:
        st.caption(f"来源链接：{hotspot.url}")

    if st.button("🧲 抓取评论并分析", key="hot_run"):
        source = st.session_state.get("hot_source")
        raw_text = ""
        videos: list[VideoItem] = list(hotspot.videos)

        try:
            with st.spinner("正在抓取评论…"):
                comments = source.fetch_comments(hotspot, limit=int(comments_per))
            if comments:
                raw_text = "\n".join(comments)
                st.info(f"抓取到 {len(comments)} 条评论。")
            else:
                st.warning("未抓取到评论，将仅基于词条分析。")
        except FetchError as exc:
            st.error(f"评论抓取失败：{exc}（将仅基于词条分析）")

        try:
            with st.spinner("正在按『最多点赞』抓取头部爆款视频…"):
                fetched = source.list_top_videos(hotspot.keyword, limit=3)
            if fetched:
                videos = fetched
                st.info(f"已定位 {len(fetched)} 条最高点赞爆款视频。")
        except FetchError as exc:
            st.warning(f"爆款视频抓取失败：{exc}（将使用搜索页直达链接兜底）")

        run_analysis(
            hotspot.keyword,
            raw_text,
            settings,
            store_key="hot_result",
            videos=videos,
            source_url=hotspot.url,
            source_label="douyin",
        )

    result = st.session_state.get("hot_result")
    if result is not None:
        st.divider()
        render_result(result, key_prefix="hot")


# --------------------------------------------------------------------------- #
# 入口
# --------------------------------------------------------------------------- #
def main() -> None:
    st.set_page_config(page_title="抖音热点深度分析", page_icon="🔥", layout="wide")
    inject_global_css()

    st.title("🔥 抖音热点深度分析")
    st.caption(
        "输入词条与评论（或实时抓取热榜），按「噪声过滤 → 情绪解构 → 传播引爆点 → 行动落地」"
        "四步输出结构化 JSON / Markdown 报告。"
    )

    try:
        base = load_settings()
    except ConfigError as exc:
        st.error(f"配置错误：{exc}")
        st.stop()

    settings = build_sidebar(base)
    render_env_status(_has_api_key(settings))

    if settings.mock_mode:
        st.info("已开启 Mock 模式：不会调用真实模型，结果来自离线样例数据。")

    tab_manual, tab_hot = st.tabs(["✍️ 手动分析", "🔥 实时热榜"])
    with tab_manual:
        page_manual(settings)
    with tab_hot:
        page_hot(settings)


if __name__ == "__main__":
    main()
