"""采集层数据模型与协议。

- VideoItem        ：一条源视频（视频链接 / 封面 / 作者 / 点赞数）。
- Hotspot          ：榜单上的一条热点（标题 / 热度 / 链接 / 关联源视频）。
- HotspotBundle    ：可直接喂给分析器的输入单元（keyword + raw_text + 源视频）。
- HotspotSource    ：采集源协议，所有来源（手动 / 浏览器 / 第三方 API）实现它。
- collect_bundles  ：通用编排：列榜单 → 逐条抓评论 → 组装 Bundle。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable
from urllib.parse import quote

DOUYIN_ORIGIN = "https://www.douyin.com"


class FetchError(RuntimeError):
    """采集失败：网络异常、风控拦截、依赖缺失、DOM 解析失败等。"""


def douyin_search_url(keyword: str, *, sort_by_like: bool = False) -> str:
    """生成抖音搜索页链接。

    Args:
        keyword: 热点词条。
        sort_by_like: 为 True 时附加 ``type=video&sort_type=most_like``，
            直达「视频 · 最多点赞」排序结果，用于对标头部爆款。

    作为兜底入口：即便抓不到单条视频，前端也能一键跳转到该热点的
    实时视频列表（或按点赞排序的爆款列表）。
    """
    base = f"{DOUYIN_ORIGIN}/search/{quote(str(keyword or '').strip())}"
    if sort_by_like:
        return f"{base}?type=video&sort_type=most_like"
    return base


@dataclass
class VideoItem:
    """一条源视频的展示信息（用于前端「封面卡片墙」）。"""

    video_url: str = ""
    cover_url: str = ""
    author_name: str = ""
    like_count: int = 0
    title: str = ""

    @property
    def like_text(self) -> str:
        """把点赞数格式化为「1.2万」这类易读文案。"""
        n = int(self.like_count or 0)
        if n >= 10000:
            return f"{n / 10000:.1f}万"
        return str(n)

    @property
    def has_cover(self) -> bool:
        return bool(self.cover_url)


@dataclass
class Hotspot:
    """榜单上的一条热点。"""

    rank: int = 0
    title: str = ""
    hot_value: int = 0
    url: str = ""
    cover: str = ""
    source: str = "manual"
    videos: list[VideoItem] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def keyword(self) -> str:
        """分析器所需的词条。"""
        return self.title


@dataclass
class HotspotBundle:
    """可直接喂给分析器的输入单元。"""

    keyword: str
    raw_text: str = ""
    comments: list[str] = field(default_factory=list)
    hotspot: Hotspot | None = None
    source: str = "manual"
    videos: list[VideoItem] = field(default_factory=list)

    def to_task(self, *, max_comments: int | None = None) -> dict[str, str]:
        """转为 CLI/分析器使用的 {"keyword", "raw_text"} 结构。"""
        comments = self.comments
        if max_comments is not None:
            comments = comments[:max_comments]

        text = self.raw_text
        if not text and comments:
            text = "\n".join(c for c in comments if c)
        return {"keyword": self.keyword, "raw_text": text}


@runtime_checkable
class HotspotSource(Protocol):
    """采集源协议。任何实现以下两个方法的对象都可作为数据源。"""

    name: str

    def list_hotspots(self, limit: int = 20) -> list[Hotspot]:
        """返回热榜前 limit 条。"""
        ...

    def fetch_comments(self, hotspot: Hotspot, limit: int = 50) -> list[str]:
        """返回该热点下的高赞评论 / 相关文本。"""
        ...


def collect_bundles(
    source: HotspotSource,
    *,
    hot_limit: int = 20,
    comments_per: int = 50,
    on_item: Any = None,
) -> list[HotspotBundle]:
    """通用编排：列榜单 → 逐条抓评论 → 组装 Bundle。

    Args:
        source: 任意实现了 HotspotSource 协议的数据源。
        hot_limit: 最多取多少条热点。
        comments_per: 每条热点最多抓多少条评论。
        on_item: 可选回调 ``fn(index, total, hotspot)``，用于 CLI 打印进度。

    Returns:
        HotspotBundle 列表；抓评论失败的条目仍会保留（raw_text 为空）。
    """
    hotspots = source.list_hotspots(limit=hot_limit)
    source_name = getattr(source, "name", "unknown")
    bundles: list[HotspotBundle] = []
    total = len(hotspots)

    for idx, hs in enumerate(hotspots, start=1):
        if on_item is not None:
            try:
                on_item(idx, total, hs)
            except Exception:  # noqa: BLE001 - 进度回调不应影响主流程
                pass
        try:
            comments = source.fetch_comments(hs, limit=comments_per)
        except FetchError:
            comments = []
        videos = list(hs.videos)
        if not videos:
            # 防空兜底：没有具体视频时，至少给出抖音搜索页以便溯源
            videos = [VideoItem(video_url=douyin_search_url(hs.keyword), title=hs.title)]
        bundles.append(
            HotspotBundle(
                keyword=hs.keyword,
                comments=comments,
                hotspot=hs,
                source=source_name,
                videos=videos,
            )
        )
    return bundles
