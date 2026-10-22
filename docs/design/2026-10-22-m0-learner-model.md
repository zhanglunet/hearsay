# M0 设计文档：学习者模型（Learner Model）

日期：2026-10-22
状态：草稿 v0.2（已通过一轮独立实现者评审并修订）
配套文档：
- [CEFR 听说 can-do 清单](cefr-can-do-listening-speaking.md)
- [中文母语者错误清单](l1-zh-error-taxonomy.md)

---

## 0. 这份文档解决什么问题

Hearsay 的差异点是"所有练习内容都从这个人身上长出来"。要做到这一点，必须先回答三个问题：

1. 我们到底记录学习者的哪些信息？用什么结构？（第 1–3 节）
2. 一次练习结束后，这些信息如何被更新？（第 4 节）
3. 内容生成和计划编排从模型里读什么？（第 5 节）

本文档不涉及 UI、存储引擎选型和具体算法参数的调优，这些留给 M1–M4。

### 0.1 设计原则

- **证据驱动**：模型里每一个判断（"听力 B1"、"θ 音有问题"、"掌握了 look forward to"）都必须能回溯到具体的会话和话语。没有证据的字段不存在。
- **分技能、分方向**：听懂一个词和说出一个词是两种状态；听力水平和口语水平分别估计。
- **先粗后细**：第一版的字段够用即可，字段宁少勿多；但 ID 体系（can-do 编号、错误代码）从第一天就要稳定，因为后面所有数据都挂在它们上面。
- **母语是一等字段**：错误分类、发音目标、解释语言都依赖 `l1`。第一版只实现 `zh-CN`，但结构上不写死。
- **用户的数据属于用户**：录音、转写、错误档案都可导出、可删除。

### 0.1a 第一版范围（我的选择，可推翻）

评审指出几处范围没有写死会让工作量差三倍，这里明确：

- **等级范围**：v1 只为 A1–B2 生成材料和场景；C1 的 can-do 保留在清单里但不被编排器安排（状态永远 not_started），C2 占位。
- **口音**：v1 只做美音（`target_variety = en-US`）。字段保留 `en-GB` 枚举值但不实现；B2 材料的"美/英混合"降级为"美音、轻微背景音"。
- **材料声音**：v1 用单一 TTS 音色族（Kokoro 多音色足够区分对话角色），不做多口音、多说话人噪声场景。
- **数据拓扑**：v1 的 ML（转写、音素评测、LLM 判定）在服务端运行，录音必须上传。学习者模型主副本在服务端账户下，客户端缓存。录音保留 30 天供回放后自动删除，模型数据随时可整体导出（JSON）和一键删除。"本地优先"在 v1 降级为"可导出、可删除"，留作后续目标。（2026-10-22 产品负责人已确认，README 已同步。）
- **人工评审**：v1 没有运营后台。`judged_by: human` / `detected_by: human` 保留给开发者用脚本手动标注；`X00` 未分类错误和低置信实例写进夜间报告文件，由开发者翻看。

### 0.2 术语

| 术语 | 含义 |
|---|---|
| 词项（Lexical Item） | 单词、词块（chunk）、搭配或句型。Hearsay 以词块为主要单位，单词次之 |
| 识别（Recognition） | 听到/看到能理解 |
| 产出（Production） | 能在说/写中正确用出来 |
| 错误实例（Error Instance） | 某次话语中发生的一次具体错误 |
| 错误模式（Error Pattern） | 同一错误代码在该学习者身上的聚合统计 |
| can-do | CEFR 风格的"能做什么"描述，带编号，可被证据验证 |
| 会话（Session） | 一次练习活动：听、跟读、复述、对话、复习之一 |
| 证据事件 | 一次会话对一条 can-do 的一次判定（demonstrated / partial / failed），见 2.6 与 4.6 |
| 材料（Material） | 一段带文本和音频的听力/跟读素材 |

---

## 1. 对象总览

```
Learner ──1:4── SkillEstimate          （听/说/读/写 四个技能的水平估计）
   │
   ├──1:n── LexicalKnowledge ──n:1── LexicalItem   （词项掌握状态，含 FSRS 卡）
   │
   ├──1:n── ErrorPattern ──1:n── ErrorInstance     （错误档案：聚合 + 实例）
   │
   ├──1:n── PhonemeProfile                          （音素级发音统计）
   │
   ├──1:n── CanDoProgress ──1:n── CanDoEvidence ──n:1── CanDoStatement
   │
   ├──1:n── Session ──n:1── Material / Scenario
   │
   └──1:n── DailyPlan
```

