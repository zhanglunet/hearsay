# 中文母语者英语错误清单（L1 = zh-CN）

日期：2026-10-22
状态：草稿 v0.2（已修订）
归属：[M0 学习者模型设计](2026-10-22-m0-learner-model.md) 的配套静态数据；`ErrorInstance.code` 和 `ErrorPattern.code` 的取值范围

---

## 0. 怎么读这份清单

- 这是**检测目标清单**，不是教学大纲：每一条都要能被某个检测器（音素评测器、LLM 对转写的判断、规则）识别，并能被某种练习针对。
- 代码格式：`<类别字母><两位序号>`。五个类别：
  - **P**（Pronunciation）发音：P01–P11 音段，P20–P25 韵律
  - **G**（Grammar）语法
  - **L**（Lexis）词汇与用法
  - **H**（Hearing）听力感知难点——学习者听不出来的东西
  - **I**（Interaction）互动与语用
- 代码一旦发布不再改含义。要拆分或合并，作废旧码、发新码。
- 保留码 `X00`：检测器发现但无法归入现有代码的现象。只记实例，不算模式，由开发者在夜间报告中决定是否发新码。
- 本清单就是主文档所需的 **ErrorCode 静态定义表**：每行给出 code、tier（优先级）、expected_fade_level（预期消退等级）、detector（检测）、exercises（练习）、opportunity_rule（机会数口径）。M1 把它转成 YAML 时按此列名。
- **优先级**分三档，依据是"中文母语者的出现频率 × 对沟通的影响"：
  - **T1**：高频且常导致误解或明显不自然，入门即处理
  - **T2**：高频但多数不影响理解，B1 前后处理
  - **T3**：中低频或只影响地道程度，B2 后处理
- "预期消退等级"是指按 CEFR 常态，到该等级的学习者这个错误应降到偶发。它用于计划编排器判断"这个错误现在值不值得练"。
- 每条都配一个**检测方式**和一个**针对性练习**。练习类型缩写：`MP` 最小对立对跟读，`SH` 句子跟读，`RC` 对话中重述（recast），`EL` 诱导任务（在场景里制造使用机会），`DL` 听写，`DC` 听辨二选一，`EX` 显性讲解（只在复盘中）。

关于"机会数（opportunities）"：ErrorPattern 需要分母才能算错误率。本清单对每条给出机会数的统计口径；写"不可统计"的条目只记次数，不算率。

---

## 1. 发音 — 音段（P01–P11）

中文（普通话）的音系没有 /θ ð v z ʒ/ 等音，没有浊塞音（b/d/g 在普通话里是不送气清音），音节结构基本是 (C)V(N)，词尾只允许 /n ŋ/。这决定了下面大部分问题。

