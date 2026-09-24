"""数据模型：热点分析报告的结构化定义（Pydantic v2）。

报告严格对应「四步分析逻辑」：
  1. NoiseFiltering    噪声过滤
  2. EmotionDecoding   情绪解构
  3. ViralMechanism    传播引爆点
  4. ActionableInsight 行动落地（2-3 条）
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator

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


class ActionableInsight(BaseModel):
    """Step 4：可执行切入点。"""

    angle_title: str = Field(..., description="切入角度标题")
    target_audience: str = Field(default="", description="目标人群")
    hook: str = Field(default="", description="前 3 秒钩子话术")
    content_outline: list[str] = Field(
        default_factory=list, description="内容分镜提纲"
    )
    execution_steps: list[str] = Field(
        default_factory=list, description="可执行步骤"
    )
    monetization: str = Field(default="", description="变现 / 引流路径")
    risk_notes: str = Field(default="", description="合规与蹭热点风险提示")


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
    """完整分析报告（四步 + 元信息）。"""

    meta: AnalysisMeta
    noise_filtering: NoiseFiltering
    emotion_decoding: EmotionDecoding
    viral_mechanism: ViralMechanism
    actionable_insights: list[ActionableInsight] = Field(default_factory=list)
    conclusion: str = Field(default="", description="给创作者的一句话决策建议")

    @field_validator("actionable_insights")
    @classmethod
    def _limit_insights(cls, v: list[ActionableInsight]) -> list[ActionableInsight]:
        # 承诺 2-3 条；若模型多给则截断，少给则保留（宽松处理）
        return v[:3]

    @property
    def is_valuable(self) -> bool:
        return self.noise_filtering.is_valuable_trend
