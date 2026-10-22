# CEFR 听说 can-do 清单

日期：2026-10-22
状态：草稿 v0.2（已修订）
归属：[M0 学习者模型设计](2026-10-22-m0-learner-model.md) 的配套静态数据

---

## 0. 怎么读这份清单

- 条目以 CEFR 及其 2020 年增补卷（Companion Volume）的量表为骨架，但文字是 Hearsay 自己写的、可被机器验证的版本，不是官方描述语的翻译。
- 每条有稳定 ID：`<技能前缀>-<等级>-<两位序号>`。前缀：`L` 听力、`SP` 口语产出（独白）、`SI` 口语互动（对话）、`PH` 语音控制。ID 一旦发布不再改动含义；要改就作废旧 ID、发新 ID。
- "验证"一列写的是**完整协议**的样本量与阈值。一次会话不必跑完整个协议：单次会话的最小样本（`min_sample`）和按比例判定的规则见主文档 4.6 节。默认 `min_sample`：L 类为 1 段材料 + 3 题（A1 为 1 段 + 2 题），SP 类为 1 次独白任务，SI 类为 1 个情境（含该条所需的 scripted_event），PH 类为 1 次跟读（≥ 6 句或 ≥ 10 个目标音素）。个别条目在验证列用「单次：」另行注明。
- `demonstrated` = 达到阈值比例；`partial` = 达到阈值比例的 80% 以上；`failed` = 更低。具体数字是 M0 的初值，M3 会按真实数据校准。
- 听力验证任务只有六种：gist、detail、inference、dictation（听写）、discrimination（二选一听辨）、spoken_response（口头回答，LLM 判）。验证列里的"听写"对应 dictation，"分类 / 听辨"对应 discrimination，"复述步骤 / 标出 / 归属"一律通过 spoken_response 完成。
- 清单覆盖 A1–C1，C2 每技能一条占位。**v1 的编排器只安排 A1–B2**；C1 条目保留 ID，状态保持 not_started。
- 读、写两个技能的 can-do 不在本文档，留给 M4。

## 1. 各等级的材料参数（供生成器使用）

| 等级 | 语速 wpm | 单段长度 | 词汇覆盖要求 | 口音 / 噪声 | 典型题材 |
|---|---|---|---|---|---|
| A1 | 90–110，字字清晰，句间停顿 | 20–40 秒 | Oxford 3000 的 A1 词 ≥ 95% | 单一标准口音，无噪声 | 自我介绍、数字、时间、购物、方向 |
| A2 | 110–130，清晰 | 40–70 秒 | A1–A2 词 ≥ 95% | 单一标准口音，无噪声 | 日常安排、天气、简单叙事、购物对话 |
| B1 | 130–150，接近自然 | 1–2 分钟 | A1–B1 词 ≥ 92% | 美音为主，偶有英音 | 工作日常、旅行、个人经历、简单观点 |
| B2 | 150–170，自然语速，含连读弱读 | 2–3 分钟 | A1–B2 词 ≥ 90% | v1：美音、轻微背景音（美/英混合留待后续） | 新闻摘要、工作讨论、抽象话题的观点 |
| C1 | 170+，自然，含口语省略、打断 | 3–5 分钟 | 不限 | 多种口音，有背景噪声，多人对话（v1 不生成） | 播客、会议、辩论、含隐含意义的对话 |

语速参考：美式英语日常对话约 150–160 wpm，新闻播音约 160–180 wpm。

新词数量（与覆盖率配套，材料越短新词越少）：A1 1–3 个，A2 3–5 个，B1 以上 5–8 个。

## 2. 听力（L）

验证通用方式：听后理解题（gist / detail / inference 三类）、听写关键词、按指令完成任务。"不重听"指材料只播放一次；允许重听的条目会注明。

### A1

