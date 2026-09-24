"""数据模型：热点分析报告的结构化定义（Pydantic v2）。

报告严格对应「四步分析逻辑」：
  1. NoiseFiltering    噪声过滤
  2. EmotionDecoding   情绪解构
  3. ViralMechanism    传播引爆点
  4. ActionableInsight 行动落地（2-3 条）
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

STEP_STATUS_SKIPPED = "skipped"


class NoiseType(str, Enum):
    """噪声类型枚举。"""

    GOVERNMENT_NOTICE = "政务通报"
    CELEBRITY_GOSSIP = "低质明星八卦"
    WATER_ARMY_MARKETING = "纯水军营销"
    SUDDEN_ACCIDENT = "突发事故"
    OTHER_NOISE = "其他噪声"
    VALUABLE = "有效话题"


class NoiseFiltering(BaseModel):
    """Step 1：噪声过滤。"""

    is_valuable_trend: bool = Field(..., description="是否为可二次创作的优质话题")
    noise_type: NoiseType = Field(..., description="话题分类")
    noise_reason: str = Field(..., description="判定原因，需给出可观测依据")
    value_score: int = Field(..., ge=0, le=100, description="内容价值评分 0-100")
    is_noise: bool = Field(default=False, description="是否为需剔除的噪声")

    @field_validator("is_noise", mode="before")
    @classmethod
    def _default_is_noise(cls, v: object, info) -> bool:  # noqa: ANN001
        if v is None:
            return False
        return bool(v)


class RiskLevel(str, Enum):
    """品牌合规风险等级。"""

    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    BAN = "Ban"


_RISK_ALIASES = {
    "low": RiskLevel.LOW,
    "低": RiskLevel.LOW,
    "低风险": RiskLevel.LOW,
    "安全": RiskLevel.LOW,
    "medium": RiskLevel.MEDIUM,
    "中": RiskLevel.MEDIUM,
    "中风险": RiskLevel.MEDIUM,
    "警告": RiskLevel.MEDIUM,
    "high": RiskLevel.HIGH,
    "高": RiskLevel.HIGH,
    "高风险": RiskLevel.HIGH,
    "ban": RiskLevel.BAN,
    "封禁": RiskLevel.BAN,
    "违禁": RiskLevel.BAN,
    "禁止": RiskLevel.BAN,
}


class RiskControl(BaseModel):
    """品牌合规与广告法风控评估（Step 0：发布前风险体检）。"""

    risk_level: RiskLevel = Field(
        default=RiskLevel.LOW, description="风险等级：Low / Medium / High / Ban"
    )
    sensitive_words_found: list[str] = Field(
        default_factory=list, description="命中的广告法敏感词 / 极限词 / 违禁表述"
    )
    compliance_suggestions: str = Field(
        default="", description="合规替换与规避建议（可直接替换的话术）"
    )

    @field_validator("risk_level", mode="before")
    @classmethod
    def _normalize_level(cls, v: Any) -> Any:  # noqa: ANN401
        if isinstance(v, str):
            key = v.strip().lower()
            if key in _RISK_ALIASES:
                return _RISK_ALIASES[key]
            for alias, level in _RISK_ALIASES.items():
                if alias in key:
                    return level
        return v

    @field_validator("sensitive_words_found", mode="before")
    @classmethod
    def _coerce_words(cls, v: Any) -> Any:  # noqa: ANN401
        """模型有时返回逗号分隔字符串，统一归一为 list[str]。"""
        if isinstance(v, str):
            return [w.strip() for w in re.split(r"[、,，;；\n]+", v) if w.strip()]
        if isinstance(v, (list, tuple)):
            return [str(w).strip() for w in v if str(w).strip()]
        return v

    @field_validator("compliance_suggestions", mode="before")
    @classmethod
    def _coerce_suggestions(cls, v: Any) -> Any:  # noqa: ANN401
        """模型有时返回字符串列表，统一拼接为单段文本（避免校验失败触发修复重试）。"""
        if isinstance(v, (list, tuple)):
            return "；".join(str(x).strip() for x in v if str(x).strip())
        return v

    @property
    def is_blocking(self) -> bool:
        """高风险 / 封禁级别需要发布前先整改。"""
        return self.risk_level in {RiskLevel.HIGH, RiskLevel.BAN}


class EmotionDecoding(BaseModel):
    """Step 2：心理与情绪解构。"""

    status: str = Field(default="done", description="done 或 skipped（噪声话题）")
    pain_points: list[str] = Field(default_factory=list, description="戳中的大众痛点")
    core_emotions: list[str] = Field(default_factory=list, description="核心情绪标签")
    collective_unconscious: list[str] = Field(
        default_factory=list, description="集体无意识 / 群体心理（对立站队、玩梗狂欢等）"
    )
    emotion_intensity: int = Field(
        default=0, ge=0, le=100, description="情绪强度 0-100"
    )
    top_controversies: list[str] = Field(
        default_factory=list,
        description="评论区 TOP3 核心争议 / 负面声音标签（反驳、质疑、骂声）",
    )
    pitfall_warnings: list[str] = Field(
        default_factory=list,
        description="拍摄避坑雷区预警（易引发反噬的表述 / 观点 / 画面）",
    )
    summary: str = Field(default="", description="情绪层面一句话总结")


class ViralMechanism(BaseModel):
    """Step 3：传播引爆点。"""

    status: str = Field(default="done", description="done 或 skipped")
    triggers: list[str] = Field(default_factory=list, description="引爆因子")
    visual_conflict: str = Field(default="", description="强视觉冲突描述（若有）")
    controversy_level: int = Field(
        default=0, ge=0, le=100, description="争议指数 0-100"
    )
    rarity: str = Field(default="", description="信息稀缺度 / 稀缺爆料说明")
    secondary_creation_potential: str = Field(
        default="", description="二次创作潜力（模板化、可复制性）"
    )
    summary: str = Field(default="", description="传播机制一句话总结")


class HookOption(BaseModel):
    """一套黄金 3 秒 Hook 方案（用于 A/B 测试矩阵）。"""

    style: str = Field(
        ..., description="Hook 风格：冲突对立型 / 悬念好奇型 / 情绪共鸣型"
    )
    script: str = Field(..., description="可直接念出的前 3 秒钩子话术")
    target_persona: str = Field(default="", description="这套 Hook 主打的人群画像")

    @model_validator(mode="before")
    @classmethod
    def _coerce_plain_string(cls, data: Any) -> Any:  # noqa: ANN401
        """兼容模型直接返回纯字符串（视为 script，风格留空）。"""
        if isinstance(data, str):
            return {"style": "", "script": data}
        return data


class ActionableInsight(BaseModel):
    """Step 4：可执行切入点。"""

    angle_title: str = Field(..., description="切入角度标题")
    target_audience: str = Field(default="", description="目标人群")
    golden_hooks: list[HookOption] = Field(
        default_factory=list,
        description="3 套不同风格的黄金 3 秒 Hook（冲突 / 悬念 / 共鸣），供 A/B 测试",
    )
    content_outline: list[str] = Field(
        default_factory=list, description="内容分镜提纲"
    )
    execution_steps: list[str] = Field(
        default_factory=list, description="可执行步骤"
    )
    engagement_trigger: str = Field(
        default="",
        description="评论区互动引导点（结尾提问 / 置顶评论 / 二选一站队）",
    )
    monetization: str = Field(default="", description="变现 / 引流路径")
    risk_notes: str = Field(default="", description="合规与蹭热点风险提示")
    mainstream_angles: list[str] = Field(
        default_factory=list,
        description="当前同质化 / 红海常规切入角度（大家都这么拍的套路）",
    )
    differentiated_angle: str = Field(
        default="",
        description="蓝海 / 反常识的差异化切入视角（人无我有的独特提案）",
    )

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_hook(cls, data: Any) -> Any:  # noqa: ANN401
        """兼容旧字段 hook（单句 str）：自动包装为单套 golden_hooks。"""
        if isinstance(data, dict):
            legacy = data.get("hook")
            has_hooks = bool(data.get("golden_hooks"))
            if legacy and not has_hooks:
                data = dict(data)
                data["golden_hooks"] = [
                    {
                        "style": "情绪共鸣型",
                        "script": str(legacy),
                        "target_persona": str(data.get("target_audience", "") or ""),
                    }
                ]
        return data

    @property
    def hook(self) -> str:
        """首套 Hook 话术（向后兼容旧字段 hook 的读取）。"""
        return self.golden_hooks[0].script if self.golden_hooks else ""

    def hook_by_style(self, style_keyword: str) -> str:
        """按风格关键字（如「冲突」「悬念」「共鸣」）取对应 Hook 话术。"""
        for opt in self.golden_hooks:
            if style_keyword in opt.style:
                return opt.script
        return ""


class AnalysisMeta(BaseModel):
    """元信息：模型、耗时、token 用量等。"""

    keyword: str = Field(..., description="热点词条")
    model: str = Field(default="", description="使用的模型名")
    base_url: str = Field(default="", description="接口地址")
    created_at: str = Field(default="", description="生成时间 ISO8601")
    elapsed_seconds: float = Field(default=0.0, description="端到端耗时（秒）")
    latency_ms: int = Field(default=0, description="单次 API 耗时（毫秒）")
    prompt_tokens: int = Field(default=0, description="提示 token 数")
    completion_tokens: int = Field(default=0, description="补全 token 数")
    total_tokens: int = Field(default=0, description="总 token 数")
    total_cost_usd: float = Field(default=0.0, description="预估成本（美元）")
    repair_attempts: int = Field(default=0, description="JSON 修复重试次数")
    mock: bool = Field(default=False, description="是否为 Mock 模式产出")
    raw_text_chars: int = Field(default=0, description="预处理后输入字符数")
    raw_text_truncated: bool = Field(default=False, description="输入是否被截断")
    deduped_lines: int = Field(default=0, description="去除的重复评论条数")


class TrendReport(BaseModel):
    """完整分析报告（四步 + 风控 + 元信息）。"""

    meta: AnalysisMeta
    noise_filtering: NoiseFiltering
    emotion_decoding: EmotionDecoding
    viral_mechanism: ViralMechanism
    actionable_insights: list[ActionableInsight] = Field(default_factory=list)
    risk_control: RiskControl = Field(
        default_factory=RiskControl, description="品牌合规与风控评估"
    )
    conclusion: str = Field(default="", description="给创作者的一句话决策建议")

    @field_validator("actionable_insights")
    @classmethod
    def _limit_insights(cls, v: list[ActionableInsight]) -> list[ActionableInsight]:
        # 承诺 2-3 条；若模型多给则截断，少给则保留（宽松处理）
        return v[:3]

    @property
    def is_valuable(self) -> bool:
        return self.noise_filtering.is_valuable_trend
