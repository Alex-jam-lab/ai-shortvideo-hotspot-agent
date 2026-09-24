"""采集层测试：手动源、协议、编排与抖音源解析（离线，不依赖 Playwright）。"""

from __future__ import annotations

import json

import pytest

from hotspot_analysis.fetcher import (
    FetchError,
    Hotspot,
    HotspotBundle,
    HotspotSource,
    ManualSource,
    VideoItem,
    available_sources,
    collect_bundles,
    douyin_search_url,
    get_source,
)
from hotspot_analysis.fetcher.douyin import DouyinSource, parse_embedded_json


# ---- ManualSource ----
def test_manual_source_lists_hotspots():
    src = ManualSource([{"keyword": "热身话题", "raw_text": "1\n2\n3"}])
    spots = src.list_hotspots(limit=10)
    assert len(spots) == 1
    assert spots[0].title == "热身话题"
    assert spots[0].keyword == "热身话题"
    assert spots[0].rank == 1


def test_manual_source_skips_empty_keyword():
    src = ManualSource([{"keyword": "  ", "raw_text": "x"}, {"keyword": "ok"}])
    assert [h.title for h in src.list_hotspots()] == ["ok"]


def test_manual_source_from_file(tmp_path):
    p = tmp_path / "in.json"
    p.write_text(
        json.dumps([{"keyword": "A", "raw_text": "a1\na2"}], ensure_ascii=False),
        encoding="utf-8",
    )
    src = ManualSource.from_file(p)
    assert src.list_hotspots()[0].title == "A"
    assert src.fetch_comments(src.list_hotspots()[0]) == ["a1", "a2"]


def test_manual_source_from_file_array_and_single(tmp_path):
    single = tmp_path / "single.json"
    single.write_text(json.dumps({"keyword": "S"}), encoding="utf-8")
    assert ManualSource.from_file(single).list_hotspots()[0].title == "S"


def test_manual_source_from_file_missing():
    with pytest.raises(FetchError):
        ManualSource.from_file("不存在的文件.json")


# ---- HotspotBundle ----
def test_bundle_to_task_joins_comments():
    bundle = HotspotBundle(keyword="K", comments=["c1", "c2"])
    assert bundle.to_task() == {"keyword": "K", "raw_text": "c1\nc2"}


def test_bundle_to_task_prefers_explicit_raw_text():
    bundle = HotspotBundle(keyword="K", raw_text="原文", comments=["c1"])
    assert bundle.to_task()["raw_text"] == "原文"


def test_bundle_to_task_max_comments():
    bundle = HotspotBundle(keyword="K", comments=["a", "b", "c"])
    assert bundle.to_task(max_comments=2)["raw_text"] == "a\nb"


# ---- 协议 & 注册表 ----
def test_manual_source_satisfies_protocol():
    assert isinstance(ManualSource(), HotspotSource)


def test_available_sources_registered():
    names = available_sources()
    assert "manual" in names
    assert "douyin" in names


def test_get_source_unknown_raises():
    with pytest.raises(FetchError):
        get_source("不存在")


def test_get_source_manual_ok():
    src = get_source("manual", items=[{"keyword": "X"}])
    assert isinstance(src, ManualSource)


# ---- collect_bundles ----
class _FakeSource:
    name = "fake"

    def __init__(self, spots, fail_on=()):
        self._spots = spots
        self._fail_on = set(fail_on)

    def list_hotspots(self, limit=20):
        return self._spots[:limit]

    def fetch_comments(self, hotspot, limit=50):
        if hotspot.title in self._fail_on:
            raise FetchError("模拟抓取失败")
        return [f"{hotspot.title}-c{i}" for i in range(1, limit + 1)]


def test_collect_bundles_basic():
    src = _FakeSource([Hotspot(title="热点一"), Hotspot(title="热点二")])
    bundles = collect_bundles(src, hot_limit=10, comments_per=2)
    assert [b.keyword for b in bundles] == ["热点一", "热点二"]
    assert bundles[0].comments == ["热点一-c1", "热点一-c2"]
    assert bundles[0].source == "fake"