| ID | 能做什么（zh） | Can-do (en) | 验证 |
|---|---|---|---|
| L-A1-01 | 能听懂针对自己的、语速慢且清晰的问候和基本问题（姓名、来自哪里、做什么） | Can understand slow, clear greetings and basic personal questions addressed to them | 5 个基本问题，答对 ≥ 4 |
| L-A1-02 | 能听出 0–1000 的数字、价格、电话号码、时间点 | Can recognise numbers up to 1000, prices, phone numbers and clock times | 10 项听写，正确 ≥ 8 |
| L-A1-03 | 能听懂日期、星期、月份 | Can understand days, dates and months | 8 项听写，正确 ≥ 6 |
| L-A1-04 | 能听懂简单的单步指令（"请坐""打开书"） | Can follow simple one-step instructions | 6 条指令，正确执行 ≥ 5 |
| L-A1-05 | 能从一段慢速短对话中听出谁在哪里、买什么、几点见面等单一具体信息 | Can pick out one concrete piece of information from a short, slow dialogue | 4 段材料各 1 题 detail，正确 ≥ 3 |
| L-A1-06 | 能听懂常见地点和方向词（左转、直走、在二楼） | Can understand common place and direction words | 6 条，正确 ≥ 5 |

### A2

| ID | 能做什么（zh） | Can-do (en) | 验证 |
|---|---|---|---|
| L-A2-01 | 能听懂关于日常话题（家庭、购物、工作、天气）的简短清晰对话的主旨 | Can understand the gist of short, clear dialogues on everyday topics | 4 段材料各 1 题 gist，正确 ≥ 3 |
| L-A2-02 | 能从公告、留言、语音信息中抓住关键信息（时间、地点、要做什么） | Can extract key details from short announcements and voice messages | 4 段各 2 题 detail，正确 ≥ 6/8 |
| L-A2-03 | 能听懂多步简单指令（"先……然后……"） | Can follow simple multi-step instructions | 3 条 3 步指令，顺序完全正确 ≥ 2 |
| L-A2-04 | 能听懂一段 1 分钟以内、按时间顺序讲的简单个人经历 | Can follow a short, chronological personal narrative | 3 段各 2 题（1 gist + 1 detail），正确 ≥ 5/6 |
| L-A2-05 | 能听出说话人是在建议、请求还是拒绝 | Can distinguish suggestions, requests and refusals | 8 条短话语分类，正确 ≥ 6 |
| L-A2-06 | 能在清晰语速下听懂常见缩约形式（I'm, don't, can't, it's） | Can understand common contractions at clear speed | 10 条听写，缩约形式正确 ≥ 8 |

### B1

| ID | 能做什么（zh） | Can-do (en) | 验证 |
|---|---|---|---|
| L-B1-01 | 能听懂接近自然语速的、关于熟悉话题的 1–2 分钟独白或对话的要点 | Can understand the main points of 1–2 minute speech on familiar topics at near-natural speed | 4 段各 3 题（gist + 2 detail），正确 ≥ 9/12 |
| L-B1-02 | 能在别人之间的日常对话中跟上话题转换 | Can follow topic changes in everyday conversation between others | 3 段多人对话，标出话题变化点，正确 ≥ 2/3 |
| L-B1-03 | 能听懂说话人的态度和简单观点（赞成、反对、犹豫） | Can identify the speaker's attitude and simple opinions | 8 条，正确 ≥ 6 |
| L-B1-04 | 能听懂含常见连读和弱读的话语（want to, going to, a lot of, can/can't） | Can understand common connected speech and weak forms | 12 条听写关键词，正确 ≥ 9；其中 can/can't 对立 ≥ 3/4 |
| L-B1-05 | 能听懂一段简单的说明或讲解（如何使用某物、某流程怎么走） | Can follow straightforward explanations and procedures | 3 段，复述步骤正确 ≥ 2/3 |
| L-B1-06 | 能听懂针对自己的较长问题并抓住问题的焦点 | Can understand longer questions addressed to them and identify what is being asked | 对话中 6 个复合问题，回答切题 ≥ 5 |
| L-B1-07 | 能在允许重听一次的条件下听懂简短新闻摘要的主要事实 | Can understand the main facts of a short news brief with one replay | 3 段各 3 题，正确 ≥ 7/9 |

