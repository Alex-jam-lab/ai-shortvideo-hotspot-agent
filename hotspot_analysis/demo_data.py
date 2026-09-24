"""内置演示数据：无需 API Key 即可体验完整输出格式。

用于 CLI 的 --demo 模式与文档示例。
"""

from __future__ import annotations

from datetime import datetime, timezone

from hotspot_analysis.models import (
    ActionableInsight,
    AnalysisMeta,
    EmotionDecoding,
    HookOption,
    NoiseFiltering,
    RiskControl,
    TrendReport,
    ViralMechanism,
)


def build_demo_report(keyword: str = "年轻人开始流行反向消费") -> TrendReport:
    """构造一份示例报告（对应 examples/sample_output.md）。"""
    return TrendReport(
        meta=AnalysisMeta(
            keyword=keyword,
            model="demo-model",
            base_url="https://example.com/v1",
            created_at=datetime.now(timezone.utc).astimezone().isoformat(
                timespec="seconds"
            ),
            elapsed_seconds=0.0,
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            repair_attempts=0,
        ),
        noise_filtering=NoiseFiltering(
            is_valuable_trend=True,
            is_noise=False,
            noise_type="有效话题",
            noise_reason=(
                "评论呈现真实的自嘲、共鸣与对立讨论，非官方通报、非水军刷量；"
                "「反向消费」具备明确可复制的行为标签与内容模板，二次创作空间大。"
            ),
            value_score=82,
        ),
        emotion_decoding=EmotionDecoding(
            status="done",
            pain_points=[
                "消费降级下的经济压力与不安全感",
                "被消费主义裹挟后的疲惫与反抗",
                "代际消费观差异带来的身份焦虑",
            ],
            core_emotions=["共鸣", "焦虑", "自嘲", "解气"],
            collective_unconscious=[
                "通过「省钱」完成群体身份认同",
                "以自嘲消解焦虑、抱团取暖",
            ],
            emotion_intensity=78,
            summary="话题本质是「消费降级焦虑」转化为「清醒人设」的集体情绪出口。",
        ),
        viral_mechanism=ViralMechanism(
            status="done",
            triggers=["高共鸣情绪", "观点争议（清醒 vs 无奈）", "低成本模仿"],
            visual_conflict="无明显视觉冲突",
            controversy_level=65,
            rarity="中等，属于社会情绪型话题而非独家爆料",
            secondary_creation_potential="高，可套用「对比体」「清单体」「挑战体」模板",
            summary="情绪共振 + 低门槛模仿是登上热搜的核心机制。",
        ),
        actionable_insights=[
            ActionableInsight(
                angle_title="反向消费避坑清单",
                target_audience="18-30 岁学生与职场新人",
                golden_hooks=[
                    HookOption(
                        style="冲突对立型",
                        script="花三千买标的人别急着骂我，30 块过一天才是真本事，你服不服？",
                        target_persona="爱看站队对线的年轻用户",
                    ),
                    HookOption(
                        style="悬念好奇型",
                        script="这 5 样东西我一直劝人别买贵的，第 3 个最坑，你猜是哪个？",
                        target_persona="价格敏感、爱看避坑清单的学生党",
                    ),
                    HookOption(
                        style="情绪共鸣型",
                        script="以前买牌子，现在只看有没有券，你是不是也变成这样了？",
                        target_persona="消费降级中的都市青年",
                    ),
                ],
                content_outline=[
                    "钩子：亮出同类商品价格差",
                    "展示 3 个平替实测",
                    "给出选购判断标准",
                    "引导评论区晒自己的省钱招",
                ],
                execution_steps=[
                    "选定高频消费品类（日用、护肤）",
                    "拍前后对比 + 价格字幕",
                    "结尾提问引导互动",
                ],
                engagement_trigger="结尾提问：你买过最不值的智商税是什么？评论区说出来，我挑 3 个置顶避坑。",
                monetization="挂车低价好物 / 引流至省钱社群",
                risk_notes="避免贬低他人消费选择，防止评论区对立失控",
            ),
            ActionableInsight(
                angle_title="两代人消费观对谈",
                target_audience="25-40 岁有家庭的用户",
                golden_hooks=[
                    HookOption(
                        style="冲突对立型",
                        script="我妈说我抠，我说我在清醒，两代人到底谁对？你站哪边？",
                        target_persona="有代际消费观冲突的家庭用户",
                    ),
                    HookOption(
                        style="悬念好奇型",
                        script="我翻了妈妈的旧账本，她 30 年前省的这笔钱，够我现在买两平米，你信吗？",
                        target_persona="对家庭理财与老物件好奇的受众",
                    ),
                    HookOption(
                        style="情绪共鸣型",
                        script="我妈省钱是穷怕了，我省钱是清醒了，其实我们都没安全感。",
                        target_persona="与父母有强共鸣的情感号受众",
                    ),
                ],
                content_outline=[
                    "钩子：复述长辈原话",
                    "对比两代人的消费清单",
                    "各让一步的共识",
                    "引导晒家庭消费观",
                ],
                execution_steps=[
                    "设计双人对话脚本",
                    "用字幕强化对比",
                    "结尾抛互动问题",
                ],
                engagement_trigger="留下问题：你家是爸妈省钱还是你省钱？评论区报个数，看看哪代人更会过日子。",
                monetization="家庭好物 / 记账工具推广",
                risk_notes="避免制造代际对立，落点应是理解而非指责",
            ),
        ],
        risk_control=RiskControl(
            risk_level="Medium",
            sensitive_words_found=["最", "第一"],
            compliance_suggestions=(
                "避免使用「最便宜/第一」等极限词，改为「更划算/较省钱」；"
                "价格对比需注明来源与时效，不贬低具体品牌；"
                "涉及带货须按《广告法》标注「广告」并明示利益关系。"
            ),
        ),
        conclusion="跟进。这是强情绪共振 + 高可复制模板的优质话题，适合以「身份认同 + 省钱攻略」双线切入。",
    )