所有带时间的字段用 ISO 8601 UTC。所有 ID 用 ULID（时间可排序，便于按时间切片回放）。CanDoStatement 和 ErrorCode 用人读的稳定编码，不用 ULID。

---

## 2. 核心对象定义

下面用带注释的 YAML 描述字段。类型记法：`string`、`int`、`float`、`bool`、`datetime`、`enum[...]`、`list<T>`、`ref<T>`（外键）。

### 2.1 Learner

```yaml
Learner:
  id: ulid
  l1: enum[zh-CN]              # 母语。决定错误分类表、发音对比目标、解释语言
  target_variety: enum[en-US, en-GB]   # 发音目标口音；默认 en-US；v1 只实现 en-US
  explanation_language: enum[zh, en, auto]  # 解释用什么语言；auto = B1 以下用 zh，以上渐进用 en
  goals:                       # 学习目的，影响场景库权重
    - type: enum[daily_life, work, travel, academic, exam_ielts, exam_toefl, other]
      note: string             # 自由描述，例如"每周两次和美国同事开会"
  interests: list<string>      # 话题标签，例如 [cooking, nba, startups]，用于生成材料
  time_budget:
    minutes_per_day: int       # 默认 15
    preferred_windows: list<string>   # 例如 ["07:30-08:00", "22:00-22:30"]
  correction_style: enum[recast, explicit, delayed]   # 纠错风格；默认 recast
  feedback_density: enum[low, medium, high]           # 每次会话给多少条反馈；默认 medium
  onboarding_completed_at: datetime | null
  created_at: datetime
  updated_at: datetime
```

**纠错风格说明**
- `recast`：对话中 Agent 用正确说法自然重述，不打断；会话后复盘集中列出
- `explicit`：当场指出并要求重说一次
- `delayed`：对话中完全不纠，只在复盘时给

### 2.2 SkillEstimate

每个学习者有七行：四个展示技能（listening / speaking / reading / writing）加三个口语子行（speaking_production / speaking_interaction / phonology）。speaking 行是派生的：`level = min(speaking_production.level, speaking_interaction.level)`，`confidence` 取两者较低者。phonology 行的 `level` 字段不用，只用 `sub_score`。第一版只认真估计听与说，读写用自评 + 占位。

```yaml
SkillEstimate:
  learner_id: ref<Learner>
  skill: enum[listening, speaking, speaking_production, speaking_interaction, phonology, reading, writing]
  level: float                 # 连续值 1.0–6.0；A1=1, A2=2, B1=3, B2=4, C1=5, C2=6
                               # 小数部分表示在该级内的进度，例如 3.4 ≈ B1 中段
  prior_level: float | null    # 入门测评 / 自评给出的先验，见 4.4
  prior_weight: float          # 先验等价于多少条证据；placement 为 6，self_report 为 2
  sub_score: float | null      # 仅 phonology 行使用：0–1 的语音控制综合分，见 4.4
  confidence: float            # 0–1，证据越多、越一致越高
  evidence_count: int          # 参与估计的 CanDoEvidence 条数
  last_evidence_at: datetime | null
  source: enum[self_report, placement, inferred, derived]   # 当前估计主要来自哪里；speaking 行为 derived
  updated_at: datetime
```

`level` 与 CEFR 标签的映射：`floor(level)` 对应等级，`A1=1 … C2=6`；`level < 1.0` 视为 pre-A1。UI 显示用标签，内部计算用连续值。

### 2.3 LexicalItem 与 LexicalKnowledge

词项是全局共享的（所有学习者共用一张表），掌握状态是每个学习者自己的。

```yaml
LexicalItem:
  id: ulid
  kind: enum[word, chunk, collocation, pattern]
  #  word        : 单词，如 "appointment"
  #  chunk       : 固定词块，如 "look forward to", "as far as I know"
  #  collocation : 搭配，如 "make a decision"
  #  pattern     : 句型，如 "It takes + 时间 + to do"
  text: string                 # 规范形式（lemma 或词块原形）
  ipa_us: string | null        # 美音 IPA；词块可为空
  cefr_level: enum[A1,A2,B1,B2,C1,C2] | null   # 来源：Oxford 3000/5000 或 EVP；无则由 LLM 估计并标 estimated
  cefr_source: enum[oxford, evp, estimated]
  frequency_rank: int | null   # 词频排名（ECDICT 的 frq/bnc 字段）
  zh_gloss: string             # 简短中文释义
  tags: list<string>           # 话题/场景标签
  created_at: datetime
```

