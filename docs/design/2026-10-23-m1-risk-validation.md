# M1 技术风险验证报告

日期：2026-10-23
对应：[M0 学习者模型设计文档 第 6 节「M1 需要验证的风险」](2026-10-22-m0-learner-model.md#6-m1-需要验证的风险)，GitHub issue [zhanglunet/hearsay#1](https://github.com/zhanglunet/hearsay/issues/1)
脚本与结果：[`experiments/`](../../experiments/README.md)

本报告只记录实验结果和对设计文档的建议，不修改设计文档本身。

## 0. 结论速览

| 实验 | 风险 | 阈值 | 结果 | 结论 |
|---|---|---|---|---|
| A | ASR 自动纠正吞掉语法错误 | 错误保留率 ≥ 80% | whisperX large-v3 默认 **91.4%**；+ verbatim prompt **98.3%**；medium.en **87.9%**；wav2vec2 CTC 71.6% | **达到**（三个 whisperX 配置均达标；wav2vec2 CTC 未达标） |
| B | OpenPronounce 对中文口音评分是否稳定 | 同一录音扰动后分数标准差 < 0.1 的话语比例 | 含 `telephone_8k`：**94.9%**（37/39）；不含：**94.9%**（37/39） | **达到**（设计文档没写比例阈值，按 ≥ 90% 的惯例判定；分数完全确定，重复运行差为 0） |
| C | 词级时间戳精度是否够逐句跟读 | 词边界误差 < 150 ms 的比例 ≥ 90% | **93.1%**（词起点 99.5%，词终点 86.7%）；中位误差 59 ms，P90 114 ms | **达到**（词起点非常准；词终点的误差大部分来自 Kokoro 把停顿计入前一个词的真值，见 4.3） |

三项风险都可以从"待验证"转为"已验证，有限制条件"。限制条件和对设计文档的建议见各节末尾（2.6、3.5、4.4）。

## 1. 运行环境

| 项 | 值 |
|---|---|
| 机器 | 云端容器，4 vCPU，15 GB 内存，**无 GPU**；三个脚本全部按 `device="cpu"` / `compute_type="int8"` 运行 |
| Python | 3.11.17（`uv venv`） |
| torch / torchaudio | 2.8.0+cpu（见 5.1，默认装到的 2.14 / 2.11 与 whisperX 的依赖不兼容） |
| whisperx / faster-whisper / ctranslate2 | 3.4.5 / 1.2.1 / 4.4.0 |
| transformers | 5.17.0 |
| kokoro / misaki | 0.9.4 / 0.9.4，模型 `hexgrad/Kokoro-82M`，声音 `af_heart` |
| openpronounce | 0.3.0（`OPENPRONOUNCE_TTS=kokoro`，音素模型默认开启） |
| phonemizer / espeak-ng | 3.4.0 / `espeakng_loader` 自带的 libespeak-ng（`run_env.sh` 设置；另外 `apt-get install espeak-ng` 作为后备，实际没用到） |
| 数据 | `speechocean762` test 切分（Hugging Face `mispeech/speechocean762`，2500 条，311 MB parquet） |
| 镜像 | 未开启国内镜像（`HEARSAY_USE_CN_MIRRORS` 保持关闭） |

CPU 耗时（供估计 M1 批处理延迟参考）：

| 任务 | 耗时 |
|---|---|
| whisperX large-v3 int8，96 条 2–4 s 短句 | 1353 s（约 14 s/条；含 VAD + 转写） |
| whisperX large-v3 + verbatim prompt，同上 | 1419 s |
| whisperX medium.en int8，同上 | 782 s（约 8 s/条） |
| wav2vec2-large-960h CTC，同上 | 38 s（约 0.4 s/条） |
| OpenPronounce `compare_audio_with_text`，一条 1–4 s 话语 | 中位 8.3 s（均值 8.8 s，最大 31 s；含 Kokoro 参考音合成 + DTW + 词转写 + 音素识别） |
| Kokoro 合成 50 句 | 69 s（约 1.4 s/句，单独运行）；与实验 A、B 并行时 326 s |

## 2. 实验 A：转写对语法错误的保留率

### 2.1 设置

- 语料：`exp_a_grammar/sentences.json`，24 句、29 个植入错误，覆盖错误清单的 G01–G13、G16、L10 共 15 个代码。
- 音频：macOS `say` 合成，4 个声音 × 24 句 = 96 条 wav（16 kHz），已入库。`samantha`、`daniel` 是美/英式英语声音；`tingting`、`meijia` 是中文（普通话 / 台湾国语）声音读英文，模拟中文口音。
- 判定：转写归一化（小写、去标点）后，若出现错误形式记 `retained`，出现纠正形式记 `corrected`，两者都没有记 `other`。每条错误 × 每个声音算一次，每个配置共 116 次判定。
- 配置（4 种）：
  1. `whisperx_large-v3_default`：whisperX（faster-whisper large-v3，int8，`language="en"`，batch 8），默认选项。
  2. `whisperx_large-v3_verbatim_prompt`：同上，加 `initial_prompt`："Transcribe exactly what the speaker says, word for word, keeping all grammar mistakes such as 'he go', 'two book', 'I very like', 'in Monday'. Do not correct anything."
  3. `whisperx_medium.en_default`：whisperX medium.en，默认选项。
  4. `wav2vec2_large_960h_ctc`：`facebook/wav2vec2-large-960h`，贪心 CTC 解码，无语言模型（作为"不可能自动纠错"的对照）。
- 阈值：保留率 ≥ 80%。
- 原始结果：`exp_a_grammar/results.csv`（464 行，含每次判定的转写文本）；汇总：`python exp_a_grammar/report.py`。

### 2.2 总保留率（阈值 ≥ 80%）

| 配置 | retained | corrected | other | 保留率 | 阈值 |
|---|---|---|---|---|---|
| whisperx_large-v3_default | 106 | 4 | 6 | **91.4%** | 达到 |
| whisperx_large-v3_verbatim_prompt | 114 | 2 | 0 | **98.3%** | 达到 |
| whisperx_medium.en_default | 102 | 9 | 5 | **87.9%** | 达到 |
| wav2vec2_large_960h_ctc | 83 | 2 | 31 | **71.6%** | 未达到 |

参考（不计入正式结论）：whisper 偶尔把 two/three 写成阿拉伯数字（"I have 2 book and 3 pen"），错误形式实际保留了但字面匹配记为 `other`。把转写中的数字换回英文后重判：large-v3 默认 93.1%，verbatim prompt 98.3%，medium.en 89.7%，wav2vec2 71.6%（`report.py` 末尾那张表）。

### 2.3 按声音

| 配置 | daniel（英式） | samantha（美式） | tingting（中文口音） | meijia（中文口音） |
|---|---|---|---|---|
| whisperx_large-v3_default | 0.90 | 0.97 | 0.97 | 0.83 |
| whisperx_large-v3_verbatim_prompt | 1.00 | 1.00 | 0.97 | 0.97 |
| whisperx_medium.en_default | 0.90 | 1.00 | 0.90 | 0.72 |
| wav2vec2_large_960h_ctc | 0.93 | 0.90 | 0.66 | 0.38 |

### 2.4 按错误代码

| 代码 | 含义（摘自错误清单） | 判定数 | large-v3 默认 | large-v3 + prompt | medium.en | wav2vec2 CTC |
|---|---|---|---|---|---|---|
| G01 | 冠词缺失 / 误用（T1） | 8 | 1.00 | 1.00 | 1.00 | 0.50 |
| G02 | 复数标记缺失（T1） | 12 | 0.58 | 1.00 | 0.58 | 0.25 |
| G03 | 第三人称单数 -s 缺失（T1） | 8 | 0.88 | 1.00 | 0.88 | 0.75 |
| G04 | 过去时标记缺失（T1） | 20 | 1.00 | 1.00 | 0.75 | 0.95 |
| G05 | 时态体系混用（T2） | 4 | 1.00 | 1.00 | 1.00 | 0.50 |
| G06 | 系动词 / 助动词问题（T1） | 8 | 1.00 | 1.00 | 0.88 | 0.88 |
| G07 | 可数 / 不可数混淆（T2） | 4 | 1.00 | 1.00 | 1.00 | 0.50 |
| G08 | 介词错误（T2） | 8 | 1.00 | 1.00 | 1.00 | 0.75 |
| G09 | 语序（T1） | 12 | 1.00 | 1.00 | 1.00 | 0.92 |
| G10 | 代词：性别 / 格 / 省略（T1） | 8 | 0.50 | 0.75 | 0.75 | 0.75 |
| G11 | 成对连词双标（T2） | 8 | 1.00 | 1.00 | 1.00 | 0.75 |
| G12 | there be / have 混用（T2） | 4 | 1.00 | 1.00 | 1.00 | 0.75 |
| G13 | 比较结构（T3） | 4 | 1.00 | 1.00 | 1.00 | 0.75 |
| G16 | 条件与虚拟（T3） | 4 | 1.00 | 1.00 | 1.00 | 0.50 |
| L10 | 词形错误（T2） | 4 | 1.00 | 1.00 | 1.00 | 0.75 |

### 2.5 未保留的案例

whisperX large-v3 默认配置的 10 个未保留判定集中在 4 句：

| 句 | 错误 | 声音 | 转写 | 判定 |
|---|---|---|---|---|
| 4 "I have two book and three pen." | G02 ×2 | meijia | I have two books and three pens. | corrected |
| 4 | G02 ×2 | daniel | I have 2 book and 3 pen. | other（数字写法，实际保留） |
| 10 "Is raining outside now." | G10 | daniel, meijia | It's raining outside now. | corrected |
| 10 | G10 | samantha, tingting | raining outside now. | other（句首 Is 被丢掉） |
| 18 "Last year I visit three country in Europe." | G02 | meijia | …visit free country… | other（country 保留，three 误识为 free） |
| 23 "My brother work in bank near my home." | G03 | meijia | My brother worked in bank… | other（work → worked，属于另一种改写） |

加 verbatim prompt 后只剩 2 个：句 10 在 meijia、tingting 两个声音下仍被改成 "It's raining"。句 10 是最难的一类：主语脱落导致句子以 "Is" 开头，Whisper 的语言模型先验太强。

medium.en 多出的 corrected 集中在 G04 过去时（句 18 "I visit" → "I visited"，3 个声音；句 24 "I play / father teach" → "played / taught"，meijia），说明小模型更倾向于改写时态。

wav2vec2 CTC 的 31 个 `other` 几乎全是口音声音下的拼写错乱（"I BALT CAR"、"HE'LL HAVE MANY PEOPLE"、"IF I HAND YOU"），不是纠错。它没有语言模型所以几乎不会纠错（corrected 仅 2），但对口音语音的识别本身不够准，错误形式被拼错的词淹没。

### 2.6 对设计文档的建议

1. **whisperX 作为事后链路的"原样转写"可以用，不必改用 wav2vec2 CTC。** 四种配置里 wav2vec2 CTC 保留率最低（71.6%），在中文口音声音下只有 0.38–0.66；它的问题不是纠错而是识别本身，产出的文本也没法直接给 LLM 做语法错误检测。
2. **verbatim prompt 有效，建议写进设计文档 4.1 的"低归一化配置"里。** 从 91.4% 提到 98.3%，中文口音声音从 0.83–0.97 提到 0.97，G02 复数错误从 0.58 提到 1.00，且不增加耗时。prompt 文本可以直接用脚本里的那条，其中的例子最好随错误清单的 T1 代码更新（当前覆盖 he go / two book / I very like / in Monday）。
3. **大模型比小模型保留得更多。** large-v3 比 medium.en 高 3.5 个百分点，且 medium.en 更爱改时态（G04）；CPU 上 large-v3 是 medium.en 的 1.7 倍耗时。M1 若用 CPU，建议 large-v3 + prompt；若延迟预算紧，再考虑 medium.en + prompt（本实验没有测这个组合）。
4. **G10 主语脱落（"Is raining"）和 G02 复数仍是最容易被纠的两类。** 设计文档 4.1 已经规定 G/L 类检测由 LLM 在"原样转写 + 可回放音频片段"上进行；建议再补一句：对 G02 / G10 这两类代码，可以把 whisperX 词级置信度低的词作为线索，并在 n-best 里保留错误形式。
5. **注意本实验的局限。** 语料是 TTS 合成而非真人学习者录音，中文口音只是用中文 TTS 读英文模拟，词汇和语速都很"干净"；真实学习者的停顿、重复、自我修正会让保留率下降。建议 M1 原型上线后用真实录音复测同一套脚本。

## 3. 实验 B：OpenPronounce 对中文口音英语的评分稳定性

### 3.1 设置

- 数据：speechocean762 test 切分（中国学习者朗读英语短句，5 位专家打分；说话人多为儿童和青少年）。过滤 ≥ 4 词的话语，按人工 `total` 分三层（≤5 / 6–7 / 8–10）、每层按说话人去重后各抽 `40 // 3 = 13` 条，共 **39 条**（脚本的 `N // 3` 取整导致是 39 而不是 40，未改）。人工 total 分布：2 分 1 条、3 分 5 条、4 分 2 条、5 分 5 条、6 分 8 条、7 分 5 条、8 分 13 条。
- 评测：`openpronounce.compare_audio_with_text(wav, text)`，默认参数（音素模型开启，Kokoro 合成参考音）。分数 0–100，归一到 0–1 后统计。OpenPronounce 的分数由三部分加权：wav2vec2 嵌入 DTW 声学距离 30%、音素错误率 40%、词错误率 30%。
- 扰动条件（8 种）：`orig`、`orig_repeat`（同一音频再跑一次，测确定性）、`gain+6dB`、`gain-6dB`、`noise_snr30`、`noise_snr20`（白噪）、`telephone_8k`（降采样到 8 kHz 再升回）、`shift_100ms`（前置 100 ms 静音）。
- 稳定性指标：每条话语 8 个条件分数的标准差；阈值"标准差 < 0.1"的话语比例，分别给含 / 不含 `telephone_8k` 两组。
- 附带有效性指标：`orig` 分数与人工 total 的 Spearman 相关；被标记单词与人工单词分（accuracy ≤ 5 视为有问题）的精确率 / 召回率。
- 原始结果：`exp_b_pronounce/results.json`、`runs.csv`（312 行 = 39 × 8）、`words.csv`（233 个词）。
- 与设计文档的差异：设计文档写的是"同一人同一句录 5 遍，标准差 < 0.1"，脚本用"同一录音 8 种扰动"替代（没有真人多次录音），本报告按脚本的设计判定。

### 3.2 稳定性结果

| 指标 | 含全部 8 条件 | 不含 `telephone_8k`（7 条件） |
|---|---|---|
| 话语数 | 39 | 39 |
| 标准差均值 | 0.0489 | 0.0357 |
| 标准差中位数 | 0.0416 | 0.0275 |
| 标准差 P90 | 0.0916 | 0.0675 |
| 标准差最大 | 0.2022 | 0.1518 |
| **标准差 < 0.1 的话语比例** | **94.9%**（37/39） | **94.9%**（37/39） |
| 确定性：`orig` 与 `orig_repeat` 最大差 | 0.0 | — |

阈值判定：设计文档的"标准差 < 0.1"是对单条话语的要求，没有写比例阈值；按 ≥ 90% 的惯例，含 / 不含电话带宽两组都 **达到**。

标准差 ≥ 0.1 的 2 条话语都是数字串短句（分数为 0–100）：

| 文本 | 人工 total | orig | gain±6dB | noise_snr30 | noise_snr20 | telephone_8k | shift_100ms |
|---|---|---|---|---|---|---|---|
| SIX NINE ONE THREE | 5 | 86.2 | 86.2 / 86.2 | 53.8 | 54.5 | 35.0 | 79.5 |
| SEVEN NINE FOUR SIX | 8 | 62.3 | 62.2 / 62.3 | 44.3 | 39.8 | 36.0 | 65.1 |

### 3.3 逐条件敏感度（相对 `orig` 的分数偏移，0–1 归一）

| 条件 | 平均偏移 | \|偏移\| 均值 | \|偏移\| P90 | \|偏移\| 最大 | \|偏移\| > 0.1 的话语比例 |
|---|---|---|---|---|---|
| orig_repeat | 0 | 0 | 0 | 0 | 0% |
| gain-6dB | 0 | 0 | 0 | 0 | 0% |
| gain+6dB | −0.002 | 0.002 | 0.002 | 0.042 | 0% |
| shift_100ms | +0.003 | 0.020 | 0.053 | 0.122 | 2.6% |
| noise_snr30 | −0.006 | 0.050 | 0.121 | 0.324 | 20.5% |
| noise_snr20 | −0.056 | 0.066 | 0.180 | 0.317 | 23.1% |
| telephone_8k | −0.047 | 0.091 | 0.211 | 0.512 | 33.3% |

各条件对三个分数分量的平均影响（相对 orig）：

| 条件 | 音素错误率 | 词错误率 | 声学距离 |
|---|---|---|---|
| noise_snr20 | +0.041 | +0.092 | +0.35 |
| telephone_8k | +0.043 | +0.071 | +0.54 |
| noise_snr30 | −0.002 | +0.009 | +0.02 |
| shift_100ms | −0.001 | +0.006 | −0.14 |
| gain±6dB | 0 | 0 | ≤ +0.02 |

解读：

- **增益变化完全不敏感**（wav2vec2 特征对幅度归一），**前置静音基本不敏感**（DTW 吸收了偏移）。
- **电话带宽最敏感**，其次是 SNR 20 dB 白噪：两者同时抬高音素错误率、词错误率和声学距离，平均把分数拉低 5 个百分点，三分之一 / 四分之一的话语偏移超过 0.1。
- SNR 30 dB 白噪平均影响很小，但个别话语（数字串短句）偏移超过 0.3，说明短句分数对识别结果的单个词翻转很敏感。

### 3.4 有效性（附带，不设阈值）

| 指标 | 值 |
|---|---|
| `orig` 分数与人工 total 的 Spearman 相关 | 0.366 |
| `orig` 分数与人工 accuracy 的 Spearman 相关 | 0.362 |
| −音素错误率 与人工 accuracy 的 Spearman 相关 | 0.259 |
| 单词级标记精确率 / 召回率（人工 accuracy ≤ 5 为正例） | 0.303 / 0.588（233 词，人工认为有问题 34 词，OpenPronounce 标记 66 词） |
| `orig` 分数范围 | 11.3–94.8 |
| 按人工层的 `orig` 均分（± 标准差） | 低（≤5）38.3 ± 21.9；中（6–7）41.5 ± 17.9；高（8–10）54.1 ± 26.7 |
| `orig` 的平均音素错误率 / 词错误率 | 0.40 / 0.61 |

OpenPronounce 的分数与人工评分只有弱相关（0.37），绝对分数偏低且离散（人工 8 分以上的话语均分只有 54），词错误率平均 0.61 说明它内置的英语词转写模型对中文儿童口音识别很差，30% 权重的词分量基本是噪声。单词级标记召回率 0.59 但精确率只有 0.30。

### 3.5 对设计文档的建议

1. **稳定性风险可以关闭，但要限定输入条件。** 在增益、轻噪、时移下分数几乎不变；电话带宽和 SNR 20 dB 噪声会系统性压低分数约 5 个百分点并使三分之一话语漂移超过 0.1。设计文档 1 节已限定"不做多口音、多说话人噪声场景"，建议再补一条录音要求：客户端采集 16 kHz 以上、不做电话带宽压缩；检测到低 SNR 时提示换环境，而不是让分数进入 PhonemeProfile。
2. **PhonemeProfile 只用音素级输出，不要用总分。** 设计文档 2.5 把 OpenPronounce 的音素结果映射到 PhonemeProfile，这个方向是对的；本实验表明总分里 30% 的词错误率分量在中文口音上不可靠，总分与人工评分相关只有 0.37。建议明确："评测器的 0–100 总分不进入学习者模型，只用 `differences.errors` 的音素级信息"。
3. **音素级可靠性本实验没有验证。** 0.30 是**词级**精确率：脚本只比较"哪些词被标记"和该词的人工 accuracy，没有比较被标记的是哪个音素、替换成了什么，也没用 speechocean762 自带的音素级分数（`phones-accuracy`、`mispronunciations`）。所以它只说明"按词标记会有不少误报"，不能用来支撑 `common_substitution` 或 P 类 ErrorInstance 的具体门槛。建议 M1 在接入 PhonemeProfile 前补一个音素级对比：把 OpenPronounce 的 `expected_phones` / `heard_phones` 与 speechocean762 的音素级标注对齐，测音素级精确率 / 召回率和替换方向的准确率，再定门槛。在此之前，P 类错误可以先沿用设计文档 4.1 的置信度思路（多次、跨会话出现才产生 ErrorInstance），但具体数字待定。
4. **短句（≤ 4 词、数字串）分数方差大。** 跟读句子建议 ≥ 6 词，这与 5.3 shadow 块"挑 4–6 句"不冲突，只是句长要有下限。
5. **CPU 耗时 8 s/句（中位）**，其中 Kokoro 参考音合成是大头。跟读材料的参考音可以在生成材料时预先合成并缓存，M1 的"批处理 < 60 s"预算里应把参考音合成排除在会话后链路之外。
6. **数据局限。** speechocean762 的说话人以儿童为主，与 Hearsay 的成人用户不同；有效性数字只能说明"OpenPronounce 总分不可靠"，不能反推成人口音上的精确率。稳定性结论（对扰动的敏感度）与说话人年龄关系不大，可以沿用。

## 4. 实验 C：词级时间戳精度

### 4.1 设置

- 真值：Kokoro（`hexgrad/Kokoro-82M`，`af_heart`，speed 1.0）合成 `exp_c_timestamps/sentences.txt` 前 50 句（日常口语，每句 12–20 词），取 `KPipeline` 返回的 token 级 `start_ts` / `end_ts` 作为词边界真值（音频由这些时长直接生成，所以是精确真值）。Kokoro 0.9.4 的字段名与脚本一致，不需要改。
- 拼接：每 5 句拼成一段，句间插入 300–600 ms 随机静音，共 10 段（24 kHz → 16 kHz）。
- 假设：whisperX large-v3 int8 转写 + whisperX 默认英文对齐模型（wav2vec2）对齐，取 `word_segments` 的 start / end。
- 匹配：真值词序列与假设词序列用 `difflib` 做序列匹配，只统计匹配上的词的起点误差 `ds` 和终点误差 `de`。
- 阈值：词边界误差（起点和终点合并统计）< 150 ms 的比例 ≥ 90%。
- 原始结果：`exp_c_timestamps/results.json`、`word_errors.csv`（每个匹配词一行）。合成音频和真值 JSON 在 `exp_c_timestamps/audio/`（未入库，可重跑生成）。

### 4.2 结果（阈值 ≥ 90%）

| 指标 | 值 |
|---|---|
| 真值词数 / 匹配词数 | 766 / 761（匹配率 99.3%；10 段里有 2 段假设词数与真值差 1） |
| 词边界误差中位数 / P90 | 58.5 ms / 113.5 ms |
| **词边界误差 < 150 ms 的比例（起点 + 终点）** | **93.1%** → 达到 |
| 词起点误差 < 150 ms 的比例 | 99.5% |
| 词终点误差 < 150 ms 的比例 | 86.7% |

误差分布：

| 阈值 | 起点 + 终点 | 起点 | 终点 |
|---|---|---|---|
| < 50 ms | 41.7% | 6.3% | 77.0% |
| < 100 ms | 87.4% | 88.4% | 86.3% |
| < 150 ms | 93.1% | 99.5% | 86.7% |
| < 200 ms | 93.6% | 100% | 87.3% |
| < 300 ms | 98.0% | 100% | 96.1% |

起点误差中位数 75 ms、最大 159 ms，几乎是一个固定偏移（whisperX 对齐给出的起点系统性比 Kokoro 真值晚 50–100 ms，带符号中位数 +75 ms）。终点误差中位数只有 31 ms，但有一条长尾：101 个词（13%）的终点误差在 150 ms 以上，典型值 270–370 ms，最大 1130 ms。

这条长尾的来源（用 `word_errors.csv` 新增的 `gap_after`、`h_end`、`t_end` 列分析）：

- 101 个大误差词里 100 个是 whisperX 的终点**早于**真值，不是晚于。
- 其中 49 个是句末词（Kokoro 真值终点比 whisperX 晚 282 ms 中位），52 个是句中词，几乎都在短语边界（"work **because**"、"spring **and**"、"weekend **but**"、"meeting **so**"），真值终点同样比 whisperX 晚 290 ms 中位。
- Kokoro 的 token 时间戳是首尾相接的（句内 `gap_after` 全为 0），它在短语边界插入的停顿被计入前一个词的 `end_ts`。对这 52 个句中词，whisperX 终点到 Kokoro 终点之间那段音频的能量比词内低 17.8 dB（中位），即基本是静音；而终点误差 < 150 ms 的词，其最后 100 ms 能量与整词持平。

所以终点的大误差主要是真值把停顿算进了词里，whisperX 的终点更接近声学上的词尾。**去掉句末词后**，终点 < 150 ms 的比例是 92.7%，起点 + 终点合并 96.1%。正式结论仍按原指标（93.1%）判定，这个分析只说明达标数字是偏保守的。

### 4.3 句边界

脚本第一次运行时句边界误差中位数为 328 ms（句首）/ 533 ms（句尾），< 150 ms 的比例为 0。排查后发现这是真值定义的问题而不是 whisperX 的误差：Kokoro 每句合成音频首尾各带 250–300 ms / 225–275 ms 静音，脚本把音频片段的起止点当成句子真值，静音被整体算进了误差。改为用该句首词起点 / 末词终点作为句边界真值后重跑（改动见 5.3），结果：

| 指标 | 值 |
|---|---|
| 匹配到的句边界 | 49 / 50（1 句的末词 "holidays" 没在 whisperX 假设里按原词匹配上，被跳过） |
| 句首误差中位数 | 62.8 ms |
| 句尾误差中位数 | 282.7 ms（whisperX 末词终点比 Kokoro 真值早，见 4.2 的分析） |
| 句首 + 句尾误差 < 150 ms 的比例 | 49.0%（句首几乎全部 < 150 ms，句尾几乎全部 ≥ 150 ms） |

句首边界与词起点一样准；句尾差的 280 ms 与上面句末词的分析一致，是 Kokoro 把句末停顿计入末词时长所致，不是 whisperX 把句子切早了。

上面的句边界是在 whisperX 扁平的 `word_segments` 里按真值句的首末词去找对应词，**不能说明 whisperX 自己的分段与句子对应**。为此补跑了 `exp_c_timestamps/check_segments.py`（同一批音频、同一配置，结果在 `segments.json`）：

| whisperX 输出层 | segment 数（真值 50 句） | 与真值句严格一一对应的段落 |
|---|---|---|
| `transcribe` 的 segments | 10 | 0 / 10（每段 5 句、句间 300–600 ms 静音，全部合成 1 个 segment） |
| `align` 之后的 segments（按标点分句） | 51 | 8 / 10 |

`align` 后不对应的 2 段：一段是语料第 15 行本身含两句（"…already October? This year has gone by so quickly."），whisperX 按问号拆成两句，按语言学意义其实是对的；另一段句数相同，但有一处 segment 与相邻真值句重叠超过 50 ms。在一一对应的 8 段（40 句）上，segment 起点误差中位 61 ms、全部 < 150 ms；终点误差中位 283 ms，原因同上（Kokoro 把句末停顿算进末词）。

### 4.4 对设计文档的建议

1. **词起点精度完全够逐句跟读的切句和高亮。** 起点误差 99.5% 在 150 ms 内，而且是稳定的小偏移，可以在播放器里统一减掉 ~70 ms。
2. **词终点在停顿前与 TTS 的 token 时长不一致，裁剪跟读句时给末词终点留余量。** whisperX 给出的终点是声学词尾，而 Kokoro（以及一般 TTS 的时长预测）把短语停顿算在前一个词里。两种定义都能用，但切句时若用 whisperX 的末词 end 直接截断，会切掉句尾 200–300 ms 的自然衰减和停顿，听感生硬。建议：逐句跟读的句子终点取 whisperX 末词 end + 250 ms，或取"下一句首词起点 − 固定余量"；材料本身由 Kokoro 合成时，直接用 Kokoro 的 token 时间戳切句更简单，whisperX 对齐只用于学习者录音。
3. **不要用 whisperX `transcribe` 的 segments 切句。** 它是 VAD 分块，句间 300–600 ms 的停顿不足以切开，5 句合成 1 段。`align` 之后的 segments 靠转写标点分句，本实验 8/10 段与真值句一一对应，但依赖标点，学习者口语里标点会更不可靠。建议：**材料侧**切句用已知的原文句子（Kokoro 合成时直接按句合成、记录每句时长，不需要事后切）；**学习者录音侧**用原文句子的首末词去匹配 whisperX 的词级时间戳得到句边界（即实验 C 的做法，句首误差中位 63 ms），不依赖 whisperX 的分段。
4. **真值来自 TTS，口音和语速都偏理想。** 真实学习者跟读时停顿更多、吐字更含糊，对齐误差会更大；但 M1 跟读的"原句"是 TTS 材料（设计文档 5.3 shadow 块），本实验恰好对应这个场景，结论可以直接用于材料侧的切句。学习者侧录音的对齐精度留到 M1 用真实录音再测。

## 5. 脚本改动说明

实验设计（样本数、扰动条件、阈值、模型配置）没有改动。改动只有环境兼容和一处真值定义修正：

### 5.1 环境：torch / torchaudio 钉到 2.8.0

`uv pip install torch torchaudio whisperx …` 默认装到 torch 2.14 / torchaudio 2.11，而 whisperX 3.4.5 依赖的 pyannote.audio 3.4 仍引用 torchaudio 2.9 起删除的 `torchaudio.AudioMetaData`，`import whisperx.asr` 直接失败。处理：`uv pip install "torch==2.8.0" "torchaudio==2.8.0" --index-url https://download.pytorch.org/whl/cpu`。建议把这一行写进 `experiments/README.md`（本 PR 已加）。

### 5.2 `exp_a_grammar/run.py`、`exp_c_timestamps/run.py`：`torch.load` 兼容垫片

torch ≥ 2.6 把 `torch.load` 的 `weights_only` 默认改为 True；whisperX 自带的 pyannote VAD 权重（`whisperx-vad-segmentation.bin`，含 omegaconf 对象）用 lightning 的 `pl_load` 加载时显式传 `weights_only=None`，于是报 `UnpicklingError`。两个脚本开头加了十行垫片：未显式指定 `weights_only` 时改为 False。该权重由 whisperX 官方托管，属可信来源。不影响实验逻辑。

### 5.3 `exp_c_timestamps/run.py`：句边界真值改用首词起点 / 末词终点

原脚本把每句 Kokoro 音频片段的起止点当作句边界真值，但 Kokoro 输出的音频首尾各带约 250–300 ms 静音（真值 JSON 里首词 `start` 距片段起点中位 275 ms，末词 `end` 距片段终点中位 250 ms），导致句边界误差被静音整体抬高（第一次运行：句首 328 ms、句尾 533 ms 中位，< 150 ms 比例 0）。改为用该句首词的 `start` / 末词的 `end` 作为 `sents[].start/end`，原片段起止点另存为 `audio_start/audio_end`。词级指标不受此改动影响。

另外 `word_errors.csv` 增加了 `para`、`t_start/t_end`（真值）、`h_start/h_end`（假设）、`gap_after`（真值里该词之后到下一词的停顿）五列，方便分析终点误差与停顿的关系，不影响 `results.json` 的任何数字。

### 5.4 新增 `exp_c_timestamps/check_segments.py`

PR 评审指出原报告"whisperX 分段与真值句一一对应"没有依据（`run.py` 的句边界评估只在扁平的 `word_segments` 里找词）。新增这个脚本复用 `run.py` 生成的音频，检查 `transcribe` 与 `align` 两层 segments 与真值句的对应关系，结果写 `segments.json`（见 4.3）。不改变 `results.json` 的任何数字。

### 5.5 `exp_a_grammar/report.py`：增加数字归一化重判表

末尾增加一张"转写中的阿拉伯数字换回英文后重判"的保留率表，只作参考，不改 `results.csv` 和正式结论（见 2.2）。

### 5.6 未改但需要说明

- 实验 B 抽样得到 39 条而不是 40 条，是脚本按三层各抽 `N // 3 = 13` 条的取整结果，未改。
- 实验 B 的 `telephone_8k` 条件对部分话语把分数从 86 拉到 35（见 3.2），但这是实验条件而不是脚本错误，按原设计保留。
- 全部实验在 CPU 上运行；`device` / `compute_type` 保持脚本默认的 `cpu` / `int8`。