### B2

| ID | 能做什么（zh） | Can-do (en) | 验证 |
|---|---|---|---|
| L-B2-01 | 能听懂自然语速、含连读弱读的 2–3 分钟材料的要点和多数细节 | Can understand main points and most details of 2–3 minute natural-speed speech | 3 段各 4 题，正确 ≥ 10/12 |
| L-B2-02 | 能听懂抽象或半专业话题（工作、社会、科技）的讨论，只要话题熟悉 | Can follow discussion on abstract or semi-specialised topics in a familiar field | 3 段各 3 题（含 1 inference），正确 ≥ 7/9 |
| L-B2-03 | 能识别说话人的言外之意：讽刺、礼貌拒绝、委婉批评 | Can recognise implied meaning: irony, polite refusal, indirect criticism | 8 条，正确 ≥ 6 |
| L-B2-04 | 能在轻微背景音和两种口音（美/英）切换下保持理解 | Can maintain comprehension with mild background noise and US/UK accent variation | 3 段混合口音材料各 3 题，正确 ≥ 7/9 |
| L-B2-05 | 能跟上三人以上的讨论，分清谁持什么立场 | Can follow a discussion among three or more speakers and attribute positions | 2 段，立场归属正确 ≥ 80% |
| L-B2-06 | 能听懂常见习语和短语动词的含义 | Can understand common idioms and phrasal verbs in context | 10 条，正确 ≥ 7 |
| L-B2-07 | 能通过重音和语调判断强调点和对比 | Can use stress and intonation to identify emphasis and contrast | 8 条（如 "I said TUESday, not Thursday"），正确 ≥ 6 |

### C1

| ID | 能做什么（zh） | Can-do (en) | 验证 |
|---|---|---|---|
| L-C1-01 | 能听懂 3–5 分钟的播客、讲座或会议片段，包括结构不清、有打断和自我修正的部分 | Can follow 3–5 minute podcasts, talks or meetings including poorly structured speech | 2 段各 5 题，正确 ≥ 8/10 |
| L-C1-02 | 能在多种口音（含印度、澳洲、苏格兰）和明显背景噪声下理解要点 | Can understand main points across varied accents and noticeable background noise | 3 段各 3 题，正确 ≥ 7/9 |
| L-C1-03 | 能理解口语中的省略、俚语和文化指涉 | Can understand ellipsis, slang and cultural references in speech | 8 条，正确 ≥ 6 |
| L-C1-04 | 能听出说话人论证的结构（主张、理由、让步、反驳） | Can identify argument structure: claim, support, concession, rebuttal | 2 段辩论，结构标注正确 ≥ 75% |
| L-C1-05 | 能在快速对话中识别幽默、双关和情绪变化 | Can recognise humour, wordplay and shifts in mood in fast conversation | 6 条，正确 ≥ 4 |

### C2（占位）

| ID | 能做什么（zh） | Can-do (en) | 验证 |
|---|---|---|---|
| L-C2-01 | 能毫不费力地理解任何形式的口语，包括专业讨论和强地方口音 | Can understand any kind of spoken language with ease | 待定 |

## 3. 口语产出（SP）—— 独白：描述、叙述、说明、论证

验证通用指标（由 LLM 对原样转写打分，由规则对时长和流利度计数）：
- **内容覆盖**：复述时覆盖材料要点的比例
- **可理解度**：Agent 在不看文本的情况下能否正确复述学习者的意思
- **流利度**：有效语速（去掉停顿）、每百词内 3 秒以上的停顿次数、每百词内的填充词和重启次数
- **准确度**：每百词的 major 错误数

### A1

