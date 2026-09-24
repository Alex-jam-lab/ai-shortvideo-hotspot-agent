"""提示词引擎：把「四步分析逻辑」固化为系统提示词与 JSON Schema 规约。

设计要点：
- 角色设定：短视频运营总监 + 传播学学者 + 数据分析师
- 强约束输出：给出完整 JSON Schema，要求只输出 JSON
- 噪声短路：判定为噪声后，后续三步允许输出 skipped
- 评分规约：value_score / emotion_intensity / controversy_level 均有锚点说明
"""

from __future__ import annotations

import json

SYSTEM_PROMPT = """你是一位精通抖音生态的资深短视频运营总监、传播学学者兼数据分析师。
你的任务是对给定的抖音热点词条及相关评论/文本进行深度剖析，剔除无用噪声，提炼核心情绪，
并为创作者提供高可执行的商业或内容决策。

你必须严格按以下四步逻辑进行思考与输出：

1. 【噪声过滤 (Noise Filtering)】
判断该热点是真实引爆大众讨论的优质话题，还是转瞬即逝、无二次创作价值的
「严肃政务通报」「低质明星八卦」或「纯水军营销」。
- 若为噪声：is_valuable_trend=false，is_noise=true，noise_type 取对应枚举，noise_reason 说明依据，
  后续三步 emotion_decoding / viral_mechanism 输出 {"status":"skipped"}，actionable_insights 为空数组。
- 若有效：is_valuable_trend=true，is_noise=false，noise_type="有效话题"，给出 value_score（0-100）。
value_score 锚点：0-30 无讨论价值；31-60 短期流量、难沉淀；61-80 有明确情绪与可复制模板；
81-100 强情绪共振 + 高二次创作潜力。

2. 【心理与情绪解构 (Emotion Decoding)】
分析它戳中了大众的什么痛点、情绪或集体无意识（如：消费降级焦虑、猎奇、对立站队、玩梗狂欢）。
- pain_points：2-4 条具体痛点
- core_emotions：2-4 个情绪标签（愤怒/共鸣/解气/焦虑/羡慕/猎奇等）
- collective_unconscious：1-3 条群体心理
- emotion_intensity：情绪强度 0-100
- top_controversies：评论区 **TOP3 核心争议 / 负面声音**标签（如「这是炫富」「站着说话不腰疼」「数据造假」），
  直接引用评论中的反驳与质疑，禁止编造
- pitfall_warnings：拍摄**避坑雷区预警** 2-4 条（哪些表述 / 观点 / 画面容易引发反噬、举报或舆情翻车）

3. 【传播引爆点 (Viral Mechanism)】
推导它为什么能上热搜（如：强视觉冲突、争议性观点导致评论区大战、稀缺爆料）。
- triggers：2-4 个引爆因子
- visual_conflict：若有强视觉冲突，具体描述；否则填「无明显视觉冲突」
- controversy_level：争议指数 0-100
- rarity：信息稀缺度说明
- secondary_creation_potential：二次创作潜力（模板化程度、可复制性）

4. 【行动落地 (Actionable Insights)】
为普通短视频创作者或品牌提供 2-3 个可以直接开拍、借势营销的切入角度。
每个角度必须包含：
- angle_title：角度标题
- target_audience：目标人群
- golden_hooks：**3 套不同风格的黄金 3 秒 Hook 矩阵**（见下方 A/B 测试要求）
- content_outline：内容分镜提纲（3-5 条）
- execution_steps：可执行步骤（2-4 条）
- engagement_trigger：**评论区互动引导点**，明确写出结尾提问 / 置顶评论 / 二选一站队话术
- monetization：变现/带货或引流路径
- risk_notes：合规与蹭热点风险提示
- mainstream_angles：当前该话题**同质化 / 红海**的 2-3 个常规切入角度（大家都在拍的老套路）
- differentiated_angle：**蓝海 / 反常识的差异化切入视角**（人无我有、反直觉但成立的一句话提案，
  避免与 mainstream_angles 重复）

【A/B 测试 Hook 矩阵（golden_hooks 硬性要求）】
每条 actionable_insights 的 golden_hooks 必须且只能包含 **3 套**方案，
风格分别固定为：
- 「冲突对立型」：制造观点对立或身份反差，逼观众站队（如「…就是割韭菜，你信不信？」）
- 「悬念好奇型」：制造信息缺口，让人必须看完才知道答案（如「90% 的人都买错了，第 3 个最坑」）
- 「情绪共鸣型」：直接戳中痛点/委屈/爽点，引发「这说的就是我」（如「你是不是也被人说过太抠？」）
每套方案字段：style（固定为上述三个风格名之一）、script（可直接念出、含具体数字/冲突/反常识，禁止空泛）、
target_persona（这套 Hook 主打的人群画像）。

5. 【品牌合规与风控评估 (Risk Control)】
在给出行动方案的同时，必须站在品牌方与广告法角度做发布前风险体检，输出 risk_control：
- risk_level：风险等级，只能取 Low / Medium / High / Ban 四档之一。
  · Low：无违规风险，可放心发布；Medium：存在擦边表述或争议风险，需改写；
  · High：命中广告法极限词/功效承诺/医疗保健等高风险表述，必须整改后再发；
  · Ban：涉及违禁内容（赌博、色情、医疗诊断、虚假投资等），禁止发布。
- sensitive_words_found：从词条与评论中命中的**具体**敏感词/极限词/违禁表述清单
  （如：最、第一、国家级、100%有效、根治、稳赚不赔、包治百病 等）；
  若无则为空数组 []，**严禁编造不存在的敏感词**。
- compliance_suggestions：给出可直接替换的合规改写建议（把「最」改「较」、把功效承诺改为体验描述等），
  并提示需按《广告法》标注「广告」或避免绝对化用语。

最后给出 conclusion：面向创作者的一句话决策建议（跟进 / 谨慎 / 放弃）。

【字段约束（防幻觉 / 防空话）】
- actionable_insights：若 is_valuable_trend=true，必须输出 2-3 条，**严禁返回空数组**。
- 每条 actionable_insights 的 golden_hooks 必须恰好 3 套，风格须覆盖
  「冲突对立型」「悬念好奇型」「情绪共鸣型」各一套，禁止重复风格；script 必须具体可念。
- 每条 actionable_insights 必须给出 engagement_trigger（评论区引导互动点），
  必须是可直接使用的提问句或站队话术，禁止留空。
- content_outline 至少 3 条、execution_steps 至少 2 条，必须具体到动作。
- emotion_decoding.top_controversies 为有效话题时必须输出 2-3 条真实负面声音，
  pitfall_warnings 必须输出 2-4 条拍摄雷区，禁止留空数组或用「无」占位。
- 每条 actionable_insights 必须给出 mainstream_angles（2-3 条）与 differentiated_angle（1 条），
  differentiated_angle 必须与同质化角度形成明确反差，禁止与 mainstream_angles 语义重复。
- 所有痛点/情绪/引爆因子必须引用评论中的具体信号，禁止只写「无」「不清楚」「一般」。
- 若信息不足，请基于词条合理推断并降低相应分值，但不得留空必填项。
- 无法确定的信息（如 visual_conflict）用「无明显视觉冲突」等明确表述，而非空字符串。
- risk_control 必须始终输出：即便风险为 Low，也要给出 risk_level 与（可为空数组的）
  sensitive_words_found 以及合规提示，禁止省略该字段。

【硬性要求】
- 只输出一个合法 JSON 对象，不要输出任何解释文字、Markdown 代码块或多余标点。
- 所有文本使用简体中文。
- 严格遵循下方 JSON Schema 的字段名与类型，不得增删字段。
"""

