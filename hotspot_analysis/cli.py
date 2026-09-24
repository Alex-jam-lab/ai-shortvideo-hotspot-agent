"""命令行入口（typer + rich）。

示例：
    python -m hotspot_analysis.cli --keyword "词条" --text "评论原文"
    python -m hotspot_analysis.cli --keyword "词条" --file examples/sample_input.json
    python -m hotspot_analysis.cli --file examples/sample_input.json --format both --out ./output
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel

from hotspot_analysis.analyzer import AnalyzerError, HotspotAnalyzer
from hotspot_analysis.config import ConfigError, load_settings
from hotspot_analysis.demo_data import build_demo_report
from hotspot_analysis.fetcher import FetchError, collect_bundles, get_source
from hotspot_analysis.fetcher.base import HotspotBundle
from hotspot_analysis.renderers import render


def _force_utf8_streams() -> None:
    """在 Windows 控制台（默认 GBK）下避免中文/符号输出报错。"""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):  # pragma: no cover
                pass


_force_utf8_streams()

app = typer.Typer(
    add_completion=False,
    help="抖音热点深度分析工具：输入词条与评论，输出四步结构化报告。",
)
# 关闭 legacy_windows 渲染器，避免非 ASCII 字符在 GBK 控制台报错
console = Console(legacy_windows=False)


def _read_input_file(path: Path) -> list[dict[str, str]]:
    """读取批量输入 JSON。

    支持两种结构：
      - 单条：{"keyword": "...", "raw_text": "..."}
      - 多条：[{"keyword": "...", "raw_text": "..."}, ...]
    """
    if not path.exists():
        raise typer.BadParameter(f"文件不存在: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list):
        return data
    raise typer.BadParameter("输入文件必须是对象或对象数组。")


def _safe_filename(keyword: str) -> str:
    invalid = '<>:"/\\|?*'
    name = "".join("_" if c in invalid else c for c in keyword).strip()
    return (name or "report")[:60]


def _run_fetch(
    source_name: str,
    *,
    hot_limit: int,
    comments_per: int,
    headless: bool,
    storage_state: Optional[Path],
) -> list[HotspotBundle]:
    """执行采集（浏览器自动化 / 手动源），返回 HotspotBundle 列表。"""
    kwargs: dict[str, object] = {}
    if source_name.strip().lower() == "douyin":
        kwargs = {
            "headless": headless,
            "storage_state": str(storage_state) if storage_state else None,
        }
    source = get_source(source_name, **kwargs)

    console.print(
        f"[bold cyan]>> 正在采集：{source_name}（前 {hot_limit} 条，"
        f"每条最多 {comments_per} 条评论）[/bold cyan]"
    )

    def _progress(index: int, total: int, hs) -> None:  # noqa: ANN001
        console.print(f"[cyan]   [{index}/{total}] {hs.title}[/cyan]")

    return collect_bundles(
        source, hot_limit=hot_limit, comments_per=comments_per, on_item=_progress
    )


def _dump_bundles(bundles: list[HotspotBundle], path: Path) -> None:
    """把采集结果保存为可直接复用的输入 JSON。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [
        {
            "keyword": b.keyword,
            "raw_text": b.to_task()["raw_text"],
            "source": b.source,
            "url": b.hotspot.url if b.hotspot else "",
        }
        for b in bundles
    ]
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


