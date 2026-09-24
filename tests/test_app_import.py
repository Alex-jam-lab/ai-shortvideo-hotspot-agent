"""Streamlit 界面冒烟测试：模块可导入、main 可调用、纯函数行为正确。

这些用例不启动 Streamlit 服务，也不发起网络请求；
未安装 Streamlit 时整体跳过（UI 为可选依赖）。
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="module")
def app_module():
    """导入 app 模块；缺少 Streamlit 时跳过。"""
    pytest.importorskip("streamlit", reason="未安装 streamlit，跳过 UI 冒烟测试")
    return importlib.import_module("app")


def test_app_module_imports(app_module):
    """app 模块应可导入，且暴露 main 入口与关键函数。"""
    assert callable(getattr(app_module, "main", None))
    for name in (
        "build_sidebar",
        "run_analysis",
        "render_result",
        "render_video_wall",
        "render_kpi",
        "render_storyboard",
        "render_run_metrics",
        "page_manual",
        "page_hot",
        "apply_preset",
        "_pick_source_videos",
        "_cover_placeholder",
        "_like_badge",
        "_build_storyboard_markdown",
        "_storyboard_download",
        "inject_global_css",
        "render_env_status",
        "render_demo_shortcuts",
        "run_demo",
    ):
        assert callable(getattr(app_module, name)), f"缺少可调用对象: {name}"


def test_global_css_covers_core_effects(app_module):
    """全局 CSS 应覆盖按钮 hover 渐变、微阴影、标题层级与暗色卡片边界。"""
    css = app_module.GLOBAL_CSS
    assert "<style>" in css and "</style>" in css
    assert "stButton" in css and ":hover" in css
    assert "linear-gradient" in css
    assert "box-shadow" in css
    assert "h1" in css and "font-size" in css
    assert "prefers-color-scheme: dark" in css
    assert 'div[data-testid="stVerticalBlockBorderWrapper"]' in css


def test_playwright_ready_returns_bool(app_module):
    """环境探测应安全返回布尔值（不抛异常）。"""
    assert isinstance(app_module._playwright_ready(), bool)


def test_presets_available(app_module):
    """预设爆款案例应不少于 2 个，且除占位项外均含 keyword/raw_text。"""
    presets = app_module.PRESETS
    filled = {k: v for k, v in presets.items() if v is not None}
    assert len(filled) >= 2
    for name, data in filled.items():
        assert data.get("keyword"), f"{name} 缺少 keyword"
        assert data.get("raw_text"), f"{name} 缺少 raw_text"


def test_storyboard_table_renders_markdown(app_module):
    """分镜提纲应渲染为 Markdown 表格，并对竖线做转义。"""
    table = app_module._storyboard_table(["钩子：亮出价格差", "展示平替实测"])
    assert table.startswith("| 序号 | 画面 / 步骤 | 核心台词 / Hook |")
    assert "| 1 | 钩子 | 亮出价格差 |" in table
    assert "| 2 | 展示平替实测 | — |" in table
    assert app_module._storyboard_table([]) == "_（模型未给出分镜提纲）_"

    steps = app_module._steps_table(["选品", "拍对比"])
    assert steps.startswith("| 步骤 | 操作说明 |")
    assert "| 1 | 选品 |" in steps

    assert app_module._cell("a|b\nc") == "a\\|b c"


def test_safe_filename_sanitizes(app_module):
    """文件名应剔除非法的 Windows 路径字符，并限制长度。"""
    assert app_module._safe_filename('a/b:c*d?e"f<g>h|i\\j') == "a_b_c_d_e_f_g_h_i_j"
    assert app_module._safe_filename("   ") == "report"
    assert len(app_module._safe_filename("热点" * 100)) == 60


def test_has_api_key_detects_placeholder(app_module, tmp_path):
    """占位 Key 应被判定为未配置。"""
    from dataclasses import replace

    from hotspot_analysis.config import Settings

    base = Settings(
        base_url="https://api.deepseek.com/v1",
        api_key="",
        model="deepseek-chat",
        temperature=0.3,
        timeout=90.0,
        max_retries=1,
        use_json_mode=True,
    )
    assert app_module._has_api_key(base) is False
    assert app_module._has_api_key(replace(base, api_key="sk-your-key")) is False
    assert app_module._has_api_key(replace(base, api_key="sk-abcdef1234567890")) is True


def test_main_is_callable_without_running(app_module):
    """main 应存在于模块入口分支（通过 __main__ 守卫调用）。"""
    import inspect

    source = inspect.getsource(app_module)
    assert 'if __name__ == "__main__":' in source
    assert "st.set_page_config" in inspect.getsource(app_module.main)


def test_pick_source_videos_filters_and_sorts_by_like(app_module):
    """仅挑 /video/ 形态，且按点赞量降序取 Top3。"""
    from hotspot_analysis.fetcher import VideoItem

    result = app_module.AnalysisResult(
        report=None,  # type: ignore[arg-type] - 仅测试筛选逻辑，不访问 report
        videos=[
            VideoItem(video_url="https://www.douyin.com/video/1", like_count=100),
            VideoItem(video_url="https://www.douyin.com/search/词条"),
            VideoItem(video_url="https://www.douyin.com/video/2", like_count=50000),
            VideoItem(video_url=""),
            VideoItem(video_url="https://www.douyin.com/video/3", like_count=9000),
            VideoItem(video_url="https://www.douyin.com/video/4", like_count=1),
        ],
    )
    picked = app_module._pick_source_videos(result)
    assert [v.video_url for v in picked] == [
        "https://www.douyin.com/video/2",
        "https://www.douyin.com/video/3",
        "https://www.douyin.com/video/1",
    ]


def test_like_badge_highlights_top(app_module):
    """Top1 应标注「点赞量最高」，其余展示点赞数。"""
    from hotspot_analysis.fetcher import VideoItem

    top = VideoItem(like_count=120000)
    other = VideoItem(like_count=3456)
    assert "点赞量最高" in app_module._like_badge(top, is_top=True)
    assert "12.0万" in app_module._like_badge(top, is_top=True)
    assert "点赞量最高" not in app_module._like_badge(other, is_top=False)
    assert "3456" in app_module._like_badge(other, is_top=False)


def test_cover_placeholder_html(app_module):
    """封面占位块应包含提示文案与 HTML 结构。"""
    html = app_module._cover_placeholder("暂无封面")
    assert "暂无封面" in html
    assert "height:160px" in html


def test_build_storyboard_markdown_contains_hook_and_tables(app_module):
    """导出脚本文档应含决策建议、A/B Hook 矩阵、风控与分镜 / 步骤表格。"""
    from hotspot_analysis.models import (
        ActionableInsight,
        AnalysisMeta,
        EmotionDecoding,
        HookOption,
        NoiseFiltering,
        NoiseType,
        RiskControl,
        TrendReport,
        ViralMechanism,
    )

    report = TrendReport(
        meta=AnalysisMeta(keyword="年轻人开始流行反向消费", model="deepseek-chat"),
        noise_filtering=NoiseFiltering(
            is_valuable_trend=True,
            noise_type=NoiseType.VALUABLE,
            noise_reason="评论具备二次创作空间",
            value_score=82,
        ),
        emotion_decoding=EmotionDecoding(emotion_intensity=78),
        viral_mechanism=ViralMechanism(controversy_level=65),
        actionable_insights=[
            ActionableInsight(
                angle_title="反向消费实测",
                target_audience="价格敏感年轻人",
                golden_hooks=[
                    HookOption(style="冲突对立型", script="同样是咖啡，我花了 1/3 的钱", target_persona="价格敏感党"),
                    HookOption(style="悬念好奇型", script="这 5 样东西，贵的一定更好吗？", target_persona="理性消费者"),
                    HookOption(style="情绪共鸣型", script="不是买不起，是不想再当冤种", target_persona="被消费主义裹挟者"),
                ],
                engagement_trigger="评论区扣「1」看完整避坑清单",
                content_outline=["钩子：亮出价格差", "展示平替实测"],
                execution_steps=["选品", "拍对比"],
                monetization="挂车带货",
                risk_notes="避免夸大功效",
            )
        ],
        risk_control=RiskControl(
            risk_level="Medium",
            sensitive_words_found=["最", "第一"],
            compliance_suggestions="将「最便宜」改为「更划算」。",
        ),
        conclusion="值得跟进，快节奏实测切入。",
    )

    text = app_module._build_storyboard_markdown(report)
    assert "# 🎬 短视频拍摄脚本：年轻人开始流行反向消费" in text
    assert "## 🎯 决策建议" in text
    assert "值得跟进，快节奏实测切入。" in text
    # A/B 测试 Hook 矩阵（3 套风格）
    assert "🧪 A/B 测试 Hook 矩阵（3 套风格）" in text
    assert "| 风格 | 钩子话术 | 主打人群 |" in text
    assert "| 冲突对立型 | 同样是咖啡，我花了 1/3 的钱 | 价格敏感党 |" in text
    assert "悬念好奇型" in text and "情绪共鸣型" in text
    # 评论区互动引导点
    assert "💬 评论区互动引导点" in text
    assert "> 评论区扣「1」看完整避坑清单" in text
    # 品牌合规与风控评估
    assert "## 🛡️ 品牌合规与风控评估" in text
    assert "**风险等级**：Medium" in text
    assert "最、第一" in text
    assert "将「最便宜」改为「更划算」。" in text
    # 分镜 / 步骤表格
    assert "| 序号 | 画面 / 步骤 | 核心台词 / Hook |" in text
    assert "| 1 | 钩子 | 亮出价格差 |" in text
    assert "| 1 | 选品 |" in text
    assert "挂车带货" in text
    assert text.endswith("\n")


def test_build_storyboard_markdown_without_insights(app_module):
    """无切入点时导出脚本仍应包含决策建议与提示占位。"""
    from hotspot_analysis.models import (
        AnalysisMeta,
        EmotionDecoding,
        NoiseFiltering,
        NoiseType,
        TrendReport,
        ViralMechanism,
    )

    report = TrendReport(
        meta=AnalysisMeta(keyword="噪音话题"),
        noise_filtering=NoiseFiltering(
            is_valuable_trend=False,
            noise_type=NoiseType.OTHER_NOISE,
            noise_reason="无二次创作价值",
            value_score=10,
        ),
        emotion_decoding=EmotionDecoding(),
        viral_mechanism=ViralMechanism(),
        actionable_insights=[],
        conclusion="",
    )
    text = app_module._build_storyboard_markdown(report)
    assert "## 🎯 决策建议" in text
    assert "（模型未给出决策建议）" in text
    assert "（本次报告未产出可执行切入点，可能为噪声话题）" in text


def test_ui_has_risk_card_and_hook_matrix(app_module, monkeypatch):
    """核心洞察应渲染风控色卡；分镜页应以 st.columns 并排 3 套 A/B Hook。"""
    from hotspot_analysis.models import (
        ActionableInsight,
        AnalysisMeta,
        EmotionDecoding,
        HookOption,
        NoiseFiltering,
        NoiseType,
        RiskControl,
        TrendReport,
        ViralMechanism,
    )

    report = TrendReport(
        meta=AnalysisMeta(keyword="反向消费"),
        noise_filtering=NoiseFiltering(
            is_valuable_trend=True,
            noise_type=NoiseType.VALUABLE,
            noise_reason="可复制",
            value_score=80,
        ),
        emotion_decoding=EmotionDecoding(),
        viral_mechanism=ViralMechanism(),
        actionable_insights=[
            ActionableInsight(
                angle_title="角度",
                golden_hooks=[
                    HookOption(style="冲突对立型", script="话术A"),
                    HookOption(style="悬念好奇型", script="话术B"),
                    HookOption(style="情绪共鸣型", script="话术C"),
                ],
                engagement_trigger="你站哪一派？",
            )
        ],
        risk_control=RiskControl(risk_level="High", sensitive_words_found=["最"], compliance_suggestions="改写"),
        conclusion="结论",
    )

    markdown_calls: list[str] = []
    monkeypatch.setattr(app_module.st, "markdown", lambda *a, **k: markdown_calls.append(a[0] if a else ""))
    monkeypatch.setattr(app_module.st, "caption", lambda *a, **k: None)
    monkeypatch.setattr(app_module.st, "info", lambda *a, **k: None)
    monkeypatch.setattr(app_module.st, "code", lambda *a, **k: None)
    monkeypatch.setattr(app_module.st, "error", lambda *a, **k: None)

    container_ctx = __import__("contextlib").nullcontext()
    monkeypatch.setattr(app_module.st, "container", lambda *a, **k: container_ctx)

    cols: list[object] = []

    class _Col:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def _columns(n):
        result = [_Col() for _ in range(n if isinstance(n, int) else len(n))]
        cols.extend(result)
        return result

    monkeypatch.setattr(app_module.st, "columns", _columns)

    # 1) 风控色卡：High → 红色 (#dc2626) 且输出「高风险」
    app_module.render_risk_assessment(report)
    html = " ".join(str(x) for x in markdown_calls if x)
    assert "🛡️ 品牌合规与风控评估" in html
    assert "#dc2626" in html
    assert "高风险" in html

    # 2) Hook 矩阵：渲染 3 套（st.columns(3)）
    cols.clear()
    app_module.render_hook_matrix(report.actionable_insights[0], key_prefix="t", index=1)
    assert len(cols) == 3, f"应并排渲染 3 套 Hook，实际 {len(cols)}"


def _download_report(app_module, *, keyword: str = "反向消费/测试"):
    """构造一份含分镜提纲与互动引导的最小报告，供导出按钮测试复用。"""
    from hotspot_analysis.models import (
        ActionableInsight,
        AnalysisMeta,
        EmotionDecoding,
        NoiseFiltering,
        NoiseType,
        TrendReport,
        ViralMechanism,
    )

    return TrendReport(
        meta=AnalysisMeta(keyword=keyword),
        noise_filtering=NoiseFiltering(
            is_valuable_trend=True,
            noise_type=NoiseType.VALUABLE,
            noise_reason="可复制",
            value_score=80,
        ),
        emotion_decoding=EmotionDecoding(),
        viral_mechanism=ViralMechanism(),
        actionable_insights=[
            ActionableInsight(
                angle_title="角度",
                hook="钩子",
                content_outline=["开场钩子：贵的就一定好吗", "平替实测：实测 3 款饮品", "结尾引导"],
                engagement_trigger="你会怎么选？",
            )
        ],
        conclusion="结论",
    )


def test_storyboard_download_buttons_markdown_and_csv(app_module, monkeypatch):
    """底部应同时提供 Markdown 脚本与 CSV 分镜表两个导出按钮。"""
    report = _download_report(app_module)

    captured: list[dict[str, object]] = []
    monkeypatch.setattr(
        app_module.st,
        "download_button",
        lambda *a, **k: captured.append({**k, "label": a[0] if a else ""}),
    )
    app_module._storyboard_download(report, key_prefix="t")

    assert len(captured) == 2, f"应渲染 2 个导出按钮，实际 {len(captured)}"

    md_btn = captured[0]
    assert md_btn["file_name"] == "反向消费_测试_短视频拍摄脚本.md"
    assert md_btn["mime"] == "text/markdown"
    assert "拍摄脚本" in str(md_btn["label"])

    csv_btn = captured[1]
    assert csv_btn["file_name"] == "反向消费_测试_分镜表.csv"
    assert csv_btn["mime"] == "text/csv"
    assert "CSV" in str(csv_btn["label"])


def test_build_storyboard_csv_columns_and_interaction(app_module):
    """CSV 表头应为「角度/镜号/景别/台词/音效/互动点」，互动点仅挂在最后一镜。"""
    import csv as _csv

    report = _download_report(app_module)
    rows = list(_csv.reader(app_module._build_storyboard_csv(report).splitlines()))

    assert rows[0] == ["角度", "镜号", "景别", "台词", "音效", "互动点"]
    assert len(rows) == 1 + 3, "3 条分镜提纲应产出 3 行数据"

    body = rows[1:]
    assert [r[1] for r in body] == ["1", "2", "3"]
    # 互动点只出现在最后一镜
    assert [r[5] for r in body] == ["", "", "你会怎么选？"]
    # 台词列应剥离「景别前缀：」只留可念内容
    assert body[0][3] == "贵的就一定好吗"
    # 景别 / 音效应有可读取值
    assert all(r[2] and r[4] for r in body)


def test_render_pitfall_warnings_renders_two_columns(app_module, monkeypatch):
    """舆情雷区卡片应并排展示「负面声音」与「避坑雷区」两栏。"""
    from hotspot_analysis.models import (
        AnalysisMeta,
        EmotionDecoding,
        NoiseFiltering,
        NoiseType,
        TrendReport,
        ViralMechanism,
    )

    report = TrendReport(
        meta=AnalysisMeta(keyword="反向消费"),
        noise_filtering=NoiseFiltering(
            is_valuable_trend=True,
            noise_type=NoiseType.VALUABLE,
            noise_reason="可复制",
            value_score=80,
        ),
        emotion_decoding=EmotionDecoding(
            top_controversies=["这不就是穷吗？", "幸存者偏差"],
            pitfall_warnings=["避免贬低高消费人群"],
        ),
        viral_mechanism=ViralMechanism(),
        conclusion="结论",
    )

    html_calls: list[str] = []
    monkeypatch.setattr(app_module.st, "markdown", lambda *a, **k: html_calls.append(str(a[0]) if a else ""))
    monkeypatch.setattr(app_module.st, "caption", lambda *a, **k: None)

    cols: list[object] = []

    class _Col:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def _columns(n):
        result = [_Col() for _ in range(n if isinstance(n, int) else len(n))]
        cols.extend(result)
        return result

    monkeypatch.setattr(app_module.st, "columns", _columns)

    app_module.render_pitfall_warnings(report)

    assert len(cols) == 2, "应并排渲染两栏"
    joined = " ".join(html_calls)
    assert "舆情雷区与避坑预警" in joined
    assert "这不就是穷吗？" in joined
    assert "避免贬低高消费人群" in joined


def test_render_pitfall_warnings_skips_when_empty(app_module, monkeypatch):
    """无争议 / 无雷区（或噪声跳过）时不应渲染卡片。"""
    from hotspot_analysis.models import (
        AnalysisMeta,
        EmotionDecoding,
        NoiseFiltering,
        NoiseType,
        TrendReport,
        ViralMechanism,
    )

    report = TrendReport(
        meta=AnalysisMeta(keyword="反向消费"),
        noise_filtering=NoiseFiltering(
            is_valuable_trend=True,
            noise_type=NoiseType.VALUABLE,
            noise_reason="可复制",
            value_score=80,
        ),
        emotion_decoding=EmotionDecoding(status="skipped"),
        viral_mechanism=ViralMechanism(),
        conclusion="结论",
    )

    called: list[str] = []
    monkeypatch.setattr(app_module.st, "markdown", lambda *a, **k: called.append(str(a[0]) if a else ""))
    app_module.render_pitfall_warnings(report)
    assert called == []


def test_render_angle_comparison_renders_red_blue(app_module, monkeypatch):
    """差异化切入卡片应分别渲染「红海同质化」与「蓝海提案」。"""
    from hotspot_analysis.models import ActionableInsight

    insight = ActionableInsight(
        angle_title="角度",
        mainstream_angles=["平替清单", "省钱攻略"],
        differentiated_angle="反常识：不买才是最贵的省法",
    )

    md_calls: list[str] = []
    success_calls: list[str] = []
    monkeypatch.setattr(app_module.st, "markdown", lambda *a, **k: md_calls.append(str(a[0]) if a else ""))
    monkeypatch.setattr(app_module.st, "success", lambda *a, **k: success_calls.append(str(a[0]) if a else ""))
    monkeypatch.setattr(app_module.st, "caption", lambda *a, **k: None)

    ctx = __import__("contextlib").nullcontext()
    monkeypatch.setattr(app_module.st, "container", lambda *a, **k: ctx)

    cols: list[object] = []

    class _Col:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def _columns(n):
        result = [_Col() for _ in range(n if isinstance(n, int) else len(n))]
        cols.extend(result)
        return result

    monkeypatch.setattr(app_module.st, "columns", _columns)

    app_module.render_angle_comparison(insight, index=1)

    assert len(cols) == 2
    joined = " ".join(md_calls)
    assert "差异化 / 反常识切入视角" in joined
    assert "平替清单" in joined
    assert success_calls == ["反常识：不买才是最贵的省法"]


def test_render_video_wall_always_renders_search_button(app_module, monkeypatch):
    """无源视频时也必须渲染「最多点赞」搜索页直达按钮（不再弱化提示）。"""
    from hotspot_analysis.fetcher import VideoItem

    class _Meta:
        keyword = "测试热点"

    class _Report:
        meta = _Meta()

    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(app_module.st, "link_button", lambda *a, **k: calls.append((a[0], a[1])))
    monkeypatch.setattr(app_module.st, "markdown", lambda *a, **k: None)
    monkeypatch.setattr(app_module.st, "caption", lambda *a, **k: None)
    monkeypatch.setattr(app_module.st, "divider", lambda *a, **k: None)

    result = app_module.AnalysisResult(
        report=_Report(),  # type: ignore[arg-type]
        videos=[VideoItem(video_url="https://www.douyin.com/search/测试热点")],
    )
    app_module.render_video_wall(result, key_prefix="t")

    assert calls, "应渲染至少一个 link_button"
    label, url = calls[0]
    assert "最多点赞" in label
    assert "/search/" in url
    assert "sort_type=most_like" in url


# --------------------------------------------------------------------------- #
# 端到端 UI 冒烟（AppTest，Mock 模式，无网络）
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def app_test():
    """启动 AppTest（不点击任何按钮，全程无网络请求），返回已 run 的实例。"""
    app_testing = pytest.importorskip("streamlit.testing.v1", reason="需要 Streamlit 测试工具")
    AppTest = app_testing.AppTest

    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=90)
    at.run()
    return at


def test_ui_has_env_status_and_cards(app_test):
    """顶部应展示环境状态标签；侧边栏开发者参数应折叠收纳。"""
    assert not app_test.exception, [e.value for e in app_test.exception]

    captions = " ".join(c.value for c in app_test.caption)
    assert "系统环境已就绪" in captions

    # 高级调试配置应存在于折叠面板（expander）中，而非散落在侧边栏
    expander_labels = [e.label for e in app_test.expander]
    assert any("高级调试配置" in str(x) for x in expander_labels)


def test_ui_has_editable_api_key_in_advanced_config(app_test):
    """「⚙️ 高级调试配置」内应提供可编辑的 API Key 输入框（默认回退虚拟环境）。"""
    assert not app_test.exception, [e.value for e in app_test.exception]

    text_inputs = {str(ti.label): ti for ti in app_test.text_input}
    assert any("API Key" in label for label in text_inputs), text_inputs.keys()

    # 密码型输入框（type=password）用于安全填写 Key
    key_inputs = [ti for ti in app_test.text_input if "API Key" in str(ti.label)]
    assert key_inputs, "应存在 API Key 输入框"


def test_ui_removes_pip_hint_and_has_demo_buttons(app_test):
    """正文不应出现 pip 安装提示；空状态下应渲染 3 个 Demo 快捷按钮。"""
    all_text = " ".join(c.value for c in app_test.caption)
    for md in app_test.markdown:
        all_text += " " + str(md.value)
    assert "pip install" not in all_text

    button_labels = [b.label for b in app_test.button]
    demo_labels = [x for x in button_labels if x.startswith(("🔁", "🧊", "💼"))]
    assert len(demo_labels) >= 3, f"应提供 3 个 Demo 按钮，实际：{button_labels}"
    assert any("秒级体验" in str(m.value) for m in app_test.markdown)


# --------------------------------------------------------------------------- #
# 轻量级可视化图表：五维综合战力雷达图 + 评论区主题情绪热力图
# --------------------------------------------------------------------------- #
def _chart_report(app_module):
    """构造一份维度信号齐全的报告，供图表测试复用。"""
    from hotspot_analysis.models import (
        ActionableInsight,
        AnalysisMeta,
        EmotionDecoding,
        NoiseFiltering,
        NoiseType,
        RiskControl,
        TrendReport,
        ViralMechanism,
    )

    return TrendReport(
        meta=AnalysisMeta(keyword="反向消费"),
        noise_filtering=NoiseFiltering(
            is_valuable_trend=True,
            noise_type=NoiseType.VALUABLE,
            noise_reason="可复制",
            value_score=82,
        ),
        emotion_decoding=EmotionDecoding(
            pain_points=["经济压力", "被消费主义裹挟"],
            core_emotions=["共鸣", "焦虑"],
            emotion_intensity=78,
            top_controversies=["这不就是穷吗？"],
        ),
        viral_mechanism=ViralMechanism(
            triggers=["高共鸣"],
            controversy_level=65,
            secondary_creation_potential="高",
        ),
        actionable_insights=[
            ActionableInsight(
                angle_title="反向消费避坑清单",
                monetization="挂车低价好物",
                engagement_trigger="你怎么看？",
            )
        ],
        risk_control=RiskControl(risk_level="Medium", sensitive_words_found=["最"]),
        conclusion="跟进。",
    )


def test_charts_expose_public_entrypoints(app_module):
    """模块应暴露图表渲染入口（雷达图 / 热力图 / 组合渲染）。"""
    for name in ("render_power_radar", "render_comment_heatmap", "render_insight_charts"):
        assert callable(getattr(app_module, name, None)), f"缺少 {name}"


def test_radar_dimensions_five_dimensions_in_range(app_module):
    """雷达图应输出指定的 5 个维度，得分均在 0-100 区间内。"""
    report = _chart_report(app_module)
    dims, values = app_module._radar_dimensions(report)

    assert dims == ["情绪强度", "争议指数", "二次创作潜力", "合规安全性", "商业变现度"]
    assert values[0] == 78.0
    assert values[1] == 65.0
    # 风控 Medium(=70) 命中 1 个敏感词 → 扣 4 分
    assert values[3] == 66.0
    assert all(0.0 <= v <= 100.0 for v in values)


def test_radar_safety_tracks_risk_level(app_module):
    """合规安全性应随风险等级下降（Low > High > Ban）。"""
    from hotspot_analysis.models import RiskControl

    report = _chart_report(app_module)
    safety = {}
    for level in ("Low", "High", "Ban"):
        report.risk_control = RiskControl(risk_level=level, sensitive_words_found=[])
        safety[level] = app_module._radar_dimensions(report)[1][3]

    assert safety["Low"] > safety["High"] > safety["Ban"]


def test_heatmap_matrix_shape_and_scale(app_module):
    """热力矩阵应为「主题 × 高赞/争议/吐槽」，且每格落在 0-100。"""
    report = _chart_report(app_module)
    topics, cols, matrix = app_module._heatmap_matrix(report)

    assert cols == ["高赞", "争议", "吐槽"]
    assert topics, "应至少有一个评论主题"
    assert len(matrix) == len(topics)
    assert all(len(row) == 3 for row in matrix)
    assert all(0.0 <= v <= 100.0 for row in matrix for v in row)


def test_heatmap_matrix_is_deterministic(app_module):
    """同一报告两次构造应得到完全一致的矩阵（图表可复现）。"""
    report = _chart_report(app_module)
    assert app_module._heatmap_matrix(report) == app_module._heatmap_matrix(report)


def test_render_insight_charts_renders_two_columns(app_module, monkeypatch):
    """组合渲染应以两栏并排调用两张图表的渲染函数。"""
    report = _chart_report(app_module)

    calls: list[str] = []
    monkeypatch.setattr(app_module, "render_power_radar", lambda r: calls.append("radar"))
    monkeypatch.setattr(app_module, "render_comment_heatmap", lambda r: calls.append("heat"))

    cols: list[object] = []

    class _Col:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def _columns(n):
        result = [_Col() for _ in range(n if isinstance(n, int) else len(n))]
        cols.extend(result)
        return result

    monkeypatch.setattr(app_module.st, "columns", _columns)

    if app_module.go is None:
        pytest.skip("未安装 plotly")

    app_module.render_insight_charts(report)
    assert len(cols) == 2
    assert calls == ["radar", "heat"]


def test_render_power_radar_emits_plotly_chart(app_module, monkeypatch):
    """雷达图应调用 st.plotly_chart 并带五维标题。"""
    if app_module.go is None:
        pytest.skip("未安装 plotly")

    report = _chart_report(app_module)
    charts: list[object] = []
    markdown_calls: list[str] = []

    monkeypatch.setattr(app_module.st, "plotly_chart", lambda fig, **k: charts.append(fig))
    monkeypatch.setattr(app_module.st, "markdown", lambda *a, **k: markdown_calls.append(str(a[0]) if a else ""))
    monkeypatch.setattr(app_module.st, "caption", lambda *a, **k: None)

    app_module.render_power_radar(report)

    assert len(charts) == 1
    assert any("五维综合战力雷达图" in m for m in markdown_calls)
    # 雷达图应闭合（首尾维度一致）
    trace = charts[0].data[0]
    assert trace.theta[0] == trace.theta[-1]
    assert len(trace.r) == 6


def test_render_comment_heatmap_emits_plotly_chart(app_module, monkeypatch):
    """热力图应调用 st.plotly_chart 并带热力图标题。"""
    if app_module.go is None:
        pytest.skip("未安装 plotly")

    report = _chart_report(app_module)
    charts: list[object] = []
    markdown_calls: list[str] = []

    monkeypatch.setattr(app_module.st, "plotly_chart", lambda fig, **k: charts.append(fig))
    monkeypatch.setattr(app_module.st, "markdown", lambda *a, **k: markdown_calls.append(str(a[0]) if a else ""))
    monkeypatch.setattr(app_module.st, "caption", lambda *a, **k: None)

    app_module.render_comment_heatmap(report)

    assert len(charts) == 1
    assert any("评论区主题情绪热力图" in m for m in markdown_calls)
    trace = charts[0].data[0]
    assert list(trace.x) == ["高赞", "争议", "吐槽"]
