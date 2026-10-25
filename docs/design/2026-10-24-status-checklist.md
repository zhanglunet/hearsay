# 状态清单（2026-10-24）

这份清单对照三样东西：README 路线图、M0 设计文档第 6 节的风险、产品设想里那些还没交付的能力。

数字以 [M1 风险验证报告](2026-10-23-m1-risk-validation.md) 和 `experiments/` 里的结果文件为准。报告写 0.148 的地方，`experiments/exp_d_phonemes/results.json` 里的原始值是 0.1481，下面两处都注明。

编写时主分支是 `d22c0fb`（知情同意与采集规范，#7）。本文件描述的是写它的这条分支：设计与风险验证沿用 main，跟读原型是这次加上的最小切片。

## 1. 路线图

| 里程碑 | 状态 | 依据 |
|---|---|---|
| M0 设计文档 | 完成 | [学习者模型](2026-10-22-m0-learner-model.md)、[CEFR 听说 can-do](cefr-can-do-listening-speaking.md)、[中文母语者错误清单](l1-zh-error-taxonomy.md) 都在仓库里。README 写 109 条 can-do、66 条错误，本清单不另数一遍 |
| M1 跟读原型 | 未完成，最小切片已能本地跑 | 产品代码以前没有。这条分支的 `prototype/` 覆盖「演示或导入音频 → 逐句播放 → 录音 → 并排回放 → 词级相似度」。验收还没齐，路线图不勾选，跟踪 [issue #8](https://github.com/zhanglunet/hearsay/issues/8)。运行说明见 [prototype/README.md](../../prototype/README.md) |
| M2 对话 | 未完成，最小切片已能本地跑 | [设计草案](2026-10-25-m2-dialogue.md)与 [prototype/m2_dialogue/](../../prototype/m2_dialogue/README.md)：单场景、mock / 可选 Claude、浏览器语音输入输出、复盘；事后 whisperX 批处理（verbatim 转写 + provisional 核对）可选启用。pipecat 实时流水线未接，路线图不勾选 |
| M3 学习者模型 + FSRS | 未开始 | 没有 Learner 存储，没有复习调度 |
| M4 每日计划 + can-do 进度 | 未开始 | 没有计划编排，没有进度页 |

## 2. M0 §6 风险

脚本和结论在 [`experiments/`](../../experiments/README.md)，写进报告的日期是 2026-10-23。

| 风险 | 报告结论 | 这次怎么用 |
|---|---|---|
| A. ASR 会不会把语法错误改掉 | **通过（限 whisperX）**。large-v3 默认 91.4%，加 verbatim prompt 98.3%，medium.en 87.9%，都 ≥ 80%。wav2vec2 CTC 71.6%，**没过** | 原型不算语法错误，也没有接 whisperX。以后做原样转写再沿用 verbatim prompt |
| B. OpenPronounce 分数稳不稳定 | **通过**。8 种扰动下，标准差 < 0.1 的话语占 94.9%（37/39）。同一条音频重跑差为 0 | 设计文档写的是「同一人同一句录 5 遍」。实验换成了扰动，报告已说明，并按 ≥ 90% 判通过。原型不用 OpenPronounce 总分 |
| C. 词级时间戳够不够切句 | **通过**。词边界误差 < 150ms 的比例 93.1%（起点 99.5%，终点 86.7%） | 原型按原文词序消耗时间戳，句尾最多再留 250ms，且不超过下一词起点。不用 whisperX `transcribe` 的分段 |
| D. 音素级输出能不能支撑 PhonemeProfile / P 类 ErrorInstance | **没过**。精确率 0.148（原始 0.1481），召回率 0.759（原始 0.7592），替换方向 0.351（原始 0.3514）。门槛是精确率 ≥ 0.60、召回率 ≥ 0.50、方向 ≥ 0.70 | **产品规则：不要用 OpenPronounce 的音素标记写 P 类 ErrorInstance，不要填 `accuracy_mean` / `accuracy_mean_30d`，不要填 `common_substitution`。** 原型里的低分句只来自词召回 |
| 真人复测 A 和句界 | **未做**。[issue #4](https://github.com/zhanglunet/hearsay/issues/4) 开着。模板在 [同意书](../ops/m1-consent.md) 和 [采集规范](../ops/m1-recording-protocol.md)。仓库里没有学习者录音，也没有签过名的同意书 | `experiments/exp_a_grammar/audio/` 是 macOS `say` 合成的，experiments README 写明了。不要把它当成真人复测 |
| LLM 判 can-do 是否稳定 | **未验证** | 要等对话路径。报告没有这项实验 |
| 实时 recast 误报 | **未验证** | M2 切片能测规则 recast 的 discarded 比例（实时文本 vs 批处理文本），但实时 LLM 纠错链路不存在，M0 §6 的 ≤20% 指标仍未测 |
| 会话后批处理 < 60 秒 | **未验证** | M2 切片已接 whisperX verbatim 批处理并记录 `batch.duration_sec`，但还没用 5 分钟真实对话录音测过端到端预算 |

A/B/C 的材料是合成语音或朗读语料，不是 Hearsay 的成人自由对话。这些限制写在报告 2.6、3.5、4.4、6.7，这里不改写。

## 3. 工程

| 项 | 状态 |
|---|---|
| CI | [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml) 做 `compileall`、ruff 语法（E9/F63/F7/F82），并跑 `prototype/tests`。不安装 torch / whisperX / Kokoro / OpenPronounce，不跑 A/B/C/D，不下载模型 |
| issue #1 | 已关闭。云端跑通 A/B/C 并出报告 |
| issue #3 | 已关闭。实验 D，音素级可靠性 |
| issue #4 | **开着**。真人录音复测。本清单不把它算作完成 |
| issue #8 | **开着**。M1 跟读原型。最小切片对着它做，验收没齐，不关闭 |
| 合并前的 README | `d22c0fb` 仍写「设计阶段（2026-10-22）……尚无代码」。这和 `experiments/` 不符。本分支改了状态行和路线图注释 |

## 4. 产品设想

README 第二节里的能力，没有一件作为产品交付。

| 能力 | 状态 |
|---|---|
| 个性化学习者模型（分技能、词项、错误档案、兴趣、时间预算） | 只有设计，没有运行时的 Learner |
| 听 → 跟读 → 复述 → 对话 | 跟读、对话各有最小切片。听的理解题、复述没有；对话切片不是实时语音流水线 |
| 从自己的话里长出 FSRS，在新场景里再用 | 没有 |
| 面向中文母语者的发音和语法处理 | 错误清单在设计里。原型不标音素，也不做 L1 纠错 |
| can-do 进度，而不是宝石 | 清单在设计里。没有进度页，也没有 CanDoEvidence |
| 每天约 15 分钟的计划 | 设计在 M0 §5.3（跟读块 4 分钟、4–6 句）。没有编排器。演示材料是 6 句，只是为了让切片有东西可跟 |

## 5. 和任务摘要不一致、以仓库为准的地方

1. 「A 通过（whisperX ≥ 80%）」和报告一致，但不要理解成所有 ASR 配置都过了。wav2vec2 CTC 是 71.6%，未通过。
2. 「B 通过」和报告结论一致。验证方式不是设计文档原文的「录 5 遍」，而是 8 种扰动。报告 3.1 写了这个差别。
3. 音素精确率对外写 0.148，结果文件是 0.1481。召回率 0.759 / 0.7592，方向 0.351 / 0.3514。门槛判定用的是报告里的四舍五入，两边都未达到。
4. 「M1 产品代码尚未开始」只对 `d22c0fb` 成立。本分支已经放上 `prototype/`，所以清单改记成「最小切片已开始，M1 仍不勾选」。
5. issue 列表对得上：开着的是 #4 和 #8，关上的是 #1 和 #3。没有别的 issue。

## 6. 原型相对设计对象的对齐

用了这些名字，但没有把对象存下来：

- 材料：`kind`、`target_cefr`、`topic_tags`、`generated_by: imported`、句级 `start_ms` / `end_ms`
- 会话类型：`shadow`
- 反馈：词级对齐（match / substitution / deletion / insertion），不是 `detected_by: phoneme_scorer`

没用、也不该在这一步用的：

- `ErrorInstance`（任何代码，包括 P 类）
- `PhonemeProfile.accuracy_mean_30d` 和 `common_substitution`
- `CanDoEvidence`、`DailyPlan`、FSRS 卡