| ID | 能做什么（zh） | Can-do (en) | 验证 |
|---|---|---|---|
| SP-A1-01 | 能用简单短句介绍自己：姓名、国家、职业、住在哪 | Can give basic personal information in simple phrases | 覆盖 4 项信息 ≥ 3，可理解 |
| SP-A1-02 | 能说出常见物品、颜色、数量 | Can name common objects, colours and quantities | 看图说出 10 个，正确 ≥ 7 |
| SP-A1-03 | 能用 "I like / I don't like / I have" 表达简单喜好和拥有 | Can express simple likes, dislikes and possession | 3 句以上，可理解 |
| SP-A1-04 | 能描述自己的家人或朋友（谁、几岁、做什么） | Can describe family members or friends in simple terms | 2 人各 2 项信息，可理解 |
| SP-A1-05 | 能说出一天的简单安排（几点起床、吃什么、去哪） | Can describe a simple daily routine | 4 件事以上，时间表达正确 ≥ 3 |

### A2

| ID | 能做什么（zh） | Can-do (en) | 验证 |
|---|---|---|---|
| SP-A2-01 | 能用一连串简单句讲一件过去发生的事（昨天 / 上周末） | Can narrate a past event in a series of simple sentences | ≥ 5 句，过去时标记正确率 ≥ 60%，可理解 |
| SP-A2-02 | 能描述自己的住处、城市或工作场所 | Can describe their home, town or workplace | ≥ 6 句，覆盖 3 个方面，可理解 |
| SP-A2-03 | 能简单说明自己的计划和打算（下周、假期） | Can talk about plans and intentions in simple terms | ≥ 4 句，将来表达正确 ≥ 3 |
| SP-A2-04 | 能用 1 分钟复述一段 A2 材料的主要内容 | Can retell the main content of an A2 passage in about a minute | 内容覆盖 ≥ 60%，可理解 |
| SP-A2-05 | 能给出简单的理由（because...）和比较（... is bigger than ...） | Can give simple reasons and make simple comparisons | 各 2 例，结构正确 |
| SP-A2-06 | 能描述自己的感受和身体状况（累、开心、头痛） | Can describe feelings and physical states | 看情境说出 5 个，正确 ≥ 4 |

### B1

| ID | 能做什么（zh） | Can-do (en) | 验证 |
|---|---|---|---|
| SP-B1-01 | 能就熟悉话题做 1–2 分钟连贯陈述，句子之间有基本衔接（and, but, so, then, because） | Can give a 1–2 minute connected talk on a familiar topic | 时长 ≥ 60 秒，衔接词 ≥ 4 种，3 秒以上停顿 ≤ 3 次/百词 |
| SP-B1-02 | 能按时间顺序讲一个完整的经历或故事，有开头、过程、结果 | Can tell a complete story or experience with beginning, middle and end | 三部分俱全，过去时正确率 ≥ 75% |
| SP-B1-03 | 能复述 B1 材料的要点并加入自己的一句评价 | Can retell the main points of a B1 passage and add a personal comment | 内容覆盖 ≥ 70%，评价成句 |
| SP-B1-04 | 能解释一件事怎么做（流程、用法），步骤清楚 | Can explain how to do something step by step | ≥ 4 步，顺序词正确，可理解 |
| SP-B1-05 | 能表达并简单论证一个观点（我认为……因为……另外……） | Can express an opinion and support it with two reasons | 观点 + 2 个理由，可理解 |
| SP-B1-06 | 能描述自己的梦想、希望和目标 | Can describe dreams, hopes and ambitions | ≥ 5 句，可理解 |
| SP-B1-07 | 能在不知道某个词时用解释、同义或举例绕过去 | Can paraphrase around an unknown word | 3 次目标词被屏蔽的任务，成功绕过 ≥ 2 |

### B2

