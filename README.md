# Hearsay · 听说

> 一个为非英语母语者量身定制的英语听说陪练 Agent。
> 名字取自 **hear + say**，中文名「听说」——既是"听与说"两项核心技能，也是"道听途说"的双关：语言本来就是从别人嘴里听来、再从自己嘴里说出去的东西。

状态：M0 设计文档和 M1 风险验证已经完成（2026-10-23）。跟读原型只有最小切片，产品功能还没交付。对照见 [2026-10-24 状态清单](docs/design/2026-10-24-status-checklist.md)。

---

## 一、为什么要做它：多邻国的问题在哪

多邻国很会让人"每天打开 App"，但不太会让人"开口说话"。对一个成年的非母语学习者来说，它有几个结构性短板：

| 多邻国的做法 | 对听说能力的实际效果 |
|---|---|
| 固定课程树，所有人走同一条路 | 内容和你的水平、兴趣、职业无关，i+1（略高于当前水平）很难命中 |
| 以翻译题、选词题为主 | 练的是"认"，不是"听懂"和"说出来" |
| 语音题判定宽松，只看有没有说出单词 | 发音、连读、语调几乎得不到反馈 |
| 错题只在课程内复现 | 你昨天说错的句子，明天不会以新的场景再出现 |
| 用 XP、连胜、宝石衡量进度 | 学习者不知道自己"能做什么"了，只知道连胜几天 |
| 不认识你的母语 | 中文母语者的典型困难（th/s、l/n、词尾辅音、冠词、时态、单复数）没有针对性处理 |

Hearsay 的立场是：**成年人学外语，最稀缺的不是动力，而是"刚好适合我、且逼我开口的输入与输出机会"。** 所以个性化不是换个头像和主题色，而是让每一分钟的听、说材料都从"这个人"身上长出来。

## 二、核心思路：个性化到底指什么

### 1. 学习者模型（Learner Model）是一切的中心

Agent 维护一份持续更新的学习者画像，所有内容生成和练习安排都从它出发：

- **分技能水平**：听、说、读、写分别对应 CEFR 等级（A1–C2），不是一个总分
- **词汇与词块掌握度**：哪些词/短语"听得懂"、"说得出"、"只认识"，由测试 + 实际对话中的使用情况共同估计
- **错误档案（Error Profile）**：音素级发音问题、语法模式（时态、冠词、介词……）、L1 迁移错误，按出现频率和近期趋势排序
- **兴趣与场景**：你的职业、常聊的话题、要应付的真实场景（开会、点餐、面试、雅思口语……）
- **时间预算**：每天能给多少分钟，什么时候

### 2. 听 → 跟读 → 复述 → 对话：一条循环，而不是四种题型

每次练习围绕一段"刚好适合你"的材料展开：

1. **听**：按你的水平和兴趣生成或挑选 1–3 分钟的材料（对话、播客片段、短故事），带词级时间戳，可逐句回放、慢放、挡字幕
2. **跟读（Shadowing）**：逐句影子跟读，对比原声波形与你的录音，给出音素级发音、重音、连读反馈
3. **复述**：用自己的话把刚听的内容讲出来，Agent 评估内容覆盖度、流利度、语法，用"重述"（recast）而不是打断来纠错
4. **对话**：进入和材料相关的角色扮演场景，自由对话；Agent 根据你的水平控制自己的语速和词汇，并在对话结束后出一份"你说过的话"复盘

这条循环里，**说的时间要占一半以上**。

### 3. 从你自己的话里长出复习项

错过的词、说不出的表达、发错的音，自动变成间隔重复（FSRS）的复习卡，但复习的方式不是翻卡片，而是**在新的对话场景里再次被要求用出来**。Agent 记得你三天前把 "I have been to" 说成 "I have gone to"，会在今天的场景里制造一个需要用它的机会。

### 4. 母语感知（L1-aware）

第一版面向中文母语者。发音训练用针对中文母语者的最小对立对（minimal pairs）；语法纠错优先处理中文迁移错误；解释可以用中文，但练习永远用英文。

### 5. 进度用"能做什么"来表示

进度页展示的是 CEFR 的 can-do 描述（例如"能听懂语速正常的日常对话""能就熟悉话题做 2 分钟不间断陈述"），以及它们各自被你的实际表现验证了多少次。没有宝石。

### 6. 每天 15 分钟，由 Agent 排

根据学习者模型和今天的时间预算，Agent 自动组一份当日计划：几分钟听、哪段材料、复习哪些项、进哪个场景。你只需要打开然后开口。

## 三、非目标（第一版明确不做）

- 不做儿童向、游戏化的闯关
- 不做多语种，先把"中文母语 → 英语"做透
- 不做题库刷题（四六级/雅思真题），但场景可以覆盖雅思口语
- 不做社交 / 真人配对

## 四、开源项目调研（2026-10-22）

完整清单见 [docs/research/2026-10-22-github-open-source-survey.md](docs/research/2026-10-22-github-open-source-survey.md)。可直接复用的部分：