```yaml
LexicalKnowledge:
  learner_id: ref<Learner>
  item_id: ref<LexicalItem>

  # 识别方向（听懂）
  recognition: enum[unknown, exposed, recognized, comprehended]
  #  unknown      : 从未在材料中出现
  #  exposed      : 出现过，但学习者在理解检查中未证明听懂
  #  recognized   : 在理解检查中至少一次正确
  #  comprehended : 在 ≥3 段不同材料中理解正确，且近 30 天无失败
  recognition_evidence: list<ref<Session>>    # 最近 10 条

  # 产出方向（说出来）
  production: enum[never, attempted, produced, automatic]
  #  never      : 从未尝试产出
  #  attempted  : 尝试过但有错（发音 / 形态 / 搭配）
  #  produced   : 在复述或对话中至少一次正确使用
  #  automatic  : 在 ≥3 次不同场景中自发（非提示）正确使用
  production_evidence: list<ref<Session>>

  # 间隔重复（FSRS）。只有当 item 进入"需要主动复习"状态时才创建卡
  fsrs: FsrsCard | null
  review_reason: enum[missed_in_listening, failed_in_production, mispronounced, learner_saved] | null

  first_seen_at: datetime
  last_seen_at: datetime
  updated_at: datetime
```

```yaml
FsrsCard:                      # 字段与 ts-fsrs / py-fsrs 保持一致，便于直接调库
  due: datetime
  stability: float
  difficulty: float
  elapsed_days: int
  scheduled_days: int
  reps: int
  lapses: int
  state: enum[new, learning, review, relearning]
  last_review: datetime | null
```

**复习的含义不同于 Anki**：对 Hearsay 来说，"复习一张卡"= 在新的材料或场景中再次遇到/被要求使用该词项。评分（again / hard / good / easy）由 Agent 根据这次遭遇的结果自动给出，学习者不需要手动打分。见第 4.3 节。

### 2.4 ErrorInstance 与 ErrorPattern

错误代码来自 [中文母语者错误清单](l1-zh-error-taxonomy.md)，形如 `P01`、`G01`、`L03`、`H02`、`I04`。

```yaml
ErrorInstance:
  id: ulid
  learner_id: ref<Learner>
  session_id: ref<Session>
  utterance_id: string         # 会话转写中的话语编号；H 类指向 speaker=material 的话语
  code: ErrorCode              # 如 G01；取值范围见错误清单，含保留码 X00
  observed: string             # 学习者实际说的（原样）；H 类为学习者听写/选择的内容
  expected: string             # 目标说法；H 类为材料原文
  context: string              # 前后各一句
  severity: enum[minor, major]
  #  minor : 不影响理解（如多数发音偏差、冠词）
  #  major : 导致误解或听不懂（如 can/can't、时态造成的时间误解、关键词发音致不可辨）
  detected_by: enum[phoneme_scorer, asr_llm, asr_llm_realtime, rule, human]
  status: enum[provisional, confirmed, discarded]
  #  provisional : 对话中实时链路发现、已用于 recast，但尚未被会话后批处理核对
  #  confirmed   : 批处理确认（或批处理直接发现）
  #  discarded   : 批处理发现实时判断有误；保留记录但不计入统计
  confidence: float            # 检测置信度；低于 0.6 的不计入 ErrorPattern 统计，只保留实例
  audio_ref: string | null     # 对应录音片段
  created_at: datetime
```

```yaml
ErrorPattern:
  learner_id: ref<Learner>
  code: ErrorCode
  count_total: int
  count_30d: int
  count_7d: int
  opportunities_30d: int | null   # 近 30 天有多少次"本可以犯这个错"的机会；用于算错误率
                                  # 例如 G01 冠词的 opportunities = 转写中名词短语数量
                                  # 统计范围见 4.7；未统计时为 null
  opportunities_7d: int | null
  error_rate_30d: float | null # count_30d / opportunities_30d；opportunities 为 null 时为 null
  error_rate_7d: float | null
  trend: enum[improving, stable, worsening, insufficient_data]
  first_seen_at: datetime
  last_seen_at: datetime
  remediation:
    status: enum[none, scheduled, in_progress, resolved]
    fsrs: FsrsCard | null      # 错误模式也走 FSRS：到期 = 在新场景里制造一次用对的机会
    resolved_at: datetime | null   # 近 30 天 error_rate < 阈值 且 opportunities ≥ 10 时标 resolved
  updated_at: datetime
```

**为什么要记 opportunities**：只数错误次数会惩罚说得多的人。一个人说了 200 个名词短语错 10 个冠词，比说了 20 个错 5 个好得多。没有机会数就没有错误率，就没法判断趋势。