| ID | 能做什么（zh） | Can-do (en) | 验证 |
|---|---|---|---|
| SP-B2-01 | 能就自己领域的话题做 2–3 分钟有条理的陈述，使用清晰的结构信号（首先、其次、总之） | Can give a clear, structured 2–3 minute presentation on a topic in their field | 时长 ≥ 120 秒，结构信号 ≥ 3 处，major 错误 ≤ 3/百词 |
| SP-B2-02 | 能比较两种方案的优缺点并给出建议 | Can weigh the pros and cons of two options and recommend one | 双方各 ≥ 2 点，有明确结论 |
| SP-B2-03 | 能用假设和条件句讨论可能性（If we did X, we might...） | Can speculate using conditionals and hedging | ≥ 3 个条件/假设结构正确 |
| SP-B2-04 | 能解释一个较复杂的问题的原因和后果 | Can explain the causes and consequences of a complex problem | 因果链 ≥ 2 层，可理解 |
| SP-B2-05 | 能在陈述中自我监控和自我纠正明显错误 | Can self-monitor and self-correct noticeable errors while speaking | 自我纠正 ≥ 2 次且纠正正确 |
| SP-B2-06 | 能用不同的句式和词汇避免重复（不只用 very / good / thing） | Can vary sentence structure and vocabulary to avoid repetition | very/good/thing/many 合计 ≤ 3/百词；从句比例 ≥ 30% |
| SP-B2-07 | 能概括一段 B2 材料的论点和论据，而非逐句复述 | Can summarise the argument and evidence of a B2 passage rather than retelling it | 抽象概括句 ≥ 2，覆盖 ≥ 70% |

### C1

| ID | 能做什么（zh） | Can-do (en) | 验证 |
|---|---|---|---|
| SP-C1-01 | 能就复杂话题做 3–5 分钟陈述，展开分论点并处理可能的反驳 | Can present a complex topic in 3–5 minutes, developing sub-points and addressing counterarguments | 分论点 ≥ 3，含 ≥ 1 处让步/反驳处理 |
| SP-C1-02 | 能根据听众调整正式程度和措辞 | Can adjust register and wording to the audience | 同一内容对两种听众各讲一遍，LLM 判定差异明显 |
| SP-C1-03 | 能准确表达细微的态度差异（略有保留、坚决反对、谨慎乐观） | Can convey fine shades of attitude and stance | 6 种态度提示，表达到位 ≥ 5 |
| SP-C1-04 | 能流畅使用习语、短语动词和口语化表达，且用得恰当 | Can use idioms, phrasal verbs and colloquialisms fluently and appropriately | ≥ 5 个，不当使用 ≤ 1 |
| SP-C1-05 | 能即兴回应一个陌生话题并保持结构 | Can respond to an unfamiliar topic at short notice while keeping structure | 准备时间 15 秒，≥ 90 秒连贯，3 秒以上停顿 ≤ 2 次/百词 |

### C2（占位）

| ID | 能做什么（zh） | Can-do (en) | 验证 |
|---|---|---|---|
| SP-C2-01 | 能流畅、精准、有风格地就任何话题发表长篇讲话 | Can speak at length on any topic with fluency, precision and style | 待定 |

## 4. 口语互动（SI）—— 对话：理解对方、回应、维持和推进对话

验证通用指标：
- **回应延迟**：对方说完到学习者开口的中位时间
- **切题率**：学习者的回应与对方话轮相关的比例
- **任务完成**：Scenario.objectives 的完成比例
- **互动策略**：澄清请求、确认、反馈信号（uh-huh, right, I see）的出现次数

### A1

| ID | 能做什么（zh） | Can-do (en) | 验证 |
|---|---|---|---|
| SI-A1-01 | 能回答关于自己的简单问题，并反问同样的问题 | Can answer simple personal questions and ask them back | 5 轮问答，切题 ≥ 4，反问 ≥ 2 |
| SI-A1-02 | 能用固定表达应对最基本的社交场合（问候、告别、感谢、道歉） | Can handle basic social exchanges with set phrases | 6 个情境，恰当回应 ≥ 5 |
| SI-A1-03 | 能用 "Sorry?" / "Again, please?" 请对方重复 | Can ask for repetition with a set phrase | 在 2 次听不懂的设计情境中，至少 1 次主动请求重复 |
| SI-A1-04 | 能在商店或餐厅完成最简单的点单和付款（指物、说数量、问价格） | Can order and pay in a shop or café using very simple language | 场景目标完成 ≥ 2/3 |
| SI-A1-05 | 能听懂并回答 yes/no 问题和选择问句 | Can understand and answer yes/no and alternative questions | 8 题，正确回应 ≥ 6 |