JSON_SCHEMA_BLOCK = {
    "meta": {
        "keyword": "string（热点词条）",
        "model": "string（可留空，由程序回填）",
        "base_url": "string（可留空，由程序回填）",
        "created_at": "string（可留空，由程序回填）",
        "elapsed_seconds": "number（可留空，由程序回填）",
        "prompt_tokens": "integer（可留空，由程序回填）",
        "completion_tokens": "integer（可留空，由程序回填）",
        "total_tokens": "integer（可留空，由程序回填）",
        "repair_attempts": "integer（可留空，由程序回填）",
    },
    "noise_filtering": {
        "is_valuable_trend": "boolean",
        "is_noise": "boolean",
        "noise_type": "政务通报 | 低质明星八卦 | 纯水军营销 | 突发事故 | 其他噪声 | 有效话题",
        "noise_reason": "string",
        "value_score": "integer 0-100",
    },
    "emotion_decoding": {
        "status": "done | skipped",
        "pain_points": ["string"],
        "core_emotions": ["string"],
        "collective_unconscious": ["string"],
        "top_controversies": ["string（评论区 TOP3 核心争议/负面声音）"],
        "pitfall_warnings": ["string（拍摄避坑雷区预警）"],
        "emotion_intensity": "integer 0-100",
        "summary": "string",
    },
    "viral_mechanism": {
        "status": "done | skipped",
        "triggers": ["string"],
        "visual_conflict": "string",
        "controversy_level": "integer 0-100",
        "rarity": "string",
        "secondary_creation_potential": "string",
        "summary": "string",
    },
    "actionable_insights": [
        {
            "angle_title": "string",
            "target_audience": "string",
            "golden_hooks": [
                {
                    "style": "冲突对立型",
                    "script": "string",
                    "target_persona": "string",
                },
                {
                    "style": "悬念好奇型",
                    "script": "string",
                    "target_persona": "string",
                },
                {
                    "style": "情绪共鸣型",
                    "script": "string",
                    "target_persona": "string",
                },
            ],
            "content_outline": ["string"],
            "execution_steps": ["string"],
            "engagement_trigger": "string",
            "monetization": "string",
            "risk_notes": "string",
            "mainstream_angles": ["string（同质化常规角度）"],
            "differentiated_angle": "string（蓝海/反常识差异化视角）",
        }
    ],
    "risk_control": {
        "risk_level": "Low | Medium | High | Ban",
        "sensitive_words_found": ["string"],
        "compliance_suggestions": "string",
    },
    "conclusion": "string",
}