| 代码 | 名称 | 现象 | 典型例子 | 优先级 | 预期消退 | 检测 | 练习 | 机会数口径 |
|---|---|---|---|---|---|---|---|---|
| P01 | /θ/ /ð/ 替换 | /θ/→/s/ 或 /f/，/ð/→/z/ 或 /d/ | think→sink，this→dis/zis，three→free | T1 | B1 | 音素评测器 TH/DH 得分；替换方向从最近音素读出 | MP（think/sink, they/day）、SH | 目标文本中 TH/DH 音素数 |
| P02 | /v/→/w/ | 唇齿擦音读成双唇近音 | very→wery，video→wideo | T1 | B1 | 音素评测器 V | MP（vest/west, vine/wine） | V 音素数 |
| P03 | /n/ /l/ 混淆 | 主要见于部分南方方言背景；此外词尾 dark /l/ 常读成 /u/ 或脱落 | night→light；feel→"fiu"，people→"peopo" | T2 | B1 | 音素评测器 N/L，按位置分；词尾 L 单独统计 | MP（night/light）、SH（词尾 l 句） | N、L 音素数（分位置） |
| P04 | /r/ 问题 | 词首 /r/ 卷舌过重或读成 /l/；词尾 /r/（美音）缺失 | rice→lice（部分方言）；car→"ca" | T3 | B2 | 音素评测器 R（分位置） | MP（rice/lice, right/light） | R 音素数 |
| P05 | 词尾辅音脱落或加元音 | 中文音节不允许大多数词尾辅音，于是吞掉或加 /ə/ | bad→"ba"/"bad-uh"，good night→"goo-nigh" | T1 | A2 | 音素评测器：词尾位置辅音得分 + 时长异常（加元音会多出一个音段） | SH（词尾辅音密集句）、MP（bad/bat 需先有尾音） | 词尾辅音数 |
| P06 | 辅音丛简化 | 两个以上辅音相连时省略其一 | sixths，texts→"tex"，world→"word" | T2 | B1 | 音素评测器：丛内各音素得分 | SH（辅音丛句） | 辅音丛数 |
| P07 | 词尾浊塞音清化 / 长度不分 | bad/bat、big/pig、dog/dock 词尾 b-p、d-t、g-k 不分；配合前元音长度也不分 | bad→bat，cab→cap | T2 | B1 | 音素评测器 B/D/G 词尾 + 前元音时长 | MP（bad/bat, cab/cap, dog/dock） | 词尾浊塞音数 |
| P08 | 元音对立缺失 | /iː/–/ɪ/（sheep/ship）、/e/–/æ/（bed/bad）、/ʌ/–/ɑː/（cut/cart）、/ʊ/–/uː/（full/fool）、/æ/–/ʌ/（cat/cut） | sheep→ship，bad→bed | T1 | B1 | 音素评测器 IY/IH、EH/AE、AH/AA、UH/UW | MP 五组 | 对应元音数 |
| P09 | /z/ /ʒ/ /dʒ/ 混淆 | /z/ 读成 /s/；/ʒ/ 读成 /dʒ/ 或 /ʃ/ | zoo→soo，usually→"uzhually"→"ujually"，pleasure | T3 | B2 | 音素评测器 Z/ZH/JH | MP（zoo/sue, pleasure/pledger） | Z、ZH、JH 音素数 |
| P10 | 语法性词尾 -s/-ed 不发音 | 复数、第三人称单数、过去式的词尾被吞掉（兼有语法与发音属性；本码只记"知道要加但没发出"的情况，与 G02–G04 的区分见注） | books→"book"，walked→"walk" | T1 | A2 | 音素评测器：词尾 S/Z/IZ、T/D/ID 得分，且转写层 LLM 判断该处语法上应有词尾 | SH（词尾 -s/-ed 密集句） | 语法上要求 -s/-ed 的词数 |
| P11 | /h/ 过重或词尾 /ŋ/→/n/ | /h/ 读成软腭擦音 /x/；词尾 /ŋ/ 读成 /n/（部分方言）。注：/n/ /l/ 混淆属 P03 | he→"khe"，sing→sin | T3 | B2 | 音素评测器 HH；词尾 NG 得分 | MP（sing/sin, thing/thin） | HH、词尾 NG 音素数 |

**P10 与 G02–G04 的区分**：当学习者在同一会话中其他位置能正确产出 -s/-ed，而某处缺失且音素评测显示词尾音段弱或无，记 P10；当学习者系统性不加（转写层也没有），记 G 类。两者都记时取置信度高者。

## 2. 发音 — 韵律（P20–P25）

普通话是音节计时（每个音节时长接近）且每个音节有声调。英语是重音计时，非重读音节压缩，功能词弱读。这是中文母语者"每个词都说清楚了但听起来不像英语、也听不懂母语者"的根源，同时影响说和听。