### A2

| ID | 能做什么（zh） | Can-do (en) | 验证 |
|---|---|---|---|
| SI-A2-01 | 能就日常话题进行简短交流，但需要对方配合放慢语速 | Can hold short everyday exchanges if the other person speaks slowly | 8 轮以上对话，切题 ≥ 75% |
| SI-A2-02 | 能提出和回应邀请、建议、道歉 | Can make and respond to invitations, suggestions and apologies | 3 个情境各 1 次发起 + 1 次回应，恰当 ≥ 5/6 |
| SI-A2-03 | 能询问和给出方向、时间、价格等具体信息 | Can ask for and give directions, times and prices | 场景目标完成 ≥ 3/4 |
| SI-A2-04 | 能在听不懂某个词时问 "What does X mean?" | Can ask what a word means | 设计 2 个生词，主动询问 ≥ 1 |
| SI-A2-05 | 能完成简单的交易性对话：预约、退换货、问路、买票 | Can handle simple transactional dialogues such as booking or returning an item | 场景目标完成 ≥ 3/4 |
| SI-A2-06 | 能用简单语言表达同意、不同意和偏好 | Can express agreement, disagreement and preference simply | 6 轮，恰当 ≥ 5 |

### B1

| ID | 能做什么（zh） | Can-do (en) | 验证 |
|---|---|---|---|
| SI-B1-01 | 能在没有准备的情况下就熟悉话题进行 5 分钟以上的对话 | Can sustain an unprepared 5-minute conversation on familiar topics | ≥ 12 个学习者话轮，切题 ≥ 80%，回应延迟中位 ≤ 3 秒 |
| SI-B1-02 | 能在旅行、工作中处理大多数常见情境（投诉、改期、解释问题） | Can deal with most situations likely to arise when travelling or at work | 场景目标完成 ≥ 3/4，含 1 个意外转折 |
| SI-B1-03 | 能表达和询问观点、感受，并简单回应对方的观点 | Can exchange opinions and feelings and respond to the other person's view | 对对方观点的直接回应 ≥ 3 次 |
| SI-B1-04 | 能用 "Do you mean...?" / "So you're saying..." 确认自己的理解 | Can check understanding by reformulating | 确认性重述 ≥ 2 次 |
| SI-B1-05 | 能礼貌地打断、插话和把话题拉回 | Can interrupt politely and steer the conversation back | 设计跑题情境，成功拉回 ≥ 1 次 |
| SI-B1-06 | 能在被问到意料之外的问题时争取时间（Let me think... / That's a good question） | Can buy time when asked an unexpected question | 2 个意外问题，使用争取时间策略 ≥ 1，随后作答 |
| SI-B1-07 | 能在小组讨论中轮到自己时发言并与前一位发言衔接 | Can take a turn in a group discussion and link to the previous speaker | 衔接前一位 ≥ 2 次 |

### B2