@app.command()
def analyze(
    keyword: Optional[str] = typer.Option(
        None, "--keyword", "-k", help="热点词条"
    ),
    text: Optional[str] = typer.Option(
        None, "--text", "-t", help="相关内容 / 高赞评论原文"
    ),
    file: Optional[Path] = typer.Option(
        None, "--file", "-f", help="批量输入 JSON 文件（单条或数组）"
    ),
    fmt: str = typer.Option(
        "md", "--format", help="输出格式：json | md | both"
    ),
    out: Optional[Path] = typer.Option(
        None, "--out", "-o", help="输出文件路径（.md/.json）或目录（both 模式）"
    ),
    show_config: bool = typer.Option(
        False, "--show-config", help="打印脱敏后的当前配置后退出"
    ),
    demo: bool = typer.Option(
        False, "--demo", help="使用内置样例数据离线生成报告（无需 API Key）"
    ),
    mock: bool = typer.Option(
        False, "--mock", help="离线 Mock 模式：跳过真实请求，读取样例数据（等同 MOCK_MODE=true）"
    ),
    source: Optional[str] = typer.Option(
        None, "--source", help="采集数据源：douyin（Playwright，需可选依赖）/ manual"
    ),
    hot_limit: int = typer.Option(10, "--hot-limit", help="采集热榜条数上限"),
    comments_per: int = typer.Option(
        50, "--comments-per", help="每条热点抓取评论数上限"
    ),
    fetch_only: bool = typer.Option(
        False, "--fetch-only", help="仅采集不分析（配合 --fetch-dump 导出）"
    ),
    fetch_dump: Optional[Path] = typer.Option(
        None, "--fetch-dump", help="把采集结果保存为输入 JSON 文件"
    ),
    storage_state: Optional[Path] = typer.Option(
        None, "--storage-state", help="Playwright 登录态文件（storage_state.json）"
    ),
    no_headless: bool = typer.Option(
        False, "--no-headless", help="采集时显示浏览器窗口（便于手动过验证）"
    ),
) -> None:
    """执行热点分析并输出报告。"""
    if demo:
        report = build_demo_report(keyword or "年轻人开始流行反向消费")
        console.print(
            Panel(
                f"结论：{'有效话题' if report.is_valuable else '噪声话题'}"
                f"｜价值分 {report.noise_filtering.value_score}/100\n"
                f"建议：{report.conclusion}",
                title="[demo] 离线样例报告",
                border_style="cyan",
            )
        )
        _emit(report, fmt=fmt, out=out, keyword=report.meta.keyword)
        raise typer.Exit(code=0)

    # --mock 优先于 .env：在加载配置前注入环境变量（load_dotenv 不覆盖已存在变量）
    if mock:
        os.environ["MOCK_MODE"] = "1"

    try:
        settings = load_settings()
    except ConfigError as exc:
        console.print(f"[red]配置错误：{exc}[/red]")
        raise typer.Exit(code=2) from exc

    if show_config:
        console.print_json(data=settings.masked())
        raise typer.Exit(code=0)

    # 组装任务列表
    tasks: list[dict[str, str]] = []
    if file is not None:
        tasks.extend(_read_input_file(file))
    if keyword:
        tasks.append({"keyword": keyword, "raw_text": text or ""})

    # 可选：先采集再分析（--source douyin）
    if source:
        try:
            bundles = _run_fetch(
                source,
                hot_limit=hot_limit,
                comments_per=comments_per,
                headless=not no_headless,
                storage_state=storage_state,
            )
        except FetchError as exc:
            console.print(f"[red]采集失败：{exc}[/red]")
            raise typer.Exit(code=3) from exc

        tasks.extend(b.to_task() for b in bundles)
        console.print(f"[green]采集完成：{len(bundles)} 条热点。[/green]")

        if fetch_dump is not None:
            _dump_bundles(bundles, fetch_dump)
            console.print(f"[green]已保存采集结果：{fetch_dump}[/green]")

        if fetch_only:
            if fetch_dump is None:
                console.print_json(data=[b.to_task() for b in bundles])
            raise typer.Exit(code=0)

    if not tasks:
        console.print(
            "[yellow]未提供输入。请使用 --keyword/--text、--file 或 --source。[/yellow]"
        )
        raise typer.Exit(code=1)

    analyzer = HotspotAnalyzer(settings)
    ok, failed = 0, 0

    for item in tasks:
        kw = str(item.get("keyword", "")).strip()
        raw = str(item.get("raw_text", "") or "")
        if not kw:
            console.print("[yellow]跳过：缺少 keyword 的条目。[/yellow]")
            continue

        console.print(f"[bold cyan]>> 正在分析：{kw}[/bold cyan]")
        try:
            report = analyzer.analyze(kw, raw)
        except (AnalyzerError, ConfigError) as exc:
            failed += 1
            console.print(f"[red][x] 分析失败：{exc}[/red]")
            continue

        ok += 1
        verdict = "有效话题" if report.is_valuable else "噪声话题"
        console.print(
            Panel(
                f"结论：{verdict}｜价值分 {report.noise_filtering.value_score}/100\n"
                f"建议：{report.conclusion}",
                title=f"[ok] {kw}",
                border_style="green",
            )
        )

        _emit(report, fmt=fmt, out=out, keyword=kw)

    console.print(f"[bold]完成：成功 {ok} 条，失败 {failed} 条。[/bold]")
    if failed and ok == 0:
        raise typer.Exit(code=1)


def _emit(report, fmt: str, out: Optional[Path], keyword: str) -> None:  # noqa: ANN001
    """按格式输出到屏幕或文件。"""
    fmt = fmt.lower()
    formats = ["md", "json"] if fmt == "both" else [fmt]

    for f in formats:
        content = render(report, f)
        if out is None:
            console.print(content)
            continue

        # both 模式或 out 为目录时，按 keyword 命名落盘
        if fmt == "both" or out.suffix == "":
            out.mkdir(parents=True, exist_ok=True)
            ext = "json" if f == "json" else "md"
            target = out / f"{_safe_filename(keyword)}.{ext}"
        else:
            target = out
            target.parent.mkdir(parents=True, exist_ok=True)

        target.write_text(content, encoding="utf-8")
        console.print(f"[green]已写入：{target}[/green]")


if __name__ == "__main__":
    app()