| 代码 | 名称 | 现象 | 典型例子 | 优先级 | 预期消退 | 检测 | 练习 | 机会数口径 |
|---|---|---|---|---|---|---|---|---|
| P20 | 词重音错位 | 多音节词重音放错，常见于把重音放在第一音节或按中文习惯均匀分布 | PHOtography→phoTOgraphy，deVElop→DEvelop，comFORtable | T2 | B1 | 对齐后比较各音节的时长/能量/基频峰值与词典重音位置 | SH（重音词卡）、EX | 多音节词数 |
| P21 | 无弱化元音 | 非重读音节不弱化为 schwa，每个音节读满 | about→"a-BOUT"（a 读成 /æ/）；banana 三个 a 都一样 | T1 | B1 | 非重读音节时长 / 重读音节时长 > 0.8；元音评测器在非重读位置检出满元音 | SH（schwa 密集句）、EX | 非重读音节数 |
| P22 | 句子重音平均化 | 功能词（a, the, to, of, and, can）不弱读，内容词不突出 | "I WANT TO GO TO THE STORE" 每词等重 | T1 | B2 | 功能词时长/内容词时长 > 0.8 | SH（节拍跟读，先敲重音再读） | 功能词数 |
| P23 | 语调模式偏差 | 陈述句末不降或上扬；疑问句不升；逐词有"声调"导致句调碎 | 陈述句听起来像在问；列举时每项都降 | T2 | B1 | 基频轮廓：句末斜率、句内基频跳变频率 | SH（语调模仿）、DC（听辨问/陈） | 句数 |
| P24 | 无连读 / 逐词断开 | 词与词之间停顿，不做辅音-元音连读、同化、省音 | an apple→"an. apple"；want to 不变 wanna | T2 | B2 | 对齐后词间静音 > 100ms 的比例；连读点是否出现连接 | SH（连读标记跟读） | 连读点数（辅音结尾 + 元音开头） |
| P25 | 节奏：音节计时 | 整体听起来"一字一顿"，无重音节拍 | 各音节时长的变异系数过低 | T2 | B2 | 音节时长变异系数（nPVI）低于阈值 | SH（节拍跟读）、EX | 不可统计（整段打分） |

## 3. 语法（G）

主要来源是中文的类型学特征：无冠词、无形态变化（无复数、无时态屈折、无一致）、话题优先、"虽然……但是"类成对连词、"有"字句对应 there be、量词系统与可数性不对应。