| ID | 能做什么（zh） | Can-do (en) | 验证 |
|---|---|---|---|
| SI-B2-01 | 能与母语者进行自然流畅的对话，不让对方感到吃力 | Can interact with native speakers fluently without strain for either party | Agent 以自然语速进行 ≥ 15 轮，无须放慢；回应延迟中位 ≤ 2 秒 |
| SI-B2-02 | 能在讨论中清楚地阐述和捍卫自己的观点，并回应反驳 | Can present and defend a viewpoint and respond to counterarguments | Agent 提出 3 次反驳，有效回应 ≥ 2 |
| SI-B2-03 | 能用恰当的礼貌程度提出请求、拒绝、给出负面反馈 | Can make requests, refuse and give negative feedback with appropriate politeness | 4 个情境，LLM 判定礼貌度恰当 ≥ 3 |
| SI-B2-04 | 能在工作会议中汇报进展、回答追问、协商时间和分工 | Can report progress, field follow-up questions and negotiate in a meeting | 场景目标完成 ≥ 4/5 |
| SI-B2-05 | 能自然使用反馈信号和话轮管理（uh-huh, right, exactly, anyway, by the way） | Can use backchannels and discourse markers naturally | 每 10 轮 ≥ 3 次，且不机械重复同一个 |
| SI-B2-06 | 能应对对方的误解并澄清自己的意思 | Can deal with misunderstanding and clarify their meaning | 设计 2 次 Agent "误解"，成功澄清 ≥ 2 |
| SI-B2-07 | 能参与闲聊（small talk）并自然地开启和结束对话 | Can engage in small talk and open and close a conversation naturally | 开场、维持 ≥ 4 轮、收尾三段俱全 |

### C1

| ID | 能做什么（zh） | Can-do (en) | 验证 |
|---|---|---|---|
| SI-C1-01 | 能在快节奏的多人讨论中抢到话轮并有效贡献 | Can get the floor in fast multi-party discussion and contribute effectively | 三方模拟讨论，主动获得话轮 ≥ 3 次，贡献被 LLM 判为推进讨论 |
| SI-C1-02 | 能处理敏感或冲突性对话（协商、调解、拒绝上级） | Can handle sensitive or confrontational conversations | 2 个高难场景，目标完成且礼貌度恰当 |
| SI-C1-03 | 能理解并回应幽默、讽刺和含蓄表达 | Can understand and respond to humour, irony and indirect speech | 6 次，恰当回应 ≥ 4 |
| SI-C1-04 | 能在对话中灵活切换正式与非正式语体 | Can shift between formal and informal register within a conversation | 场景内角色切换 2 次，语体随之变化 |
| SI-C1-05 | 能即时转述第三方的话并加入自己的评价 | Can relay what a third party said and comment on it in real time | 3 次转述，内容准确 ≥ 2 且含评价 |

### C2（占位）

| ID | 能做什么（zh） | Can-do (en) | 验证 |
|---|---|---|---|
| SI-C2-01 | 能毫不费力地参与任何对话，精准传达细微含义 | Can take part effortlessly in any conversation, conveying finer shades of meaning | 待定 |

## 5. 语音控制（PH）

PH 不单独成为一个技能等级，而是口语的子指标（主文档 4.4 的 `phonology.sub_score`）。多数条目对应 [错误清单](l1-zh-error-taxonomy.md) 的一个或几个 P 类代码；可懂度类条目（PH-A1-01、PH-B1-04、PH-B2-03、PH-B2-04、PH-C1-02）是综合指标，不对应单个代码。验证主要由音素评测器和韵律分析完成。

