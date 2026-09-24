"""采集源注册表：名称 → 工厂函数。

便于 CLI / API 通过字符串选择数据源，也方便第三方注册自有实现：

    from hotspot_analysis.fetcher import register_source

    register_source("mysource", lambda **kw: MySource(**kw))
"""

from __future__ import annotations

from typing import Any, Callable

from hotspot_analysis.fetcher.base import FetchError, HotspotSource

SourceFactory = Callable[..., HotspotSource]

_REGISTRY: dict[str, SourceFactory] = {}


def register_source(name: str, factory: SourceFactory) -> None:
    """注册/覆盖一个数据源工厂。"""
    _REGISTRY[name.strip().lower()] = factory


def available_sources() -> list[str]:
    """返回已注册的数据源名称。"""
    return sorted(_REGISTRY)


def _manual_factory(**kwargs: Any) -> HotspotSource:
    from hotspot_analysis.fetcher.manual import ManualSource

    return ManualSource(items=kwargs.get("items"))


def _douyin_factory(**kwargs: Any) -> HotspotSource:
    from hotspot_analysis.fetcher.douyin import DouyinSource

    allowed = {
        "headless",
        "storage_state",
        "hot_url",
        "nav_timeout_ms",
        "scroll_times",
        "wait_after_nav_ms",
        "hot_js",
        "comment_js",
        "video_js",
        "top_video_js",
        "user_agent",
    }
    return DouyinSource(**{k: v for k, v in kwargs.items() if k in allowed})


register_source("manual", _manual_factory)
register_source("douyin", _douyin_factory)


def get_source(name: str, **kwargs: Any) -> HotspotSource:
    """按名称创建数据源实例。

    Raises:
        FetchError: 名称未注册时。
    """
    key = (name or "").strip().lower()
    if key not in _REGISTRY:
        raise FetchError(
            f"未知数据源: {name!r}。可选：{', '.join(available_sources()) or '（无）'}"
        )
    return _REGISTRY[key](**kwargs)