def build_schema_hint() -> str:
    """生成人类可读的 JSON Schema 提示块。"""
    return json.dumps(JSON_SCHEMA_BLOCK, ensure_ascii=False, indent=2)


def build_user_prompt(keyword: str, raw_text: str) -> str:
    """组装用户消息：热点数据 + Schema 约束。"""
    text = (raw_text or "").strip() or "（暂无评论文本，请仅依据词条本身推断，并降低置信度）"
    return (
        "请分析以下抖音热点数据：\n"
        f"- 【热点词条】：{keyword}\n"
        f"- 【相关内容/高赞评论】：\n{text}\n\n"
        "请严格按四步逻辑分析，并按如下 JSON Schema 输出（只输出 JSON）：\n"
        f"```json\n{build_schema_hint()}\n```"
    )


def build_repair_prompt(raw_output: str, error: str) -> str:
    """组装 JSON 修复消息。"""
    snippet = raw_output if len(raw_output) <= 6000 else raw_output[:6000] + "\n...(已截断)"
    return (
        "你上一次的输出不是合法 JSON，或字段不符合 Schema。\n"
        f"解析错误：{error}\n\n"
        "请把下面这段内容修正为**合法且符合 Schema 的 JSON**，"
        "只输出 JSON 本身，不要任何解释或 Markdown 代码块：\n"
        f"-----\n{snippet}\n-----"
    )


# -------- Few-Shot 示例（1 个有效热点 + 1 个噪声热点）--------
# 目的：稳定 JSON 结构、提升分析深度、抑制「无/不清楚」式空话。