| ID | 能做什么（zh） | Can-do (en) | 验证 | 对应 P 码 |
|---|---|---|---|---|
| PH-A1-01 | 发音虽带明显口音，但常用词在重复后能被听懂 | Pronunciation of common words is intelligible, possibly after repetition | ASR 对 A1 词表朗读的识别率 ≥ 70% | 综合 |
| PH-A1-02 | 能区分并发出 /iː/–/ɪ/、/e/–/æ/ 两组最小对立对中的至少一组 | Can produce at least one of the /iː/–/ɪ/ and /e/–/æ/ contrasts | 对立对朗读，评测器区分正确 ≥ 70% | P08 |
| PH-A2-01 | 词尾辅音大多发出，不系统性吞掉或加尾音 | Final consonants are mostly produced, without systematic deletion or vowel insertion | 词尾辅音音素正确率 ≥ 70% | P05, P10 |
| PH-A2-02 | 两音节以上的常用词重音位置正确 | Word stress is correct on common polysyllabic words | 20 词，重音正确 ≥ 14 | P20 |
| PH-A2-03 | 疑问句用升调，陈述句用降调，且可区分 | Rising intonation for yes/no questions and falling for statements are distinguishable | 10 句，语调类型正确 ≥ 7 | P23 |
| PH-B1-01 | /θ/ /ð/ /v/ 在多数情况下发对，不系统性替换为 /s/ /z/ /w/ | /θ/, /ð/ and /v/ are mostly correct and not systematically substituted | 三音素正确率均 ≥ 70% | P01, P02 |
| PH-B1-02 | 能在非重读音节使用弱化元音（schwa），而不是每个音节都读满 | Uses schwa in unstressed syllables rather than giving every syllable full weight | 功能词与非重读音节时长比 ≤ 0.7（相对重读音节） | P21 |
| PH-B1-03 | 能产出基本连读（an apple, pick it up）而不是逐词停顿 | Produces basic linking rather than word-by-word pauses | 10 处连读点，连读发生 ≥ 6 | P24 |
| PH-B1-04 | 发音总体可懂，陌生听者不需要重复就能理解 | Generally intelligible; an unfamiliar listener does not need repetition | ASR 对 B1 自由发言识别率 ≥ 85% | 综合 |
| PH-B2-01 | 句子重音落在信息词上，功能词弱读，有节奏感 | Sentence stress falls on content words with reduced function words | 韵律分析：重读/非重读时长比 ≥ 1.5；v1 由规则判，开发者抽检 | P22, P25 |
| PH-B2-02 | 能用重音表达对比和强调 | Can use stress to signal contrast and emphasis | 6 句对比重音任务，正确 ≥ 4 | P22 |
| PH-B2-03 | 自然语速下仍保持可懂度，并有常见的口语缩约（gonna, wanna, dunno） | Intelligible at natural speed and uses common spoken reductions | 有效语速 ≥ 130 wpm 且 ASR 识别率 ≥ 85% | 综合 |
| PH-B2-04 | 所有英语音素都能产出，残余口音不影响理解 | All English phonemes can be produced; residual accent does not impede understanding | 全部音素正确率均 ≥ 75%，无单一音素 < 60% | 综合 |
| PH-C1-01 | 语调能表达细微态度（犹豫、讽刺、热情） | Intonation conveys fine shades of attitude | 6 种态度朗读，LLM 从音频转写+韵律特征判定正确 ≥ 4 | P23 |
| PH-C1-02 | 口音接近目标口音或稳定、一致、不影响任何听者 | Accent approximates the target variety or is stable and never impedes comprehension | 全部音素正确率均 ≥ 85% | 综合 |

## 6. 条目数量汇总

| 技能 | A1 | A2 | B1 | B2 | C1 | C2 | 合计 |
|---|---|---|---|---|---|---|---|
| L | 6 | 6 | 7 | 7 | 5 | 1 | 32 |
| SP | 5 | 6 | 7 | 7 | 5 | 1 | 31 |
| SI | 5 | 6 | 7 | 7 | 5 | 1 | 31 |
| PH | 2 | 3 | 4 | 4 | 2 | – | 15 |
| 合计 | 18 | 21 | 25 | 25 | 17 | 3 | 109 |

## 7. 与学习者模型的关系

- `SkillEstimate.listening` 由 L 类证据计算；`speaking_production` 由 SP 类、`speaking_interaction` 由 SI 类分别计算，`speaking` 取两者较低者；PH 类证据汇成 `phonology.sub_score`，作为口语的子指标展示。计算规则见主文档 4.4。
- 每条 can-do 的默认 `weight` 为 1.0，在主文档 4.4 的加权通过率中生效。涉及"可理解度"和"任务完成"的条目权重 1.5：SP-B1-01、SP-B2-01、SI-B1-01、SI-B2-01、SI-B1-02、SI-B2-04、PH-B1-04、PH-B2-04。
- 一次会话通常只能验证 1–3 条 can-do，由编排器写入 `Session.target_can_do_ids`。编排器优先安排"当前等级尚未 validated"和"上一等级 emerging"的条目；需要 scripted_event 的 SI 条目由场景生成器据此配事件。