### 2.5 PhonemeProfile

```yaml
PhonemeProfile:
  learner_id: ref<Learner>
  phoneme: string              # ARPAbet，如 TH, DH, V, IH, IY, AE, EH；与 OpenPronounce 输出对齐
  position: enum[initial, medial, final, any]   # 词尾辅音是中文母语者的独立难点，所以按位置分开统计
  attempts_30d: int
  accuracy_mean_30d: float     # 0–1，评测器给出的音素正确率均值
  accuracy_mean_prev_30d: float | null    # 上一个 30 天，用于趋势
  common_substitution: string | null      # 最常被替换成什么，如 TH → S
  related_error_codes: list<ErrorCode>    # 关联到的 P 类错误代码，可多个（如词尾 D 同时属于 P05/P07/P10）；映射表见错误清单第 8 节
  updated_at: datetime
```

韵律（重音、语调、连读）不在音素表里，单独以错误代码 P20–P25 记入 ErrorPattern。

### 2.6 CanDoStatement / CanDoProgress / CanDoEvidence

```yaml
CanDoStatement:                # 全局静态表，内容见 can-do 清单
  id: string                   # 格式 <技能前缀>-<等级>-<序号>，前缀 L / SP / SI / PH，如 L-B1-03、SP-A2-05、PH-B1-01
  skill: enum[listening, speaking_production, speaking_interaction, phonology]
  cefr: enum[A1,A2,B1,B2,C1,C2]
  text_zh: string
  text_en: string
  verification: string         # 人读的验证标准，见清单；其含义见 4.6
  min_sample: string           # 单次会话构成一个证据事件所需的最小样本，如 "1 段材料 3 题" "1 个情境"
  weight: float                # 对 SkillEstimate 的贡献权重；默认 1.0
```

```yaml
CanDoEvidence:
  id: ulid
  learner_id: ref<Learner>
  statement_id: ref<CanDoStatement>
  session_id: ref<Session>
  verdict: enum[demonstrated, partial, failed]
  sample_size: int             # 本次事件实际完成的样本量（题数 / 情境数 / 对立对数）
  metrics: map<string, float>  # 该次验证的量化指标，例如 {comprehension_qs_correct: 0.8, wpm: 140}
  judged_by: enum[rule, llm, human]
  created_at: datetime
```

```yaml
CanDoProgress:                 # 由 CanDoEvidence 派生，可随时重算
  learner_id: ref<Learner>
  statement_id: ref<CanDoStatement>
  status: enum[not_started, emerging, validated, lapsed]
  #  not_started : 无证据
  #  emerging    : 有 demonstrated，但未满足 validated 条件
  #  validated   : 近 60 天内 ≥3 次 demonstrated，分布在 ≥2 个不同会话、≥2 段不同材料/场景，
  #                且最近 3 次中无 failed
  #  lapsed      : 曾 validated，但最近 3 次证据中有 ≥2 次 failed
  demonstrated_count: int
  failed_count: int
  last_evidence_at: datetime | null
```

### 2.7 Session

```yaml
Session:
  id: ulid
  learner_id: ref<Learner>
  type: enum[listen, shadow, retell, converse, review, placement]
  material_id: ref<Material> | null
  scenario_id: ref<Scenario> | null
  target_can_do_ids: list<ref<CanDoStatement>>   # 本次会话计划验证的条目（1–3 条）；编排器写入
  target_error_codes: list<ErrorCode>            # 本次要数机会的错误代码，见 4.7
  started_at: datetime
  ended_at: datetime | null
  duration_sec: int
  transcript:                  # 逐话语
    - utterance_id: string
      speaker: enum[learner, agent, material]
      text: string             # 对 learner：ASR 原样转写（见 4.1 关于"原样"的要求）
      realtime_text: string | null   # converse 会话中实时链路的转写，仅供追溯；权威文本是 text
      start_ms: int
      end_ms: int
      audio_ref: string | null
  metrics: map<string, float>  # 按 type 不同，见 4.2
  summary_zh: string | null    # 会话后复盘文本
  created_at: datetime
```

### 2.8 Material 与 Scenario