def test_collect_bundles_survives_fetch_error():
    src = _FakeSource([Hotspot(title="坏"), Hotspot(title="好")], fail_on={"坏"})
    bundles = collect_bundles(src, hot_limit=10, comments_per=3)
    assert len(bundles) == 2
    assert bundles[0].comments == []
    assert bundles[1].comments


def test_collect_bundles_on_item_progress():
    seen: list[tuple[int, int, str]] = []
    src = _FakeSource([Hotspot(title="A"), Hotspot(title="B")])
    collect_bundles(
        src, hot_limit=10, comments_per=1, on_item=lambda i, t, hs: seen.append((i, t, hs.title))
    )
    assert seen == [(1, 2, "A"), (2, 2, "B")]


# ---- VideoItem ----
def test_video_item_like_text_formatting():
    assert VideoItem(like_count=0).like_text == "0"
    assert VideoItem(like_count=999).like_text == "999"
    assert VideoItem(like_count=12000).like_text == "1.2万"
    assert VideoItem(like_count=345678).like_text == "34.6万"
    assert VideoItem(cover_url="http://x/y.jpg").has_cover is True
    assert VideoItem().has_cover is False


def test_video_item_in_bundle_via_collect_bundles():
    video = VideoItem(video_url="https://v/1", author_name="老王", like_count=3)
    spot = Hotspot(title="话题", url="https://v/1", videos=[video])
    src = _FakeSource([spot])
    bundles = collect_bundles(src, hot_limit=5, comments_per=5)
    assert len(bundles) == 1
    assert bundles[0].videos == [video]
    assert bundles[0].videos[0].author_name == "老王"


# ---- DouyinSource 解析（不启动浏览器）----
def test_douyin_extract_hotspots():
    src = DouyinSource()
    raw = [
        {"rank": 1, "title": "词条A", "url": "/hot/1", "hot_value": "12345"},
        {"title": "  "},  # 空标题应跳过
        {"title": "词条B"},
    ]
    spots = src._extract_hotspots(raw)
    assert [s.title for s in spots] == ["词条A", "词条B"]
    assert spots[0].hot_value == 12345
    assert spots[1].rank == 3


def test_douyin_extract_hotspots_absolutizes_and_falls_back_video():
    src = DouyinSource()
    spots = src._extract_hotspots(
        [{"title": "词条A", "url": "/hot/1", "cover": "//cdn.x/c.jpg"}]
    )
    assert spots[0].url == "https://www.douyin.com/hot/1"
    assert spots[0].cover == "https://cdn.x/c.jpg"
    # 未显式提供 videos 时，兜底为「抖音搜索页」以便溯源实时视频
    assert len(spots[0].videos) == 1
    assert spots[0].videos[0].video_url == douyin_search_url("词条A")
    assert "/search/" in spots[0].videos[0].video_url
    assert spots[0].videos[0].cover_url == "https://cdn.x/c.jpg"


def test_douyin_search_url_encodes_keyword():
    from urllib.parse import quote

    assert douyin_search_url("反向消费") == (
        "https://www.douyin.com/search/" + quote("反向消费")
    )
    url = douyin_search_url("a b&c")
    assert url.startswith("https://www.douyin.com/search/")
    # 查询串的 & 属于排序参数分隔符，词条内的空格与 & 应被编码
    assert " " not in url
    assert quote("a b&c") in url
    assert douyin_search_url("") == "https://www.douyin.com/search/"


def test_douyin_search_url_sort_by_like():
    """sort_by_like=True 时应附加「视频 · 最多点赞」排序参数。"""
    plain = douyin_search_url("反向消费")
    sorted_url = douyin_search_url("反向消费", sort_by_like=True)
    assert sorted_url == plain + "?type=video&sort_type=most_like"


