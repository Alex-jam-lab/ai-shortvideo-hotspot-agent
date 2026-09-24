"""分析器：调用 OpenAI 兼容接口，产出校验通过的 TrendReport。

关键能力：
- 模型无关：使用 settings.base_url / model
- 输入预处理：清洗、去重、按信息密度截断（见 preprocess.py）
- 强 JSON 约束：优先 response_format=json_object；不支持时降级
- 解析容错：剥离 ```json 代码块、截取首尾大括号
- 自动修复：解析/校验失败时带错误信息重试（次数由配置控制）
- Mock 模式：MOCK_MODE=True 时不发起请求，读取 examples/sample_output.json
- 结构化日志：记录每次请求、修复重试、耗时与 Token 成本
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from hotspot_analysis.config import PROJECT_ROOT, Settings, load_settings
from hotspot_analysis.logging_config import get_logger, log_event, setup_logging
from hotspot_analysis.models import TrendReport
from hotspot_analysis.preprocess import PreprocessResult, preprocess_raw_text
from hotspot_analysis.prompts import (
    SYSTEM_PROMPT,
    build_fewshot_messages,
    build_repair_prompt,
    build_user_prompt,
)

try:  # 延迟导入，方便测试时 mock
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None  # type: ignore[assignment]


class AnalyzerError(RuntimeError):
    """分析过程不可恢复的错误。"""


_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)

DEFAULT_MOCK_FILE = PROJECT_ROOT / "examples" / "sample_output.json"


def _extract_json(text: str) -> str:
    """从模型输出中提取 JSON 字符串。"""
    if not text:
        raise AnalyzerError("模型返回为空。")

    cleaned = text.strip()

    # 1) 优先取代码块内容
    fence = _CODE_FENCE_RE.search(cleaned)
    if fence:
        cleaned = fence.group(1).strip()

    # 2) 截取第一个 { 到最后一个 }
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        cleaned = cleaned[start : end + 1]

    return cleaned.strip()


def _build_meta(
    keyword: str,
    settings: Settings,
    *,
    elapsed: float,
    latency_ms: int,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    repair_attempts: int,
    mock: bool,
    pre: PreprocessResult,
) -> dict[str, Any]:
    """构造 meta 字典（唯一事实来源）。"""
    return {
        "keyword": keyword,
        "model": settings.model,
        "base_url": settings.base_url,
        "created_at": datetime.now(timezone.utc).astimezone().isoformat(
            timespec="seconds"
        ),
        "elapsed_seconds": round(elapsed, 3),
        "latency_ms": latency_ms,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "total_cost_usd": settings.estimate_cost(prompt_tokens, completion_tokens),
        "repair_attempts": repair_attempts,
        "mock": mock,
        "raw_text_chars": pre.cleaned_chars,
        "raw_text_truncated": pre.truncated,
        "deduped_lines": pre.deduped_lines,
    }


def _parse_report(
    raw: str,
    keyword: str,
    settings: Settings,
    *,
    elapsed: float,
    latency_ms: int,
    usage: Optional[Any],
    repair_attempts: int,
    mock: bool,
    pre: PreprocessResult,
) -> TrendReport:
    """把模型原始输出解析为 TrendReport，并回填 meta。"""
    payload_text = _extract_json(raw)
    try:
        data: dict[str, Any] = json.loads(payload_text)
    except json.JSONDecodeError as exc:
        raise AnalyzerError(f"JSON 解析失败: {exc}") from exc

    prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
    completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
    total_tokens = int(getattr(usage, "total_tokens", 0) or 0)

    # meta 一律由程序回填，丢弃模型自产内容
    data["meta"] = _build_meta(
        keyword,
        settings,
        elapsed=elapsed,
        latency_ms=latency_ms,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        repair_attempts=repair_attempts,
        mock=mock,
        pre=pre,
    )

    try:
        return TrendReport.model_validate(data)
    except Exception as exc:  # pydantic ValidationError
        raise AnalyzerError(f"字段校验失败: {exc}") from exc


class HotspotAnalyzer:
    """热点分析器。"""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or load_settings()
        self._client: Optional[Any] = None
        setup_logging(level=self.settings.log_level, log_dir=self.settings.log_dir)
        self.logger = get_logger("hotspot_analysis.analyzer")

    # ---- 内部：客户端与请求 ----
    def _get_client(self) -> Any:
        if OpenAI is None:
            raise AnalyzerError(
                "未安装 openai 依赖，请先执行 `pip install -r requirements.txt`。"
            )
        if self._client is None:
            self.settings.require_api_key()
            self._client = OpenAI(
                base_url=self.settings.base_url,
                api_key=self.settings.api_key,
                timeout=self.settings.timeout,
                max_retries=0,  # 重试由本模块自行控制，避免叠加
            )
        return self._client

    def _chat(self, messages: list[dict[str, str]], use_json_mode: bool) -> Any:
        client = self._get_client()
        kwargs: dict[str, Any] = {
            "model": self.settings.model,
            "messages": messages,
            "temperature": self.settings.temperature,
        }
        if use_json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        try:
            return client.chat.completions.create(**kwargs)
        except Exception as exc:  # 部分模型不支持 json_object，降级重试一次
            if use_json_mode and _is_json_mode_unsupported(exc):
                log_event(
                    self.logger,
                    "模型不支持 json_object，降级为普通模式",
                    event="json_mode_fallback",
                    model=self.settings.model,
                )
                kwargs.pop("response_format", None)
                return client.chat.completions.create(**kwargs)
            raise AnalyzerError(f"接口调用失败: {exc}") from exc

    # ---- 公共 API ----
    def analyze(self, keyword: str, raw_text: str) -> TrendReport:
        """执行完整分析流程，返回校验通过的 TrendReport。"""
        if not keyword or not keyword.strip():
            raise AnalyzerError("keyword 不能为空。")

        started = time.perf_counter()

        # 1) 输入预处理
        pre = preprocess_raw_text(
            raw_text, max_chars=self.settings.max_raw_text_chars
        )
        preview = pre.text[:60].replace("\n", " ")
        log_event(
            self.logger,
            "开始分析",
            event="analyze_start",
            keyword=keyword,
            mock=self.settings.mock_mode,
            model=self.settings.model,
            raw_chars=pre.original_chars,
            cleaned_chars=pre.cleaned_chars,
            kept_lines=pre.kept_lines,
            deduped_lines=pre.deduped_lines,
            truncated=pre.truncated,
            notes="; ".join(pre.notes),
        )

        # 2) Mock 模式：不发起请求
        if self.settings.mock_mode:
            report = self._mock_report(keyword, pre, started)
            log_event(
                self.logger,
                "Mock 分析完成",
                event="analyze_done",
                keyword=keyword,
                mock=True,
                valuable=report.is_valuable,
                value_score=report.noise_filtering.value_score,
                elapsed_seconds=report.meta.elapsed_seconds,
            )
            return report

        # 3) 真实调用
        return self._analyze_live(keyword, pre, started)

    def analyze_to_dict(self, keyword: str, raw_text: str) -> dict[str, Any]:
        """便捷方法：返回可序列化字典。"""
        report = self.analyze(keyword, raw_text)
        return report.model_dump(mode="json")

    # ---- 内部：Mock ----
    def _mock_report(
        self, keyword: str, pre: PreprocessResult, started: float
    ) -> TrendReport:
        mock_file = self.settings.mock_file or str(DEFAULT_MOCK_FILE)
        path = Path(mock_file)
        if not path.exists():
            raise AnalyzerError(f"Mock 数据文件不存在: {path}")

        data = json.loads(path.read_text(encoding="utf-8"))
        data["meta"] = _build_meta(
            keyword,
            self.settings,
            elapsed=time.perf_counter() - started,
            latency_ms=0,
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            repair_attempts=0,
            mock=True,
            pre=pre,
        )
        try:
            return TrendReport.model_validate(data)
        except Exception as exc:
            raise AnalyzerError(f"Mock 数据校验失败: {exc}") from exc

    # ---- 内部：真实调用流程 ----
    def _analyze_live(
        self, keyword: str, pre: PreprocessResult, started: float
    ) -> TrendReport:
        use_json_mode = self.settings.use_json_mode
        messages = self._build_messages(keyword, pre.text)
        last_error: Optional[str] = None

        for attempt in range(self.settings.max_retries + 1):
            call_started = time.perf_counter()
            completion = self._chat(messages, use_json_mode)
            latency_ms = int((time.perf_counter() - call_started) * 1000)
            raw = _choice_text(completion)
            usage = getattr(completion, "usage", None)

            log_event(
                self.logger,
                "完成一次模型调用",
                event="llm_call",
                keyword=keyword,
                attempt=attempt,
                latency_ms=latency_ms,
                prompt_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
                completion_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
            )

            try:
                elapsed = time.perf_counter() - started
                report = _parse_report(
                    raw=raw,
                    keyword=keyword,
                    settings=self.settings,
                    elapsed=elapsed,
                    latency_ms=latency_ms,
                    usage=usage,
                    repair_attempts=attempt,
                    mock=False,
                    pre=pre,
                )
                log_event(
                    self.logger,
                    "分析完成",
                    event="analyze_done",
                    keyword=keyword,
                    mock=False,
                    valuable=report.is_valuable,
                    value_score=report.noise_filtering.value_score,
                    elapsed_seconds=report.meta.elapsed_seconds,
                    latency_ms=latency_ms,
                    total_tokens=report.meta.total_tokens,
                    total_cost_usd=report.meta.total_cost_usd,
                    repair_attempts=attempt,
                )
                return report
            except AnalyzerError as exc:
                last_error = str(exc)
                log_event(
                    self.logger,
                    "解析/校验失败，准备修复重试",
                    event="analyze_retry",
                    keyword=keyword,
                    attempt=attempt,
                    error=last_error,
                )
                if attempt >= self.settings.max_retries:
                    break
                messages = messages[:2] + [
                    {"role": "assistant", "content": raw},
                    {"role": "user", "content": build_repair_prompt(raw, last_error)},
                ]

        self.logger.error(
            "分析最终失败 keyword=%s error=%s", keyword, last_error
        )
        raise AnalyzerError(
            f"分析失败：经过 {self.settings.max_retries + 1} 次尝试仍无法得到合法结果。"
            f"最后错误：{last_error}"
        )

    # ---- 内部：消息组装 ----
    def _build_messages(self, keyword: str, raw_text: str) -> list[dict[str, str]]:
        """System + Few-Shot 示例 + 实际用户输入。"""
        return [
            {"role": "system", "content": SYSTEM_PROMPT},
            *build_fewshot_messages(),
            {"role": "user", "content": build_user_prompt(keyword, raw_text)},
        ]


def _choice_text(completion: Any) -> str:
    """安全提取 completion 文本。"""
    try:
        return completion.choices[0].message.content or ""
    except (AttributeError, IndexError, TypeError) as exc:
        raise AnalyzerError(f"无法解析模型响应结构: {exc}") from exc


def _is_json_mode_unsupported(exc: Exception) -> bool:
    """判断异常是否为「模型不支持 response_format=json_object」。"""
    msg = str(exc).lower()
    keywords = [
        "response_format",
        "json_object",
        "not supported",
        "unsupported",
        "invalid_request_error",
    ]
    return any(k in msg for k in keywords)


# 便于直接运行：python -m hotspot_analysis.analyzer
if __name__ == "__main__":  # pragma: no cover
    import sys

    if len(sys.argv) < 3:
        print("用法: python -m hotspot_analysis.analyzer <keyword> <raw_text>")
        raise SystemExit(1)

    _kw = sys.argv[1]
    _txt = " ".join(sys.argv[2:])
    _report = HotspotAnalyzer().analyze(_kw, _txt)
    print(_report.model_dump_json(indent=2, ensure_ascii=False))