```yaml
Material:
  id: ulid
  kind: enum[dialogue, monologue, story, news_brief, instruction]
  title: string
  target_cefr: enum[A1,A2,B1,B2,C1,C2]
  topic_tags: list<string>
  text: string
  audio_ref: string
  word_timestamps: list<{word: string, start_ms: int, end_ms: int}>
  sentences: list<{idx: int, text: string, start_ms: int, end_ms: int}>
  wpm: float                   # 实测语速
  lexical_items: list<ref<LexicalItem>>   # 本材料覆盖的词项
  comprehension_questions:     # 听后检查任务，v1 支持六种
    - q_zh: string
      type: enum[gist, detail, inference, dictation, discrimination, spoken_response]
      #  gist / detail / inference : 选择或简答，LLM 判
      #  dictation                 : 听写一句或若干关键词，规则比对（容忍拼写）
      #  discrimination            : 二选一听辨（can/can't、ship/sheep、问/陈），规则判
      #  spoken_response           : 学习者口头回答（复述步骤、说出谁持什么立场），LLM 判
      #  排序、标注类验证一律转成 spoken_response
      answer: string
      item_ids: list<ref<LexicalItem>>   # 本题考查的词项；答错 → 这些词项进 FSRS
      error_codes: list<ErrorCode>       # 本题针对的 H 类难点；答错 → 写 H 类 ErrorInstance
  target_can_do_ids: list<ref<CanDoStatement>>   # 本材料设计用来验证的条目
  generated_by: enum[llm, imported]
  generated_for: ref<Learner> | null     # 个性化生成的材料记录是为谁生成的
  created_at: datetime
```

```yaml
Scenario:
  id: ulid
  title: string                # 如"向同事解释项目延期"
  target_cefr: enum[...]
  goal_types: list<enum>       # 对应 Learner.goals.type
  agent_role: string           # Agent 扮演谁
  learner_role: string
  objectives: list<string>     # 学习者在对话中需要完成的事，如"说明延期原因""提出新日期"
  target_items: list<ref<LexicalItem>>   # 希望诱导学习者用出来的词项
  target_error_codes: list<ErrorCode>    # 希望制造机会让学习者练的错误点
  target_can_do_ids: list<ref<CanDoStatement>>
  scripted_events:             # Agent 在对话中必须制造的事件，供 SI 类 can-do 验证
    - kind: enum[misunderstand, digress, unexpected_question, hard_sentence, counterargument, compliment]
      at_turn: int | null      # 大约第几轮触发；null 为 Agent 自选
      payload: string          # 事件内容，如要跑题到什么、反驳什么
  created_at: datetime
```

### 2.9 DailyPlan

```yaml
DailyPlan:
  learner_id: ref<Learner>
  date: date
  minutes_budget: int
  blocks:
    - order: int
      type: enum[listen, shadow, retell, converse, review]
      minutes: int
      material_id: ref<Material> | null
      scenario_id: ref<Scenario> | null
      review_items: list<ref<LexicalItem>>      # 本块要"顺带"复习的词项
      review_error_codes: list<ErrorCode>        # 本块要制造机会的错误点
      target_can_do_ids: list<ref<CanDoStatement>>   # 本块要验证的 can-do，1–3 条
      rationale_zh: string     # 一句话解释为什么排这个（展示给学习者）
      status: enum[pending, done, skipped]
  generated_at: datetime
```

---

## 3. 入门测评（Placement）

新用户的模型是空的。入门测评在 10 分钟内给出 listening 和 speaking 的初始 `level`（`source: placement`），并写入前几条 ErrorInstance 和 PhonemeProfile。

| 步骤 | 时长 | 产出 |
|---|---|---|
| 自评 | 1 分钟 | 四个技能各选一个 CEFR 标签，作为先验（`source: self_report`） |
| 听力阶梯 | 3 分钟 | 从自评级别起，播放 3–4 段 20–30 秒材料，每段 2 道理解题（1 detail + 1 discrimination）；全对升一级、全错降一级，直到定位。每段按该等级的一条 L 类 can-do 产出一个证据事件 |
| 发音探针 | 2 分钟 | 朗读 12 个句子，覆盖错误清单第 7 节规定的 T1 音段代码（P01、P02、P05、P07、P08、P10）和韵律代码（P20–P23）；产出 PhonemeProfile 初值和 PH-A1/A2 类证据 |
| 开放口语 | 3 分钟 | 两个提示（讲一件上周发生的事 / 介绍一位家人），Agent 按 can-do 清单判定 2–4 条 SP 类证据，并提取 ErrorInstance；提示的诱导目标见错误清单第 7 节 |
| 词汇抽样 | 1 分钟 | 从 Oxford 5000 各级抽 8 词做"是/否认识"判断，估计词汇量，批量初始化 LexicalKnowledge.recognition |

