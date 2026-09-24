"""采集层（Fetcher）：把「热点来源」与「分析器」解耦。

分析器（analyzer）只接收 keyword + raw_text；本层负责把不同来源
（手动输入、文件、浏览器自动化、第三方 API）统一成 HotspotBundle，
从而让「采集」与「分析」可各自独立演进。

用法：
    from hotspot_analysis.fetcher import get_source, collect_bundles

    source = get_source("douyin", headless=True)
    bundles = collect_bundles(source, hot_limit=10, comments_per=50)
"""

from __future__ import annotations

from hotspot_analysis.fetcher.base import (
    FetchError,
    Hotspot,
    HotspotBundle,
    HotspotSource,
    VideoItem,
    collect_bundles,
    douyin_search_url,
)
from hotspot_analysis.fetcher.manual import ManualSource
from hotspot_analysis.fetcher.registry import (
    available_sources,
    get_source,
    register_source,
)

__all__ = [
    "FetchError",
    "Hotspot",
    "HotspotBundle",
    "HotspotSource",
    "ManualSource",
    "VideoItem",
    "available_sources",
    "collect_bundles",
    "douyin_search_url",
    "get_source",
    "register_source",
]


def __getattr__(name: str):  # pragma: no cover - 延迟导入可选依赖
    """延迟暴露 DouyinSource，避免未安装 Playwright 时导入即报错。"""
    if name == "DouyinSource":
        from hotspot_analysis.fetcher.douyin import DouyinSource

        return DouyinSource
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