_FEWSHOT_USER_VALID = (
    "请分析以下抖音热点数据：\n"
    "- 【热点词条】：打工人开始流行反向消费\n"
    "- 【相关内容/高赞评论】：不是不想买，是真买不起；以前比谁买得贵，现在比谁买得便宜。"
)

_FEWSHOT_ASSISTANT_VALID = {
    "meta": {},
    "noise_filtering": {
        "is_valuable_trend": True,
        "is_noise": False,
        "noise_type": "有效话题",
        "noise_reason": "评论呈现真实自嘲与对立讨论，非政务/八卦/水军，具可复制模板。",
        "value_score": 82,
    },
    "emotion_decoding": {
        "status": "done",
        "pain_points": ["购买力不足与收入预期转弱", "对品牌溢价与智商税的反感"],
        "core_emotions": ["共鸣", "自嘲", "焦虑"],
        "collective_unconscious": ["用省钱完成身份认同", "以自嘲消解焦虑"],
        "top_controversies": ["这是穷还嘴硬，被消费主义洗脑了", "站着说话不腰疼，有钱谁不想买好的", "又是卖平价好物的软广吧"],
        "pitfall_warnings": [
            "别把「穷」说成「高级」，容易刺痛真实经济困难人群",
            "避免点名贬低具体品牌，易被投诉或引发品牌粉丝反扑",
            "未标注广告就挂车带货，存在《广告法》合规风险",
        ],
        "emotion_intensity": 78,
        "summary": "消费降级焦虑被重新包装为「清醒」人设。",
    },
    "viral_mechanism": {
        "status": "done",
        "triggers": ["反常识标签易做对比", "评论区自带金句与站队", "省钱清单可模板化"],
        "visual_conflict": "贵价购物袋与平价平替、临期食品的前后对比画面具传播力",
        "controversy_level": 62,
        "rarity": "非独家爆料，属长期存在、近期集中爆发的社会情绪",
        "secondary_creation_potential": "高，可套用挑战体/清单体/代际对谈模板",
        "summary": "反常识标签聚合省钱叙事，低门槛模仿推动扩散。",
    },
    "actionable_insights": [
        {
            "angle_title": "30 元过一天反向消费实测",
            "target_audience": "18-35 岁都市青年、学生党、消费降级焦虑人群",
            "golden_hooks": [
                {
                    "style": "冲突对立型",
                    "script": "花三千买标的人别急着骂我，30 块过一天才是真本事，你服不服？",
                    "target_persona": "爱看站队对线的年轻男性用户",
                },
                {
                    "style": "悬念好奇型",
                    "script": "我用 30 块钱撑过一整天，最后还剩 4 块，你猜我怎么做到的？",
                    "target_persona": "价格敏感、爱看省钱攻略的学生党",
                },
                {
                    "style": "情绪共鸣型",
                    "script": "以前比谁买得贵，现在比谁买得便宜，你是不是也悄悄这样了？",
                    "target_persona": "消费降级焦虑、自我认同的都市青年",
                },
            ],
            "content_outline": ["晒过去冲动消费账单制造反差", "公布今日预算与挑战目标", "实拍临期食品/平替采购", "对比体验并给避坑清单"],
            "execution_steps": ["确定垂直品类（穿搭/零食）", "手机拍账单货架开箱", "剪成 15-30 秒并把价格反差前置"],
            "engagement_trigger": "结尾提问：你最近一次「反向消费」省了多少钱？评论区晒出来，我挑 3 个最狠的置顶。",
            "monetization": "平价好物联盟分佣、临期食品团购、二手平台引流",
            "risk_notes": "不得虚构原价或功效，广告需标注，避免贬低具体品牌",
            "mainstream_angles": ["省钱清单盘点", "平价平替开箱测评", "记账省钱生活 vlog"],
            "differentiated_angle": "反常识切入：不复盘「怎么省」，而是算清「哪些钱根本不该省」——用一次「贵但值」的消费打脸极端省钱，讨论性价比的真正边界。",
        },
        {
            "angle_title": "两代人的省钱对谈",
            "target_audience": "家庭用户、情感号受众",
            "golden_hooks": [
                {
                    "style": "冲突对立型",
                    "script": "我妈说我抠，我说我这叫清醒，到底谁对？你站哪边？",
                    "target_persona": "有代际消费观冲突的家庭用户",
                },
                {
                    "style": "悬念好奇型",
                    "script": "我翻了妈妈的旧账本，发现她 30 年前省的钱够我买两平米，你信吗？",
                    "target_persona": "对家庭理财与老物件好奇的受众",
                },
                {
                    "style": "情绪共鸣型",
                    "script": "我妈省钱是穷怕了，我省钱是清醒了，其实我们都没安全感。",
                    "target_persona": "与父母有共鸣、情感号受众",
                },
            ],
            "content_outline": ["分别采访两代人对省钱的定义", "翻出老物件与平替做对比", "讨论哪些钱该省哪些不能省", "总结共同的安全感需求"],
            "execution_steps": ["准备 5 个固定问题", "双机位或分屏拍摄", "保留真实反应与笑点"],
            "engagement_trigger": "留下问题：你家是爸妈省钱还是你省钱？评论区报个数，看看哪代人更会过日子。",
            "monetization": "情感号涨粉后接家庭理财科普与家居好物",
            "risk_notes": "避免把父母塑造成抠门，理财内容需持牌合规，不承诺收益",
            "mainstream_angles": ["两代人消费观对谈", "父母省钱名场面盘点", "代际情感煽情短片"],
            "differentiated_angle": "反常识切入：不拍「谁更省」，而是追问「为什么上一代敢花的钱我们现在不敢花」，把代际冲突转成对收入预期与安全感的冷静观察。",
        },
    ],
    "risk_control": {
        "risk_level": "Medium",
        "sensitive_words_found": ["最", "第一", "100%"],
        "compliance_suggestions": "规避「最便宜/第一」等极限词，改为「更划算/较省钱」；对比价格需注明来源与时效，避免贬低具体品牌；涉及带货须按《广告法》标注「广告」。",
    },
    "conclusion": "跟进，用「省钱实测 + 代际对谈」双线切入，把情绪共鸣转为实用价值。",
}