def test_douyin_extract_top_videos_sorts_by_like():
    """按点赞量降序取 Top N；点赞缺失的条目按页面原序排在后面。"""
    src = DouyinSource()
    raw = [
        {"video_url": "/video/1", "like_text": "100", "title": "A"},
        {"video_url": "/video/2", "like_text": "5.6万", "title": "B"},
        {"video_url": "/video/3", "like_text": "1.2万", "title": "C"},
        {"video_url": "/video/4", "title": "D"},  # 无点赞
    ]
    top = src._extract_top_videos(raw, limit=3)
    assert [v.video_url for v in top] == [
        "https://www.douyin.com/video/2",
        "https://www.douyin.com/video/3",
        "https://www.douyin.com/video/1",
    ]
    assert top[0].like_count == 56000
    # limit 生效
    assert len(src._extract_top_videos(raw, limit=1)) == 1


def test_douyin_list_top_videos_without_playwright_raises():
    """未安装 Playwright 时 list_top_videos 应抛 FetchError（构造搜索 URL 后再校验依赖）。"""
    src = DouyinSource()
    try:
        import playwright  # noqa: F401
    except ImportError:
        with pytest.raises(FetchError):
            src.list_top_videos("任意词条")
    else:
        pytest.skip("已安装 playwright，跳过缺失依赖断言")


def test_collect_bundles_falls_back_to_search_url():
    """热点自身无视频时，Bundle 也应带上搜索页链接以便溯源。"""
    src = _FakeSource([Hotspot(title="无视频话题")])
    bundles = collect_bundles(src, hot_limit=1, comments_per=1)
    assert len(bundles[0].videos) == 1
    assert "/search/" in bundles[0].videos[0].video_url


def test_douyin_abs_url():
    assert DouyinSource._abs_url("") == ""
    assert DouyinSource._abs_url("/video/1") == "https://www.douyin.com/video/1"
    assert DouyinSource._abs_url("//cdn.x/a.jpg") == "https://cdn.x/a.jpg"
    assert DouyinSource._abs_url("http://a/b") == "http://a/b"


def test_douyin_parse_like():
    parse = DouyinSource._parse_like
    assert parse("") == 0
    assert parse("3456") == 3456
    assert parse("1.2万") == 12000
    assert parse("3456 点赞") == 3456
    assert parse("abc") == 0


def test_douyin_extract_videos():
    src = DouyinSource()
    raw = [
        {
            "video_url": "/video/123",
            "cover_url": "//cdn.x/a.jpg",
            "author_name": "老王",
            "like_text": "1.2万",
            "title": "标题",
        },
        {"video_url": ""},  # 无链接应跳过
        "not-a-dict",
        {},
    ]
    videos = src._extract_videos(raw)
    assert len(videos) == 1
    assert videos[0].video_url == "https://www.douyin.com/video/123"
    assert videos[0].cover_url == "https://cdn.x/a.jpg"
    assert videos[0].author_name == "老王"
    assert videos[0].like_count == 12000


def test_douyin_clean_title():
    clean = DouyinSource._clean_title
    assert clean("00:211796伙伴们快来围观！#传武 @延昆 · 1周前") == "伙伴们快来围观！"
    assert clean("00:231.0万热点：南山南翻唱145.3万人在看#南山南") == "南山南翻唱"
    assert clean("纯词条") == "纯词条"


def test_douyin_extract_comments():
    src = DouyinSource()
    raw = [{"text": "评论1"}, {"content": "评论2"}, "评论3", "", None]
    assert src._extract_comments(raw) == ["评论1", "评论2", "评论3"]


def test_douyin_fetch_comments_without_url_returns_empty():
    src = DouyinSource()
    assert src.fetch_comments(Hotspot(title="x", url="")) == []


def test_parse_embedded_json():
    html = '<script>window._ROUTER_DATA = {"a": {"b": 1}};</script>'
    assert parse_embedded_json(html) == {"a": {"b": 1}}


def test_parse_embedded_json_absent():
    assert parse_embedded_json("<html></html>") == []


def test_douyin_requires_playwright_message():
    """未安装 Playwright 时应抛 FetchError 并含安装提示；已安装则跳过。"""
    try:
        import playwright  # noqa: F401
    except ImportError:
        with pytest.raises(FetchError) as exc:
            DouyinSource._require_playwright()
        assert "playwright" in str(exc.value).lower()
    else:
        pytest.skip("已安装 playwright，跳过缺失依赖断言")
