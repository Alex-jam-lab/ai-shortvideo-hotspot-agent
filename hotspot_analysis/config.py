"""配置模块：从环境变量 / .env 读取大模型与运行参数。

全部配置走环境变量，实现「模型无关」——切换 DeepSeek / 通义 / Kimi
只需改 .env，无需改动任何代码。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:  # python-dotenv 为可选依赖，缺失时仍可用系统环境变量
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None  # type: ignore[assignment]


# 项目根目录（本文件位于 hotspot_analysis/ 下）
PROJECT_ROOT = Path(__file__).resolve().parent.parent


class ConfigError(RuntimeError):
    """配置缺失或非法时抛出。"""


def _load_env() -> None:
    """加载项目根目录下的 .env（若存在）。"""
    if load_dotenv is None:
        return
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=False)


def _get_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _get_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigError(f"环境变量 {name} 必须为数字，当前值: {raw!r}") from exc


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"环境变量 {name} 必须为整数，当前值: {raw!r}") from exc


@dataclass(frozen=True)
class Settings:
    """运行时配置。"""

    base_url: str
    api_key: str
    model: str
    temperature: float
    timeout: float
    max_retries: int
    use_json_mode: bool
    mock_mode: bool = False
    mock_file: str = ""
    max_raw_text_chars: int = 3000
    log_level: str = "INFO"
    log_dir: str = "logs"
    price_input_per_1m: float = 0.0
    price_output_per_1m: float = 0.0

    def estimate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        """按模型单价估算本次调用成本（美元）。

        单价单位：美元 / 百万 token。未配置单价时返回 0.0。
        """
        cost = (
            prompt_tokens / 1_000_000 * self.price_input_per_1m
            + completion_tokens / 1_000_000 * self.price_output_per_1m
        )
        return round(cost, 6)

    def require_api_key(self) -> None:
        """在真正调用接口前校验 API Key。"""
        if not self.api_key or self.api_key.startswith("sk-your-key"):
            raise ConfigError(
                "未检测到有效的 OPENAI_API_KEY。\n"
                "请将 .env.example 复制为 .env，并填入真实 Key，"
                "或通过环境变量 OPENAI_API_KEY 指定。"
            )

    def masked(self) -> dict[str, object]:
        """返回可用于日志/输出的脱敏配置。"""
        key = self.api_key or ""
        masked_key = (key[:6] + "..." + key[-4:]) if len(key) > 12 else "***"
        return {
            "base_url": self.base_url,
            "model": self.model,
            "temperature": self.temperature,
            "timeout": self.timeout,
            "max_retries": self.max_retries,
            "use_json_mode": self.use_json_mode,
            "mock_mode": self.mock_mode,
            "mock_file": self.mock_file or "(默认 examples/sample_output.json)",
            "max_raw_text_chars": self.max_raw_text_chars,
            "log_level": self.log_level,
            "log_dir": self.log_dir,
            "api_key": masked_key,
        }


# 常见厂商默认地址，便于快速切换
KNOWN_PROVIDERS: dict[str, str] = {
    "deepseek": "https://api.deepseek.com/v1",
    "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "kimi": "https://api.moonshot.cn/v1",
    "openai": "https://api.openai.com/v1",
}

# 模型单价表（美元 / 百万 token），格式：(输入价, 输出价)
# 仅用于成本「预估」，请以厂商最新定价为准。
KNOWN_PRICES: dict[str, tuple[float, float]] = {
    "deepseek-flash": (0.10, 0.30),
    "deepseek-v4-pro": (0.55, 2.19),
    "deepseek-chat": (0.27, 1.10),
    "deepseek-reasoner": (0.55, 2.19),
    "qwen-plus": (0.40, 1.20),
    "moonshot-v1-8k": (1.68, 1.68),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
}


def resolve_price(model: str) -> tuple[float, float]:
    """按模型名解析单价；未知模型返回 (0.0, 0.0)。"""
    if model in KNOWN_PRICES:
        return KNOWN_PRICES[model]
    # 前缀匹配，兼容带日期后缀的模型名
    for name, price in KNOWN_PRICES.items():
        if model.startswith(name):
            return price
    return (0.0, 0.0)


def load_settings() -> Settings:
    """从环境变量加载配置。"""
    _load_env()

    base_url = os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com/v1").strip()
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    model = os.getenv("OPENAI_MODEL", "deepseek-chat").strip()

    default_in, default_out = resolve_price(model)
    price_in = _get_float("OPENAI_PRICE_INPUT_PER_1M", default_in)
    price_out = _get_float("OPENAI_PRICE_OUTPUT_PER_1M", default_out)

    return Settings(
        base_url=base_url,
        api_key=api_key,
        model=model,
        temperature=_get_float("OPENAI_TEMPERATURE", 0.3),
        timeout=_get_float("OPENAI_TIMEOUT", 90.0),
        max_retries=_get_int("OPENAI_MAX_RETRIES", 1),
        use_json_mode=_get_bool("OPENAI_USE_JSON_MODE", True),
        mock_mode=_get_bool("MOCK_MODE", False),
        mock_file=os.getenv("MOCK_FILE", "").strip(),
        max_raw_text_chars=_get_int("MAX_RAW_TEXT_CHARS", 3000),
        log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper(),
        log_dir=os.getenv("LOG_DIR", "logs").strip(),
        price_input_per_1m=price_in,
        price_output_per_1m=price_out,
    )
