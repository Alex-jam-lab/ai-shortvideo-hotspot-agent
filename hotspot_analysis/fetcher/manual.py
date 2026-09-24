"""手动 / 文件数据源：把用户提供的词条与评论文本包装成 HotspotSource。

主要用于把「已有数据」纳入统一的采集-分析流水线（例如批量 JSON 文件），
也作为测试与其他数据源的参考实现。
"""

from __future__ import annotations

import json
from pathlib import Path

from hotspot_analysis.fetcher.base import FetchError, Hotspot


class ManualSource:
    """手工输入或文件输入的数据源。"""

    name = "manual"

    def __init__(self, items: list[dict[str, str]] | None = None) -> None:
        self._items: list[dict[str, str]] = []
        for item in items or []:
            keyword = str(item.get("keyword", "") or "").strip()
            if not keyword:
                continue
            self._items.append(
                {"keyword": keyword, "raw_text": str(item.get("raw_text", "") or "")}
            )

    @classmethod
    def from_file(cls, path: str | Path) -> "ManualSource":
        """从 JSON 文件读取（支持单条对象或对象数组）。"""
        p = Path(path)
        if not p.exists():
            raise FetchError(f"输入文件不存在: {p}")
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise FetchError(f"读取输入文件失败: {exc}") from exc

        if isinstance(data, dict):
            items = [data]
        elif isinstance(data, list):
            items = [d for d in data if isinstance(d, dict)]
        else:
            raise FetchError("输入文件必须是对象或对象数组。")
        return cls(items)

    def list_hotspots(self, limit: int = 20) -> list[Hotspot]:
        out: list[Hotspot] = []
        for idx, item in enumerate(self._items[:limit], start=1):
            out.append(
                Hotspot(rank=idx, title=item["keyword"], source=self.name, raw=dict(item))
            )
        return out

    def fetch_comments(self, hotspot: Hotspot, limit: int = 50) -> list[str]:
        text = str(hotspot.raw.get("raw_text", "") or "")
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        return lines[:limit]