| 代码 | 名称 | 现象 | 错误 → 正确 | 优先级 | 预期消退 | 检测 | 练习 | 机会数口径 |
|---|---|---|---|---|---|---|---|---|
| G01 | 冠词缺失 / 误用 | 中文无冠词，a/an/the 省略最常见；其次 the 过度使用于泛指 | "I bought car" → "I bought a car"；"I like the music"（泛指）→ "I like music" | T1 | B2（C1 仍有残余） | LLM 对转写判断每个名词短语的冠词需求 | RC、EL（描述物品 / 讲故事） | 名词短语数 |
| G02 | 复数标记缺失 | 中文名词无复数屈折 | "two book" → "two books"；"many people" 正确但 "many person" | T1 | B1 | LLM：数量词 / 语境要求复数的名词 | RC、EL（数数 / 描述场景） | 应为复数的名词数 |
| G03 | 第三人称单数 -s 缺失 | 一般现在时 he/she/it 动词不加 -s | "she go to work" → "she goes to work" | T1 | B1 | LLM：第三人称单数主语 + 一般现在时动词 | RC、EL（介绍他人日常） | 三单现在时动词数 |
| G04 | 过去时标记缺失 | 中文用"了/过"和时间词表达，不改变动词；叙述中动词保持原形 | "yesterday I go to the park and see my friend" → went / saw | T1 | B1 | LLM：过去时间语境 + 原形动词 | RC、EL（讲昨天 / 上周） | 过去语境中的动词数 |
| G05 | 时态体系混用 | 现在完成 vs 一般过去；一般现在 vs 现在进行；将来表达 | "I have been to Shanghai last year" → "I went to..."；"I am agree" | T2 | B2 | LLM | RC、EL（讲经历 vs 讲具体时间点的事） | 动词短语数 |
| G06 | 系动词 / 助动词问题 | 漏掉 be（"He very tall"）；多加 be（"I am agree"）；"can" 后加 to | "He very tall" → "He is very tall"；"I am agree" → "I agree" | T1 | A2 | LLM | RC、EL（描述人） | 谓语数 |
| G07 | 可数 / 不可数混淆 | 中文量词系统不对应英语可数性 | "many informations" → "a lot of information"；"an advice" → "a piece of advice"；"a bread" | T2 | B2 | LLM：不可数名词 + 复数/不定冠词 | RC、EX | 不可数名词出现数 |
| G08 | 介词错误 | 时间/地点 in/on/at；动词搭配介词多加或漏掉 | "in Monday" → "on Monday"；"listen music" → "listen to music"；"discuss about" → "discuss" | T2 | B2 | LLM | RC、EL | 介词短语数 + 需介词的动词数 |
| G09 | 语序 | 副词位置（"I very like it"）；疑问句不倒装（"You like it?" "Why you do this?"）；时间地点顺序 | "I very like it" → "I like it very much"；"Why you say that?" → "Why do you say that?" | T1 | B1 | LLM | RC、EL（提问任务） | 句数 |
| G10 | 代词：性别 / 格 / 省略 | 他/她/它同音导致 he/she 口头混用；"it" 作主语省略（"Is very important"） | "My mother... he is a teacher" → she；"Is raining" → "It is raining" | T1 | B1 | LLM：代词与先行词性别；无主句 | RC、EL（讲家人） | 第三人称代词数 + 需 it 主语的句数 |
| G11 | 成对连词双标 | 中文"虽然……但是""因为……所以"直译 | "Although it was late, but I went" → 去掉 but；"Because I was tired, so I slept" | T2 | B1 | 规则（although...but / because...so 同句共现）+ LLM 确认 | RC、EX | 让步/因果复句数 |
| G12 | there be / have 混用 | 中文"有"同时表存在和拥有 | "Here have many people" → "There are many people here"；"My city has many people" 正确 | T2 | B1 | LLM | RC、EL（描述地方） | 存在句数 |
| G13 | 比较结构 | 双重比较级；than 后结构 | "more better" → "better"；"than me do" | T3 | B2 | LLM | RC | 比较结构数 |
| G14 | 话题-述题结构直译 | 把中文话题句搬进英语，产生悬垂话题和复指代词 | "This book, I like it very much" → "I like this book very much"；"My hometown, the weather is good" | T2 | B2 | LLM：句首名词短语无语法角色 | RC、EX | 不可统计（按句判断，记次数） |
| G15 | 关系从句 | 关系代词缺失或复指 | "The man I met him yesterday" → "The man I met yesterday"；"the book which I read it" | T3 | B2 | LLM | RC、EL（描述人/物） | 关系从句数 |
| G16 | 条件与虚拟 | 虚拟语气不用过去形式 | "If I am you, I will..." → "If I were you, I would..." | T3 | C1 | LLM | RC、EL（假设性问题） | 条件句数 |
| G17 | 否定疑问的回答 | 中文"是/不是"对的是命题真假，英语 yes/no 对的是事实 | "Don't you like it?" — "Yes."（意为"对，我不喜欢"）→ "No, I don't." | T2 | B2 | LLM：否定疑问后 yes/no 与后续内容矛盾 | DC、RC、EX | 否定疑问回答数 |
| G18 | 被动与使役 | 该用被动不用；"让/使"直译为 let/make 误用 | "The meeting cancelled" → "was cancelled"；"let me very happy" → "makes me very happy" | T3 | B2 | LLM | RC | 不可统计 |

## 4. 词汇与用法（L）

