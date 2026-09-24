"""抖音热点深度分析工具。

输入热点词条与高赞评论，调用 OpenAI 兼容大模型，按
噪声过滤 → 情绪解构 → 传播引爆点 → 行动落地 四步输出结构化报告。
"""

from hotspot_analysis.models import (
    ActionableInsight,
    AnalysisMeta,
    EmotionDecoding,
    NoiseFiltering,
    TrendReport,
    ViralMechanism,
)

__version__ = "0.1.0"

__all__ = [
    "TrendReport",
    "NoiseFiltering",
    "EmotionDecoding",
    "ViralMechanism",
    "ActionableInsight",
    "AnalysisMeta",
    "__version__",
]
