"""结构化日志：控制台 + 轮转文件，记录请求、修复重试与成本。

用法：
    from hotspot_analysis.logging_config import get_logger, setup_logging
    setup_logging()
    logger = get_logger(__name__)
"""

from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Optional

from hotspot_analysis.config import PROJECT_ROOT

_CONFIGURED = False

_LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class JsonLineFormatter(logging.Formatter):
    """把日志附加字段序列化为 JSON，便于机器解析。"""

    def format(self, record: logging.LogRecord) -> str:
        base = {
            "time": self.formatTime(record, _DATE_FORMAT),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        extra = getattr(record, "extra_fields", None)
        if isinstance(extra, dict):
            base.update(extra)
        if record.exc_info:
            base["exc"] = self.formatException(record.exc_info)
        return json.dumps(base, ensure_ascii=False)


def setup_logging(
    level: str = "INFO",
    log_dir: str = "logs",
    filename: str = "hotspot_analysis.log",
) -> None:
    """初始化根日志器：控制台（简洁）+ 文件（JSON 行）。

    幂等：重复调用只生效一次（除非尚未配置）。
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    root = logging.getLogger("hotspot_analysis")
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.propagate = False

    if not root.handlers:
        # 控制台
        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))
        root.addHandler(console)

        # 文件（轮转，单个 5MB，保留 3 份）
        try:
            log_path = Path(log_dir)
            if not log_path.is_absolute():
                log_path = PROJECT_ROOT / log_path
            log_path.mkdir(parents=True, exist_ok=True)
            file_handler = RotatingFileHandler(
                log_path / filename,
                maxBytes=5 * 1024 * 1024,
                backupCount=3,
                encoding="utf-8",
            )
            file_handler.setFormatter(JsonLineFormatter())
            root.addHandler(file_handler)
        except OSError:  # pragma: no cover - 磁盘不可写时降级为仅控制台
            root.warning("无法创建日志文件，降级为仅控制台输出。")

    _CONFIGURED = True


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """获取子日志器。"""
    if not _CONFIGURED:
        setup_logging()
    return logging.getLogger(name or "hotspot_analysis")


def log_event(logger: logging.Logger, message: str, **fields: Any) -> None:
    """输出带结构化字段的 INFO 日志。"""
    logger.info(message, extra={"extra_fields": fields})