| 代码 | 名称 | 现象 | 错误 → 正确 | 优先级 | 预期消退 | 检测 | 练习 | 机会数口径 |
|---|---|---|---|---|---|---|---|---|
| L01 | 逐字直译（中式搭配） | 动宾/形名搭配按中文搬 | "open the light" → "turn on the light"；"eat medicine" → "take medicine"；"big rain" → "heavy rain"；"play phone" → "be on my phone" | T1 | B2 | LLM：搭配不当且能映射到中文表达 | RC、EL（词块卡） | 不可统计 |
| L02 | 轻动词搭配错误 | make/do/have/take/give 与名词的固定搭配 | "make a research" → "do research"；"do a decision" → "make a decision"；"have a rest" 正确 | T2 | B2 | LLM | RC、词块 FSRS | 轻动词短语数 |
| L03 | 近义词混用 | 中文一个词对应英语多个：说（say/tell/speak/talk）、看（see/look/watch）、听（hear/listen）、借（borrow/lend）、带（bring/take） | "he said me" → "he told me"；"I borrow you my pen" → "lend" | T1 | B1 | LLM | RC、EX、词块 FSRS | 对应动词出现数 |
| L04 | 语体不当 | 教科书式过正式或场合不配 | "How do you do" 日常问候；给朋友发消息用 "I would like to inquire" | T3 | B2 | LLM 结合场景语体设定 | RC、EX | 不可统计 |
| L05 | 安全词过度依赖 | very / good / thing / many / a lot 过多；形容词贫乏 | "very very good" → "excellent / really good" | T2 | B2 | 规则：very/good/thing/many 合计 > 3/百词 | EL（替换任务）、词块 FSRS | 百词 |
| L06 | 虚假对应词 | 词义被中文对应词带偏 | "convenient"（"方便"用于人："Are you convenient?"）→ "Is this a good time for you?"；"cost performance" → "value for money"；"colleague" vs "classmate/coworker" | T2 | B2 | LLM | RC、EX | 不可统计 |
| L07 | 数字换算 | 万/亿体系换算错；大数停顿位置错 | 三万 → "three ten-thousand" → "thirty thousand"；一亿 → "one hundred million" | T2 | B1 | LLM + 规则（数字转写） | DL（数字听写）、EL（报数） | 千以上数字数 |
| L08 | 模糊限制语偏差 | "maybe / I think / a little" 过度使用削弱陈述；或完全不用导致过硬 | "Maybe I think it's good" → "I think it's good"；拒绝时直接 "No" | T3 | C1 | 规则（maybe/I think 频率）+ LLM 判断场合 | RC、EX | 百词 |
| L09 | 话语标记贫乏 | 只会 "and then"、"so"；填充词用中文"嗯/那个" | "and then... and then..." → "after that / meanwhile / anyway" | T2 | B2 | 规则：标记种类数 / 中文填充词检出 | SH、EL | 话轮数 |
| L10 | 词形错误 | 词性混用：形容词当名词、名词当动词 | "I feel very boring" → "bored"；"it's very convenience" → "convenient" | T2 | B1 | LLM | RC、词块 FSRS | 不可统计 |

## 5. 听力感知难点（H）

H 类不是"学习者说错了什么"，而是"学习者听不出什么"。它来自听力会话中的理解题错误和听写错误，用于指导材料生成器刻意注入对应现象。H 与 P 多数一一对应（说不出的通常也听不出），但分开记，因为训练方式不同。

| 代码 | 名称 | 现象 | 例子 | 优先级 | 预期消退 | 检测 | 练习 | 机会数口径 | 对应 P 码 |
|---|---|---|---|---|---|---|---|---|---|
| H01 | 连读、省音、同化听不出 | 把一个词流听成一个陌生词 | "did you"→/dɪdʒə/；"a lot of"→/əlɑɾə/；"next day" 的 t 省音 | T1 | B2 | 听写：连读点处的词错误 | DL、SH（先说后听） | 材料中连读点数 | P24 |
| H02 | 弱读形式听不出 | can/can't 对立；功能词 of/to/for/them/have 弱读成 /ə/ 后听不出 | "I can go" vs "I can't go"；"should've" | T1 | B1 | 听写 / DC | DC（can/can't）、DL | 弱读功能词数 | P21、P22 |
| H03 | 数字快速听辨 | 13/30、15/50、17/70 等；大数的千/百万分段 | "fifteen" vs "fifty" | T1 | A2 | DL（数字） | DL、DC | 数字数 | P20 |
| H04 | 口语缩约形式 | gonna / wanna / gotta / dunno / kinda / lemme；I'd've | "I'm gonna" 听成 "I'm going" | T2 | B2 | 听写 | DL、SH | 缩约数 | P24 |
| H05 | 元音对立听辨 | 与 P08 同组的最小对立对在听时也分不出 | ship/sheep，bad/bed | T1 | B1 | DC | DC、MP | 对立对数 | P08 |
| H06 | 词重音导致的词识别失败 | 自己重音错的词听不出母语者的读法 | 把 "comFORtable" 听成陌生词 | T2 | B1 | 听写：多音节词错误 | SH、DL | 多音节词数 | P20 |
| H07 | 句重音与焦点 | 听不出对比重音承载的意义 | "I said TUESday" 中的纠正意图 | T2 | B2 | 理解题（inference） | DC | 对比重音句数 | P22 |
| H08 | 语调传递的态度 | 分不清反问、讽刺、不确定 | "Really?"（怀疑）vs "Really!"（惊喜） | T2 | B2 | 理解题 | DC | 不可统计 | P23 |
| H09 | 口音变体 | 英音 /ɑː/ /ɒ/，澳洲 /aɪ/，印度英语节奏等 | "can't" 英音 /kɑːnt/ | T3 | C1 | 理解题（按口音标记的材料） | 多口音 DL | 不可统计 | – |
| H10 | 短语动词与习语 | 逐词理解导致整体意思丢失 | "put up with"，"call it a day" | T2 | B2 | 理解题 / 词项 recognition 失败 | 词块 FSRS、DL | 短语动词数 | – |
| H11 | 语速过快时整体失去锚点 | 超过某 wpm 后理解率断崖式下跌 | 150 wpm 以上理解率 < 50% | T1 | B2 | 同一材料不同语速版本的理解率曲线 | 渐进加速 DL | 不可统计 | P25 |