入门测评给出 `prior_level`（`prior_weight = 6`），自评给出的先验 `prior_weight = 2`。`confidence` 上限 0.5；此后每次会话的证据按 4.4 的融合规则逐步覆盖先验。

---

## 4. 更新规则：一次会话结束后发生什么

### 4.1 转写要求（前置条件）

错误检测的质量取决于转写是否"原样"。通用 ASR（含 Whisper）会自动把 "he go to school yesterday" 修成 "he went to school yesterday"，直接吞掉 G04 错误。因此：

- 学习者语音的转写必须使用**低归一化**配置：关闭标点和大小写归一化之外的后处理，优先用带词级置信度的模型（whisperX），并保留 n-best
- 语法类错误（G/L 类）检测由 LLM 在原样转写 + 音频片段（可回放）基础上进行，置信度 < 0.6 的实例不进入统计
- 发音类错误（P 类）不走 ASR 文本，走音素评测器（OpenPronounce），输入是音频 + 目标文本

**对话会话（converse）里的实时与事后两条链路**（我的选择）：
- 实时链路：pipecat 流式 ASR（带归一化）→ LLM 对话。Agent 在对话中按 `correction_style` 做 recast / explicit 纠错时，依据的是实时转写 + LLM 的即时判断；每次纠错写一条 `status: provisional`、`detected_by: asr_llm_realtime` 的 ErrorInstance。
- 事后链路：会话结束后，对完整录音跑 whisperX 低归一化转写（权威 `transcript.text`）+ 音素评测 + LLM 错误检测。批处理发现的实例直接 `confirmed`；与 provisional 实例在同一话语、同一代码上重叠的，合并为一条 confirmed；批处理找不到对应的 provisional 实例标 `discarded`。
- `summary_zh` 等批处理完成后生成，目标延迟 < 60 秒；UI 在这期间显示"正在整理复盘"。
- 统计（ErrorPattern、SkillEstimate）只读 confirmed 实例。

这是 M1 必须验证的技术风险，见第 6 节。

### 4.2 各类会话的产出

| 会话类型 | 写入 |
|---|---|
| listen | 任务结果 → CanDoEvidence（L 类，按 `target_can_do_ids`）；`Material.lexical_items` 中的词项 → recognition 至少升到 exposed，其所在题答对 → recognized；答错题的 `item_ids` → 创建 FSRS 卡（`missed_in_listening`）；答错题的 `error_codes` → ErrorInstance（H 类，`utterance_id` 指向材料话语） |
| shadow | 每句的音素评分 → PhonemeProfile；低分音素 → ErrorInstance（P 类）；韵律问题 → ErrorInstance（P20–P25）；→ CanDoEvidence（PH 类） |
| retell | 原样转写 → ErrorInstance（G/L 类）；内容覆盖率、流利度指标 → CanDoEvidence（SP 类）；材料词项被正确用出 → production 升级 |
| converse | 同 retell，另加 CanDoEvidence（SI 类，依赖 `scripted_events` 是否触发）、I 类错误；Scenario.target_items 与 target_error_codes 的命中情况 → FSRS 评分；实时/事后两条链路的合并见 4.1 |
| review | 本质上是带特定 target 的 shadow / converse，产出同上 |

### 4.3 词项与错误模式的 FSRS 评分规则

Agent 在会话结束时为每个"到期且本次出现过"的 FSRS 卡自动打分：

| 遭遇结果 | 评分 |
|---|---|
| 词项：被提示后仍未用出 / 用错；错误模式：机会出现且犯错 | again |
| 词项：被提示后用出；错误模式：机会出现、犯错但自我纠正 | hard |
| 词项：自发用出且正确；错误模式：机会出现且未犯错 | good |
| 词项：自发、正确、且在非预期场景中用出；错误模式：连续 3 次机会均未犯错 | easy |

到期但本次没有出现的卡不打分，顺延到下一次计划。

### 4.4 SkillEstimate 的更新

每次新增 CanDoEvidence 后重算对应技能行（listening / speaking_production / speaking_interaction / phonology），然后派生 speaking 行。

**证据等级（evidence_level）**
1. 取该技能行近 90 天的全部 CanDoEvidence，按 statement 的 cefr 分组
2. 对每个等级 k，算加权通过率 `pass_rate_k = Σ(weight × score) / Σ(weight)`，其中 demonstrated = 1、partial = 0.5、failed = 0；`n_k` 为该等级的证据条数
3. 若存在满足 `pass_rate_k ≥ 0.7 且 n_k ≥ 4` 的等级，取其中最高者为 k，`evidence_level = k + 0.95 × pass_rate_{k+1}`（k+1 无证据时取 0）；上界 0.95 保证不会越级
4. 否则 `evidence_level = null`

