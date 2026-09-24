"""抖音热榜采集源（Playwright 浏览器自动化骨架）。

设计要点
--------
- **可选依赖**：Playwright 不在基础依赖内，未安装时构造/调用会给出明确提示。
- **可注入解析器**：DOM 会随抖音改版而变化，本模块不硬编码选择器，
  而是提供 `DEFAULT_HOT_JS` / `DEFAULT_COMMENT_JS` 默认脚本，
  并允许通过构造函数注入自定义 `hot_js` / `comment_js`。
- **继承即用**：子类重写 `_extract_hotspots()` / `_extract_comments()`
  即可适配新的页面结构，无需改动采集编排。
- **合规提示**：请遵守抖音用户协议与 robots 规则，仅抓取公开数据，
  控制请求频率；登录态通过 `storage_state` 注入，切勿硬编码账号密码。

用法::

    from hotspot_analysis.fetcher import get_source, collect_bundles

    src = get_source("douyin", headless=True)   # 需 pip install -r requirements-fetch.txt
    bundles = collect_bundles(src, hot_limit=10, comments_per=50)
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from hotspot_analysis.fetcher.base import (
    FetchError,
    Hotspot,
    VideoItem,
    douyin_search_url,
)

logger = logging.getLogger(__name__)

DOUYIN_HOT_URL = "https://www.douyin.com/hot"

# 默认脚本：从热榜页 DOM 中抽取结构化数据。若抖音改版导致失效，
# 可通过命令行/构造参数注入新脚本，或继承本类重写 _extract_hotspots。
DEFAULT_HOT_JS = """
() => {
  const seen = new Set();
  const out = [];
  const abs = (u) => {
    if (!u) return '';
    try { return new URL(u, location.origin).href; } catch (e) { return u; }
  };
  const coverOf = (card) => {
    if (!card) return '';
    const img = card.querySelector('img');
    if (!img) return '';
    return abs(img.getAttribute('src') || img.getAttribute('data-src') || '');
  };
  const push = (card, title, href) => {
    title = String(title || '').replace(/\\s+/g, ' ').trim();
    if (!title || title.length < 2 || seen.has(title)) return;
    seen.add(title);
    out.push({
      rank: out.length + 1,
      title,
      url: abs(href || ''),
      hot_value: 0,
      cover: coverOf(card)
    });
  };
  // 主选择器：热榜条目链接（形如 /hot/123456），顺带取同一卡片内 <img> 封面
  document.querySelectorAll('a[href*="/hot/"]').forEach(el => {
    const href = el.getAttribute('href') || '';
    const raw = el.getAttribute('title') || el.innerText || el.textContent || '';
    const card = el.closest('div[class]') || el.parentElement;
    push(card, raw.split('\\n')[0], href);
  });
  // 兜底：热榜卡片中带「热点：」前缀的文本
  if (out.length === 0) {
    document.querySelectorAll('a[href]').forEach(el => {
      const line = (el.innerText || '').split('\\n').find(s => s.includes('热点：'));
      if (line) push(el.parentElement, line.split('热点：')[1], el.getAttribute('href'));
    });
  }
  return out.slice(0, 100);
}
"""

# 默认脚本：从「搜索页（type=video&sort_type=most_like）」抽取头部爆款视频。
# 相比 DEFAULT_VIDEO_JS，额外扫描常见「点赞/播放」数字节点，力求拿到真实点赞量，
# 以便前端按点赞排序展示 Top1~Top3。
DEFAULT_TOP_VIDEO_JS = """
() => {
  const BASE = 'https://www.douyin.com';
  const out = [];
  const seen = new Set();
  const SEP = /[·|\\n\\r\\t]/;
  // 统一补全 URL：协议相对(//) / 根相对(/) / 完整链接 均转为绝对地址。
  const abs = (u) => {
    if (!u) return '';
    u = String(u).trim();
    if (u.startsWith('//')) return 'https:' + u;
    if (/^https?:\\/\\//.test(u)) return u;
    if (u.startsWith('/')) return BASE + u;
    try { return new URL(u, location.origin).href; } catch (e) { return u; }
  };
  // 封面兜底：src → data-src → data-lazy-src → currentSrc（覆盖懒加载）。
  const coverOf = (a, card) => {
    const img = a.querySelector('img') || (card ? card.querySelector('img') : null);
    if (!img) return '';
    return abs(
      img.getAttribute('src') ||
      img.getAttribute('data-src') ||
      img.getAttribute('data-lazy-src') ||
      img.currentSrc ||
      ''
    );
  };
  // 点赞量兜底链：卡片内 like 节点 → 任意数字节点 → 链接文本内「x万赞」。
  const likeOf = (a, card) => {
    if (card) {
      const likeEl = card.querySelector(
        '[data-e2e*="like"], [class*="like-count"], [class*="likeCount"], [class*="like"]'
      );
      if (likeEl) {
        const m = (likeEl.innerText || likeEl.textContent || '').match(/(\\d+(?:\\.\\d+)?万?)/);
        if (m) return m[1];
      }
    }
    const text = (a.getAttribute('title') || a.innerText || '').replace(/\\s+/g, ' ');
    const m = text.match(/(\\d+(?:\\.\\d+)?万?)\\s*(?:点赞|赞|次播放|播放)/);
    return m ? m[1] : '';
  };
  document.querySelectorAll('a[href*="/video/"]').forEach(a => {
    const href = a.getAttribute('href') || '';
    if (!href || seen.has(href)) return;
    seen.add(href);
    const card = a.closest('div[class]') || a.parentElement;
    const raw = (a.getAttribute('title') || a.innerText || '').replace(/\\s+/g, ' ').trim();
    const authorMatch = raw.match(/@([^\\s·|]+)/);
    // 标题：去掉 @作者 之后的内容，保留主体描述
    const title = raw.split(SEP)[0].split('@')[0].trim();
    out.push({
      video_url: abs(href),
      cover_url: coverOf(a, card),
      author_name: authorMatch ? authorMatch[1] : '',
      like_text: likeOf(a, card),
      title: title.slice(0, 80)
    });
  });
  return out.slice(0, 40);
}
"""

# 默认脚本：从热点/搜索页抽取关联的爆款源视频（跳转链接 / 封面 / 作者 / 点赞）。
DEFAULT_VIDEO_JS = """
() => {
  const BASE = 'https://www.douyin.com';
  const out = [];
  const seen = new Set();
  // 统一补全 URL：协议相对(//) / 根相对(/) / 完整链接 均转为绝对地址。
  const abs = (u) => {
    if (!u) return '';
    u = String(u).trim();
    if (u.startsWith('//')) return 'https:' + u;
    if (/^https?:\\/\\//.test(u)) return u;
    if (u.startsWith('/')) return BASE + u;
    try { return new URL(u, location.origin).href; } catch (e) { return u; }
  };
  // 封面兜底：优先 src，其次懒加载 data-src / data-lazy-src / currentSrc。
  const coverOf = (a, card) => {
    const img = a.querySelector('img') || (card ? card.querySelector('img') : null);
    if (!img) return '';
    return abs(
      img.getAttribute('src') ||
      img.getAttribute('data-src') ||
      img.getAttribute('data-lazy-src') ||
      img.currentSrc ||
      ''
    );
  };
  document.querySelectorAll('a[href*="/video/"]').forEach(a => {
    const href = a.getAttribute('href') || '';
    if (!href || seen.has(href)) return;
    seen.add(href);
    const card = a.closest('div[class]') || a.parentElement;
    const text = (a.getAttribute('title') || a.innerText || '').replace(/\\s+/g, ' ').trim();
    const authorMatch = text.match(/@([^\\s·|]+)/);
    let likeMatch = text.match(/(\\d+(?:\\.\\d+)?万?)\\s*(?:点赞|赞|次播放)/);
    if (!likeMatch && card) {
      const likeEl = card.querySelector('[data-e2e*="like"], [class*="like"]');
      if (likeEl) likeMatch = (likeEl.innerText || '').match(/(\\d+(?:\\.\\d+)?万?)/);
    }
    out.push({
      video_url: abs(href),
      cover_url: coverOf(a, card),
      author_name: authorMatch ? authorMatch[1] : '',
      like_text: likeMatch ? likeMatch[1] : '',
      title: text.slice(0, 80)
    });
  });
  return out.slice(0, 30);
}
"""

# 默认脚本：从视频详情页抽取评论文本。
DEFAULT_COMMENT_JS = """
() => {
  const selectors = ['[data-e2e="comment-item"]', '.comment-item', 'div[class*="comment"]'];
  for (const sel of selectors) {
    const nodes = document.querySelectorAll(sel);
    if (!nodes.length) continue;
    return Array.from(nodes)
      .map(n => (n.innerText || '').trim())
      .filter(t => t.length > 1);
  }
  return [];
}
"""


class DouyinSource:
    """基于 Playwright 的抖音热榜采集源。"""

    name = "douyin"

    def __init__(
        self,
        *,
        headless: bool = True,
        storage_state: str | None = None,
        hot_url: str = DOUYIN_HOT_URL,
        nav_timeout_ms: int = 30000,
        scroll_times: int = 3,
        wait_after_nav_ms: int = 2500,
        hot_js: str = DEFAULT_HOT_JS,
        comment_js: str = DEFAULT_COMMENT_JS,
        video_js: str = DEFAULT_VIDEO_JS,
        top_video_js: str = DEFAULT_TOP_VIDEO_JS,
        user_agent: str | None = None,
    ) -> None:
        self.headless = headless
        self.storage_state = storage_state
        self.hot_url = hot_url
        self.nav_timeout_ms = nav_timeout_ms
        self.scroll_times = scroll_times
        self.wait_after_nav_ms = wait_after_nav_ms
        self.hot_js = hot_js
        self.comment_js = comment_js
        self.video_js = video_js
        self.top_video_js = top_video_js
        self.user_agent = user_agent

    # ---- 可选依赖 ----
    @staticmethod
    def _require_playwright() -> Any:
        try:
            from playwright.sync_api import sync_playwright  # type: ignore
        except ImportError as exc:  # pragma: no cover - 取决于本地环境
            raise FetchError(
                "未安装 Playwright。请执行：\n"
                "  pip install -r requirements-fetch.txt\n"
                "  python -m playwright install chromium"
            ) from exc
        return sync_playwright

    def _open_page(self, pw: Any) -> tuple[Any, Any, Any]:
        """启动浏览器并打开一个页面，返回 (browser, context, page)。"""
        browser = pw.chromium.launch(headless=self.headless)
        ctx_args: dict[str, Any] = {}
        if self.storage_state:
            ctx_args["storage_state"] = self.storage_state
        if self.user_agent:
            ctx_args["user_agent"] = self.user_agent
        context = browser.new_context(**ctx_args)
        page = context.new_page()
        page.set_default_timeout(self.nav_timeout_ms)
        return browser, context, page

    def _dismiss_login(self, page: Any) -> None:
        """尝试关闭登录弹窗（尽力而为，失败忽略）。"""
        for text in ("以后再说", "稍后再说", "关闭"):
            try:
                loc = page.get_by_text(text, exact=False)
                if loc.count() > 0:
                    loc.first.click(timeout=1500)
                    return
            except Exception:  # noqa: BLE001 - 弹窗处理属尽力而为
                continue

    # ---- 协议实现 ----
    def list_hotspots(self, limit: int = 20) -> list[Hotspot]:
        sync_playwright = self._require_playwright()
        hotspots: list[Hotspot] = []
        with sync_playwright() as pw:
            browser, _context, page = self._open_page(pw)
            try:
                page.goto(self.hot_url, wait_until="domcontentloaded")
                self._dismiss_login(page)
                page.wait_for_timeout(self.wait_after_nav_ms)
                for _ in range(max(0, self.scroll_times)):
                    page.mouse.wheel(0, 2000)
                    page.wait_for_timeout(800)
                raw_items = page.evaluate(self.hot_js) or []
                hotspots = self._extract_hotspots(raw_items)
                with_videos = sum(1 for hs in hotspots if hs.videos)
                logger.info(
                    "成功提取到 %d 条热点，其中 %d 条含视频链接/封面",
                    len(hotspots),
                    with_videos,
                )
            except FetchError:
                raise
            except Exception as exc:  # noqa: BLE001 - 统一转成 FetchError
                raise FetchError(f"抓取抖音热榜失败: {exc}") from exc
            finally:
                browser.close()

        return hotspots[:limit]

    def fetch_comments(self, hotspot: Hotspot, limit: int = 50) -> list[str]:
        if not hotspot.url:
            return []
        sync_playwright = self._require_playwright()
        comments: list[str] = []
        with sync_playwright() as pw:
            browser, _context, page = self._open_page(pw)
            try:
                page.goto(hotspot.url, wait_until="domcontentloaded")
                self._dismiss_login(page)
                page.wait_for_timeout(self.wait_after_nav_ms)
                for _ in range(max(1, self.scroll_times)):
                    page.mouse.wheel(0, 2000)
                    page.wait_for_timeout(800)
                raw_items = page.evaluate(self.comment_js) or []
                comments = self._extract_comments(raw_items)
            except FetchError:
                raise
            except Exception as exc:  # noqa: BLE001
                raise FetchError(f"抓取评论失败: {exc}") from exc
            finally:
                browser.close()

        return comments[:limit]

    def list_videos(self, hotspot: Hotspot, limit: int = 8) -> list[VideoItem]:
        """在热点页抓取关联的爆款源视频（封面 + 作者 + 点赞 + 跳转链接）。

        用于前端「封面卡片墙」：展示可一键直达的原始视频。
        """
        if not hotspot.url:
            return []
        sync_playwright = self._require_playwright()
        videos: list[VideoItem] = []
        with sync_playwright() as pw:
            browser, _context, page = self._open_page(pw)
            try:
                page.goto(hotspot.url, wait_until="domcontentloaded")
                self._dismiss_login(page)
                page.wait_for_timeout(self.wait_after_nav_ms)
                for _ in range(max(1, self.scroll_times)):
                    page.mouse.wheel(0, 2000)
                    page.wait_for_timeout(800)
                raw_items = page.evaluate(self.video_js) or []
                videos = self._extract_videos(raw_items)
                logger.info(f"成功提取到 {len(videos)} 个视频链接/封面")
            except FetchError:
                raise
            except Exception as exc:  # noqa: BLE001
                raise FetchError(f"抓取源视频失败: {exc}") from exc
            finally:
                browser.close()

        return videos[:limit]

    def list_top_videos(self, keyword: str, limit: int = 3) -> list[VideoItem]:
        """按「最多点赞」抓取某词条的 Top1~Top3 头部爆款视频。

        打开抖音搜索页的「视频 · 最多点赞」排序结果
        （``/search/{keyword}?type=video&sort_type=most_like``），
        解析点赞量最高的前 ``limit`` 条，用于前端「🔥 该热点最高热度/点赞爆款对标」。

        容错策略：排序页可能改版或被风控拦截，抓取/解析失败时返回空列表，
        由调用方使用搜索页直达链接兜底，不抛出异常中断分析流程。
        """
        search_url = douyin_search_url(keyword, sort_by_like=True)
        sync_playwright = self._require_playwright()
        videos: list[VideoItem] = []
        with sync_playwright() as pw:
            browser, _context, page = self._open_page(pw)
            try:
                page.goto(search_url, wait_until="domcontentloaded")
                self._dismiss_login(page)
                page.wait_for_timeout(self.wait_after_nav_ms)
                for _ in range(max(1, self.scroll_times)):
                    page.mouse.wheel(0, 2000)
                    page.wait_for_timeout(800)
                raw_items = page.evaluate(self.top_video_js) or []
                videos = self._extract_top_videos(raw_items, limit=limit)
                logger.info(
                    f"成功提取到 {len(videos)} 个视频链接/封面（搜索页按最多点赞排序）"
                )
            except FetchError:
                raise
            except Exception as exc:  # noqa: BLE001 - 排序页改版/风控时降级为兜底链接
                logger.warning(f"抓取『最多点赞』视频列表失败，将使用搜索页兜底：{exc}")
            finally:
                browser.close()

        return videos

    # ---- 解析（可被子类重写）----
    @staticmethod
    def _abs_url(url: str, base: str = "https://www.douyin.com") -> str:
        """把相对/协议相对链接补全为绝对 URL。"""
        text = str(url or "").strip()
        if not text:
            return ""
        if text.startswith("//"):
            return "https:" + text
        if text.startswith(("http://", "https://")):
            return text
        if text.startswith("/"):
            return base.rstrip("/") + text
        return text

    @staticmethod
    def _parse_like(value: Any) -> int:
        """把「1.2万」「3456 点赞」等文本解析为整数。"""
        text = str(value or "").strip()
        if not text:
            return 0
        match = re.match(r"(\d+(?:\.\d+)?)(万)?", text)
        if not match:
            return 0
        number = float(match.group(1))
        if match.group(2):
            number *= 10000
        return int(number)

    def _extract_top_videos(self, raw_items: list[Any], limit: int = 3) -> list[VideoItem]:
        """解析搜索页视频卡片并按点赞量降序取 Top N。

        采用稳定排序：点赞量相同（或均缺失）时保留页面原始顺序，
        即抖音「按最多点赞」结果本身的排序，避免破坏平台热度信号。
        """
        videos = self._extract_videos(raw_items)
        ordered = sorted(videos, key=lambda v: v.like_count, reverse=True)
        return ordered[:limit]

    def _extract_videos(self, raw_items: list[Any]) -> list[VideoItem]:
        out: list[VideoItem] = []
        for item in raw_items or []:
            if not isinstance(item, dict):
                continue
            video_url = self._abs_url(str(item.get("video_url", "") or ""))
            if not video_url:
                continue
            like_raw = item.get("like_text", "") or item.get("like_count", 0)
            out.append(
                VideoItem(
                    video_url=video_url,
                    cover_url=self._abs_url(str(item.get("cover_url", "") or "")),
                    author_name=str(item.get("author_name", "") or ""),
                    like_count=self._parse_like(like_raw),
                    title=str(item.get("title", "") or ""),
                )
            )
        return out
    @staticmethod
    def _clean_title(title: str) -> str:
        """清理标题噪声：时长前缀、『热点：』前缀、热度与时间后缀。"""
        import re

        text = str(title or "").replace("\n", " ").strip()
        # 去掉「热点：」前缀，保留真正词条
        if "热点：" in text:
            text = text.split("热点：", 1)[1]
        # 去掉开头「时长 + 点赞/播放数」组合，如 00:211796
        text = re.sub(r"^\d{1,2}:\d{2}\s*\d*\s*", "", text)
        # 去掉「145.3万人在看」热度描述
        text = re.sub(r"\d+(?:\.\d+)?万?人在看", "", text)
        # 去掉结尾「· 3天前」等时间戳
        text = re.sub(r"[·•]\s*\d+\s*(?:秒|分钟|小时|天|周|个月|年)前.*$", "", text)
        # 去掉话题标签与 @作者 之后的内容
        text = re.split(r"[#@]", text, maxsplit=1)[0]
        return " ".join(text.split()).strip(" ·•-")

    def _extract_hotspots(self, raw_items: list[Any]) -> list[Hotspot]:
        out: list[Hotspot] = []
        for idx, item in enumerate(raw_items, start=1):
            if not isinstance(item, dict):
                continue
            title = self._clean_title(str(item.get("title", "") or ""))
            if not title:
                continue
            hot_value = item.get("hot_value", 0)
            try:
                hot_value = int(hot_value)
            except (TypeError, ValueError):
                hot_value = 0
            url = self._abs_url(str(item.get("url", "") or ""))
            cover = self._abs_url(str(item.get("cover", "") or ""))
            videos = self._extract_videos(item.get("videos") or [])
            if not videos:
                # 防空兜底：未解析出具体视频时，用抖音搜索页直达该热点实时视频，
                # 保证前端「关联热点视频与溯源」区块始终有可跳转的链接。
                videos = [
                    VideoItem(
                        video_url=douyin_search_url(title),
                        cover_url=cover,
                        title=title,
                    )
                ]
                logger.info(
                    f"成功提取到 {len(videos)} 个视频链接/封面（已使用抖音搜索页兜底）"
                )
            out.append(
                Hotspot(
                    rank=int(item.get("rank", idx) or idx),
                    title=title,
                    hot_value=hot_value,
                    url=url,
                    cover=cover,
                    source=self.name,
                    videos=videos,
                    raw=item,
                )
            )
        return out

    def _extract_comments(self, raw_items: list[Any]) -> list[str]:
        out: list[str] = []
        for item in raw_items:
            if isinstance(item, dict):
                text = str(item.get("text", "") or item.get("content", "") or "").strip()
            else:
                text = str(item or "").strip()
            if text:
                out.append(text)
        return out


def parse_embedded_json(html: str) -> list[dict[str, Any]]:  # pragma: no cover
    """辅助函数：从页面内联 JSON（如 `_ROUTER_DATA`）解析热榜数据。"""
    marker = "window._ROUTER_DATA"
    idx = html.find(marker)
    if idx == -1:
        return []
    start = html.find("{", idx)
    if start == -1:
        return []
    depth = 0
    for pos in range(start, len(html)):
        ch = html[pos]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(html[start : pos + 1])
                except json.JSONDecodeError:
                    return []
    return []