## 6. 互动与语用（I）

| 代码 | 名称 | 现象 | 例子 → 更好的做法 | 优先级 | 预期消退 | 检测 | 练习 | 机会数口径 |
|---|---|---|---|---|---|---|---|---|
| I01 | 回应延迟过长 | 心里先翻译再说，对方说完到开口超过 3–4 秒 | 中位延迟 > 3 秒 | T1 | B1 | 规则：话轮间静音时长 | EL（限时回应）、SH（反应短语） | 话轮数 |
| I02 | 不请求澄清 | 听不懂时沉默或猜，不说 "Sorry, could you say that again?" | 设计听不懂的情境无澄清请求 | T1 | A2 | 规则：设计性难句后是否出现澄清短语 | EL（注入难句）、SH | 设计性难句数 |
| I03 | 回应过短 / 不展开 | 只答 yes/no 或一个词，不补充；对话靠对方推动 | "Do you like your job?" — "Yes." → "Yes, mostly. The hours are long, but..." | T1 | B1 | 规则：学习者话轮平均词数；LLM 判断是否展开 | EL（追问设计）、EX | 开放问题数 |
| I04 | 直接度 / 礼貌策略 | 请求用命令式，不加 could/would/please；拒绝直接 "No"；不说 "I'm afraid" | "Give me the menu" → "Could I have the menu, please?"；"I want..." → "I'd like..." | T1 | B1 | LLM 按场景判断礼貌度 | RC、EL（请求/拒绝场景） | 请求/拒绝行为数 |
| I05 | 反馈信号缺失 | 对方说话时没有 uh-huh / right / I see，对方不知道你在听 | 整段对话无 backchannel | T2 | B2 | 规则：backchannel 词检出 / 对方话轮数 | SH、EL | 对方话轮数 |
| I06 | 闲聊回避 / 直接进入正题 | 不会开场和收尾；被问 "How's it going?" 当真回答 | "How's it going?" — "I am fine, thank you, and you?" → "Pretty good, busy week. How about you?" | T2 | B2 | LLM 判断开场/收尾是否自然 | EL（small talk 场景）、SH | 对话数 |
| I07 | 称赞与感谢的回应 | 对称赞谦虚否认（"No no, not good"） | "Your English is great." — "No, no." → "Thanks, I've been practising." | T3 | B2 | LLM | EL、SH | 称赞数 |
| I08 | 打断与争取发言权 | 多人讨论中等待被点名；不会用 "Can I just add..." | 全程 0 次主动获得话轮 | T2 | B2 | 规则：多人场景中主动话轮数 | EL（三方场景） | 讨论数 |
| I09 | 自我纠正与修补缺失 | 说错后不修补，或用中文"呃、那个"填充 | 中文填充词 / 无 "I mean..." | T2 | B1 | 规则：中文填充词检出；LLM 判断修补 | SH（修补短语）、EX | 话轮数 |
| I10 | 中文混入 | 卡壳时直接说中文词 | "那个 report 我 send 了" | T1 | A2 | ASR 语言检测 | EL（屏蔽中文）、SP-B1-07 绕行训练 | 话轮数 |