_FEWSHOT_USER_NOISE = (
    "请分析以下抖音热点数据：\n"
    "- 【热点词条】：某地发布道路结冰黄色预警\n"
    "- 【相关内容/高赞评论】：官方通报：预计未来 24 小时出现道路结冰，请注意出行安全。收到，注意安全。"
)

_FEWSHOT_ASSISTANT_NOISE = {
    "meta": {},
    "noise_filtering": {
        "is_valuable_trend": False,
        "is_noise": True,
        "noise_type": "政务通报",
        "noise_reason": "官方预警属严肃政务通告，评论均为常规回应，无冲突、无玩梗空间。",
        "value_score": 10,
    },
    "emotion_decoding": {"status": "skipped"},
    "viral_mechanism": {"status": "skipped"},
    "actionable_insights": [],
    "risk_control": {
        "risk_level": "Low",
        "sensitive_words_found": [],
        "compliance_suggestions": "政务信息转录需保持原意、避免断章取义；引用需注明来源，不得添加主观解读。",
    },
    "conclusion": "放弃，此类政务预警无借势价值。",
}


def build_fewshot_messages() -> list[dict[str, str]]:
    """构造 Few-Shot 对话消息（user/assistant 对，交替排列）。"""
    return [
        {"role": "user", "content": _FEWSHOT_USER_VALID},
        {
            "role": "assistant",
            "content": json.dumps(_FEWSHOT_ASSISTANT_VALID, ensure_ascii=False),
        },
        {"role": "user", "content": _FEWSHOT_USER_NOISE},
        {
            "role": "assistant",
            "content": json.dumps(_FEWSHOT_ASSISTANT_NOISE, ensure_ascii=False),
        },
    ]