**与先验融合**
- `n` = 近 90 天证据总条数
- `evidence_level` 为 null 时：`level = prior_level`（没有先验则 1.0），`source` 保持 placement / self_report
- 否则：`level = (prior_weight × prior_level + n × evidence_level) / (prior_weight + n)`，`source = inferred`。placement 的 `prior_weight = 6`，意味着约 6 条证据后先验与证据各占一半，20 条后先验影响低于四分之一
- `confidence = min(1, (n + prior_weight) / 36) × 一致性系数`，一致性系数在相邻等级 pass_rate 单调递减时为 1，出现倒挂时为 0.7

**派生**
- speaking 行：`level = min(SP.level, SI.level)`，`confidence = min(SP.confidence, SI.confidence)`，`source = derived`
- phonology 行：不算 level，`sub_score = Σ(weight × score) / Σ(weight)`，取近 90 天全部 PH 类证据；UI 作为口语的子指标展示

这是一个刻意简单的规则，便于解释给学习者。M3 可以换成 IRT 之类的模型，但要保留"能解释"这一点。

### 4.5 ErrorPattern 的 trend 与 resolved

**trend**
- 有机会数的代码：比较 `error_rate_7d` 与 `error_rate_30d`；差值 > 0.1 为 worsening，< −0.1 为 improving，否则 stable；`opportunities_30d < 10` 或 `opportunities_7d < 3` 时为 insufficient_data
- 无机会数的代码（清单中标"不可统计"）：比较 `count_7d × 30 / 7` 与 `count_30d`；前者高于后者 1.5 倍为 worsening，低于 0.5 倍为 improving，否则 stable；`count_30d < 5` 时为 insufficient_data

**resolved**
- G / L / I 类及韵律 P20–P24：`opportunities_30d ≥ 10` 且 `error_rate_30d < 0.1`
- 音段 P01–P11：取错误清单第 8 节映射到该代码的全部音素（按位置）的 `accuracy_mean_30d` 加权平均（按 attempts 加权）> 0.85，且总 attempts ≥ 20
- 不可统计的代码（P25、G14、G18、L01、L04、L06、L10、H08、H09、H11）：不自动 resolved，只能由开发者手动标记
- resolved 后 FSRS 卡进入长间隔，不删除

### 4.6 证据事件的粒度（评审问题 1 的回答）

can-do 清单"验证"列描述的是**完整协议**的样本量和阈值，例如 L-B1-01 "4 段各 3 题，正确 ≥ 9/12"。一次会话不要求跑完整个协议：

- 每条 can-do 的 `min_sample` 规定单次会话构成一个证据事件所需的最小样本（听力类通常是 1 段材料 + 3 题，互动类是 1 个情境或 1 个 scripted_event）
- 单次事件的 verdict 按**比例**判：达到验证列阈值比例（如 9/12 = 75%）为 demonstrated，达到阈值比例的 80% 以上为 partial，否则 failed；样本太小导致比例跳变时向上取整
- `validated` 要求 ≥ 3 次 demonstrated 事件，分布在 ≥ 2 个会话、≥ 2 段不同材料/情境，这本身就把"多材料"要求分摊到多天
- 编排器通过 `target_can_do_ids` 声明每次会话要验证哪 1–3 条，材料生成器和场景生成器据此配题、配 scripted_events

这样 placement 的听力阶梯每段材料都能产出一个 L 类事件，一个 15 分钟计划一天能产出 3–6 个事件。

### 4.7 机会数的统计范围（评审问题 7 的回答）

不是每个会话对全部 66 个代码数机会。会话后批处理只对下列代码统计 opportunities：

1. 全部 T1 代码中可统计的（P 类由音素评测器天然给出，G/L/I 类需 LLM 标注）
2. 该学习者已有 ErrorPattern 的代码
3. 本次会话 `target_error_codes` 中的代码

合计上限 15 个代码；超出时按 T1 > 有 ErrorPattern > target 的顺序截断。其余代码只记 ErrorInstance 次数，`opportunities` 为 null。随着学习者错误档案收敛，被统计的集合会自然变小。

---

## 5. 内容生成与计划编排从模型里读什么

### 5.1 生成一段听力材料