## 7. 优先级汇总与入门探针覆盖

### T1（入门即处理，共 26 条）

| 类别 | 代码 |
|---|---|
| P | P01, P02, P05, P08, P10, P21, P22 |
| G | G01, G02, G03, G04, G06, G09, G10 |
| L | L01, L03 |
| H | H01, H02, H03, H05, H11 |
| I | I01, I02, I03, I04, I10 |

### 入门测评的发音探针（12 句）必须覆盖

- P01：≥ 4 个 /θ/ /ð/（think, this, three, they）
- P02：≥ 2 个 /v/（very, video）
- P05/P07：≥ 4 个词尾塞音（bad, bat, big, dog）
- P08：五组元音对立对各 1 对（sheep/ship, bed/bad, cut/cart, full/fool, cat/cut）
- P10：≥ 3 个 -s/-ed 词尾（books, walked, watches）
- P20：≥ 3 个三音节以上的词（photography, comfortable, development）
- P21/P22：≥ 2 句含多个功能词的句子（"I want to go to the store for a bottle of water."）
- P23：1 个一般疑问句 + 1 个陈述句

### 入门测评的开放口语（2 个提示）设计为诱导

- 过去时叙事提示（"讲一件上周发生的事"）→ G04, G01, G02, P10
- 描述人物提示（"介绍一位家人"）→ G03, G06, G10

## 8. 与学习者模型的关系

- `ErrorInstance.code` 取值限于本清单（含保留码 `X00`）。
- `ErrorPattern.opportunities_30d / _7d` 按"机会数口径"列统计，统计范围（不是每会话全部 66 条）见主文档 4.7；"不可统计"的代码 `error_rate` 为 null，`trend` 用次数粗估，规则见主文档 4.5。
- 口语场景的 `target_error_codes` 选取规则**只在主文档 5.2 定义**，本清单提供其所需的 tier 与预期消退等级。直觉上：T1 优先、错误率高优先、"当前等级已超过预期消退等级却仍在犯"的顽固错误再乘 1.5。
- H 类不进入 `target_error_codes`（那是口语场景的参数），而是进入材料生成器的"听力难点注入"参数，并通过 `Material.comprehension_questions[].error_codes` 回写 H 类 ErrorInstance。
- `PhonemeProfile.related_error_codes` 是多值的。音素（ARPAbet，含位置）到 P 码的映射：

| 音素（位置） | P 码 |
|---|---|
| TH, DH（任意） | P01 |
| V（任意） | P02 |
| N, L（词首、词中） | P03 |
| L（词尾） | P03, P05 |
| R（任意） | P04 |
| 任意辅音（词尾） | P05 |
| 辅音丛内各辅音 | P06 |
| B, D, G（词尾） | P05, P07 |
| D（词尾，且为 -ed 词尾） | P05, P07, P10 |
| IY, IH, EH, AE, AH, AA, UH, UW | P08 |
| Z, ZH, JH（任意） | P09 |
| S, Z（词尾，且为 -s 词尾） | P05, P10 |
| T（词尾，且为 -ed 词尾） | P05, P10 |
| HH（任意） | P11 |
| NG（词尾） | P11 |

  主文档 4.5 判 P01–P11 是否 resolved 时，取映射到该 P 码的全部音素行按 attempts 加权平均。

## 9. 数量汇总

| 类别 | 条目数 | T1 | T2 | T3 |
|---|---|---|---|---|
| P（音段） | 11 | 5 | 3 | 3 |
| P（韵律） | 6 | 2 | 4 | 0 |
| G | 18 | 7 | 7 | 4 |
| L | 10 | 2 | 6 | 2 |
| H | 11 | 5 | 5 | 1 |
| I | 10 | 5 | 4 | 1 |
| 合计 | 66 | 26 | 29 | 11 |