| 能力 | 推荐项目 | 许可证 | 备注 |
|---|---|---|---|
| 语音识别（含词级时间戳） | [m-bain/whisperX](https://github.com/m-bain/whisperX)、[SYSTRAN/faster-whisper](https://github.com/SYSTRAN/faster-whisper) | BSD-2 / MIT | 词级时间戳是跟读对齐的基础 |
| 端侧语音（ASR/TTS/VAD 一体） | [k2-fsa/sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) | Apache-2.0 | 可跑在手机和浏览器，离线 |
| 语音合成 | [hexgrad/kokoro](https://github.com/hexgrad/kokoro)、[SWivid/F5-TTS](https://github.com/SWivid/F5-TTS) | Apache-2.0 / MIT | Kokoro 小而快，适合实时 |
| 音素级发音评测 | [Halleck45/OpenPronounce](https://github.com/Halleck45/OpenPronounce) | MIT | Wav2Vec2 + DTM，自托管替代 Azure 发音评估 |
| 强制对齐 | [MontrealCorpusTools/Montreal-Forced-Aligner](https://github.com/MontrealCorpusTools/Montreal-Forced-Aligner) | MIT | 原声与用户录音的音素级对齐 |
| 实时语音 Agent 框架 | [pipecat-ai/pipecat](https://github.com/pipecat-ai/pipecat)、[livekit/agents](https://github.com/livekit/agents) | BSD-2 / Apache-2.0 | 对话环节的流水线：VAD → ASR → LLM → TTS |
| 间隔重复算法 | [open-spaced-repetition/ts-fsrs](https://github.com/open-spaced-repetition/ts-fsrs)、[py-fsrs](https://github.com/open-spaced-repetition/py-fsrs) | MIT | 取代 Anki 式固定牌组 |
| 语法纠错 | [languagetool-org/languagetool](https://github.com/languagetool-org/languagetool) | LGPL-2.1 | 规则型，可作 LLM 纠错的兜底 |
| 词典 / 词库 | [skywind3000/ECDICT](https://github.com/skywind3000/ECDICT)、[open-dict-data/ipa-dict](https://github.com/open-dict-data/ipa-dict) | MIT / 多 | 英汉释义、词频、柯林斯星级、IPA |
| 可借鉴的同类产品 | [ZuodaoTech/everyone-can-use-english](https://github.com/ZuodaoTech/everyone-can-use-english)（Enjoy App）、[TideSparrow/shadowing-english](https://github.com/TideSparrow/shadowing-english)、[xiaochong/hi-kid](https://github.com/xiaochong/hi-kid)、[Thiagohgl/ai-pronunciation-trainer](https://github.com/Thiagohgl/ai-pronunciation-trainer) | GPL-3 / MIT / MIT / AGPL-3 | 跟读交互、儿童口语陪练、发音打分的现成实现 |

**调研结论**：底层能力（识别、合成、发音评测、对齐、间隔重复）都有成熟开源件可用；真正缺的是把它们串起来的"学习者模型 + 内容生成 + 练习编排"这一层。这正是 Hearsay 要做的部分。

## 五、技术方向（我的初步选择，可推翻）

- **Agent 层**：Claude 作为导师大脑，负责生成材料、控制对话难度、给出重述式纠错、维护学习者模型
- **语音层**：实时对话走 pipecat 流水线；跟读评测走 whisperX + OpenPronounce 的离线批处理
- **客户端**：先做 Web（PWA），麦克风权限和实时音频在浏览器里已经够用
- **数据**：转写、发音评测和 LLM 判定在服务端运行，录音需上传，保留 30 天供回放后自动删除。学习者模型、错误档案、复习项的主副本在服务端账户下，客户端缓存；全部数据随时可整体导出（JSON）和一键删除。本地优先是后续目标，不是 v1 承诺

## 六、路线图

完成度、风险实验和还没做的产品能力见 [2026-10-24 状态清单](docs/design/2026-10-24-status-checklist.md)。

- [x] M0 — 设计文档：[学习者模型](docs/design/2026-10-22-m0-learner-model.md)、[CEFR 听说 can-do 清单](docs/design/cefr-can-do-listening-speaking.md)（109 条）、[中文母语者错误清单](docs/design/l1-zh-error-taxonomy.md)（66 条）
- [ ] M1 — 跟读原型：导入一段音频 → 逐句播放 → 录音 → 发音反馈。风险实验见 [报告](docs/design/2026-10-23-m1-risk-validation.md)：A / B / C 已通过，D 未通过（OpenPronounce 音素级精确率 0.148，所以不要用它写 P 类错误）。真人录音复测仍是 [issue #4](https://github.com/zhanglunet/hearsay/issues/4)，还没采集。最小切片在 [prototype/](prototype/README.md)，还没满足 [issue #8](https://github.com/zhanglunet/hearsay/issues/8) 的全部验收，所以这里不勾选。
- [ ] M2 — 对话原型：一个场景，实时语音对话，结束后复盘。[设计草案](docs/design/2026-10-25-m2-dialogue.md)与最小切片 [prototype/m2_dialogue/](prototype/m2_dialogue/README.md) 已能本地跑（mock / 可选 Claude，浏览器语音；事后 whisperX 批处理与 Claude 错误检测可选启用）；pipecat 实时链路 `realtime.py` 与 [风险测量脚本](experiments/exp_e_dialogue/README.md)已写但均未实测，所以这里不勾选。
- [ ] M3 — 学习者模型 + FSRS：把 M1/M2 中的错误变成复习项，并在新场景中复现
- [ ] M4 — 每日计划与 can-do 进度页

本地跟读切片的运行方式见 [prototype/README.md](prototype/README.md)。它只覆盖「演示或导入音频 → 按句播放 → 录音 → 并排回放 → 词级相似度」。不写音素级错误，也不代替上面的 M1 勾选。对话切片的运行方式见 [prototype/m2_dialogue/README.md](prototype/m2_dialogue/README.md)。

## 许可证

MIT