输入：
- `target_cefr` = `floor(listening.level)`，若 `listening.level` 小数部分 > 0.7 则取上一级（i+1）
- `topic_tags` 从 `interests` 加权随机
- 必须包含：到期的 `review_reason = missed_in_listening` 词项（最多 5 个）
- 词汇约束：`cefr_level ≤ target_cefr` 的词占比按 can-do 清单第 1 节的覆盖要求（A1–A2 ≥ 95%，B1 ≥ 92%，B2 ≥ 90%）；其余为"新词"，数量 A1 为 1–3、A2 为 3–5、B1 以上为 5–8，并全部写入 `Material.lexical_items`
- `lexical_items` 只收录 5–15 个目标词项（新词 + 到期复习词 + 本等级关键词块），不是材料的全部 token；LexicalKnowledge 只为这些词项建行
- 语速目标：按 can-do 清单中该等级的 wpm 区间
- 听力难点注入：按 ErrorPattern 中 H 类代码，在材料中刻意包含对应现象（如连读、弱读 can/can't），并为每个注入点配一道 dictation 或 discrimination 题，题的 `error_codes` 指向该 H 码
- 配题：按 `target_can_do_ids` 的 `min_sample` 配理解任务，题的 `item_ids` 指向所考词项

### 5.2 选择 / 生成一个对话场景

- `target_cefr` 同上但基于 speaking.level
- `goal_types` 匹配 `Learner.goals`
- `target_items`：到期的 `failed_in_production` / `mispronounced` 词项，最多 5 个
- `target_error_codes`（唯一的选取规则，错误清单第 8 节引用本节）：
  1. 候选：ErrorPattern 中 `remediation.status ≠ resolved` 的 G / L / I 类代码
  2. 打分：`score = tier_weight × severity_30d × stubbornness`，其中 `tier_weight` T1=3、T2=2、T3=1；`severity_30d` 有机会数时为 `error_rate_30d`，否则为 `min(1, count_30d / 10)`；`stubbornness` 在"当前 speaking 等级已超过该代码的预期消退等级"时为 1.5，否则为 1
  3. 取 score 最高的 3 个；FSRS 到期的代码强制进入（挤掉分最低的）
  4. Scenario 的 objectives 要自然地制造使用机会（例如要练 G04 过去时，就让学习者"讲一下上周发生了什么"）
- `target_can_do_ids`：优先当前 speaking 等级中状态为 not_started / emerging 的 SI 条目，其次上一等级 emerging 的；1–3 条，并据此生成 `scripted_events`

### 5.3 当日计划

默认 15 分钟的模板（可按 time_budget 缩放）：

| 块 | 分钟 | 内容 |
|---|---|---|
| listen | 3（A1–B1）/ 5（B2） | 一段新材料 + 按 `target_can_do_ids` 的 min_sample 配 3 题左右；B2 材料长 2–3 分钟，块扩到 5 分钟，总时长按 time_budget 缩放其他块 |
| shadow | 4 | 同一材料中挑 4–6 句，优先含低分音素的句子 |
| retell | 3 | 复述该材料 |
| converse | 5 | 与材料相关的场景对话，注入 target_items / target_error_codes / scripted_events |

每天的 `rationale_zh` 要能回答"为什么今天是这个"，例如："你上周三次把 th 说成 s，今天的跟读句子里有 6 个 th。"

---

## 6. M1 需要验证的风险

| 风险 | 验证方式 |
|---|---|
| ASR 自动纠正吞掉语法错误 | 用 20 条含典型 G 类错误的录音测 whisperX 低归一化配置，统计错误保留率；目标 ≥ 80% |
| OpenPronounce 对中文口音的音素评分是否稳定 | 同一人同一句录 5 遍，评分标准差 < 0.1 |
| LLM 判定 can-do 的一致性 | 同一转写判 5 次，verdict 一致率 ≥ 80% |
| 词级时间戳精度是否够逐句跟读 | 抽 50 句，边界误差 < 150 ms 的比例 ≥ 90% |
| 实时链路的 recast 误报率 | 20 段对话，provisional 实例被批处理 discarded 的比例 ≤ 20% |
| 会话后批处理延迟 | 5 分钟对话录音，转写 + 评测 + LLM 检测 + 复盘生成 < 60 秒 |

---

## 7. 未决问题（留给后续里程碑）

- 读写两个技能的 can-do 与证据来源（M4）
- 多设备同步与本地优先存储的冲突处理（M3）
- 词项"自动（automatic）"状态是否需要衰减（长期不用是否降级）
- 学习者是否可以手动修正模型（"这个词我其实会"），以及如何防止自评污染证据
- 本地优先存储何时、如何从"可导出可删除"升级回来（见 0.1a）
- C1 材料所需的多口音、多说话人、噪声注入能力（见 0.1a）
