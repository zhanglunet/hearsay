# M2 对话原型（最小切片）

设计草案：[docs/design/2026-10-25-m2-dialogue.md](../../docs/design/2026-10-25-m2-dialogue.md)。

单场景「向同事解释项目延期」：Agent 扮演同事 Alex，学习者说明延期原因、提出新日期，
并在大约第 2 轮回应「客户今天要一页摘要」的意外要求。结束后出复盘。

## 怎么跑

需要 Python 3.11+，只用标准库。在 `prototype/` 目录下：

```bash
cd prototype
python -m m2_dialogue
```

浏览器打开 <http://127.0.0.1:8766/>（端口用 `HEARSAY_M2_PORT` 改）。
默认 tutor 后端是 **mock**：离线脚本，不需要 key 和网络，用来验证完整流程。

用 Claude 当导师（也兼容 Kimi 的 Anthropic 协议端点）：

```bash
HEARSAY_LLM=anthropic HEARSAY_ANTHROPIC_API_KEY=... python -m m2_dialogue
# 模型默认 claude-haiku-4-5-20251001，用 HEARSAY_LLM_MODEL 覆盖

# 或用 Kimi（https://www.kimi.com/code/docs/en/ 的 Anthropic 兼容地址）：
HEARSAY_LLM=anthropic \
HEARSAY_LLM_BASE_URL=https://api.kimi.com/coding/v1/messages \
HEARSAY_LLM_API_KEY=... HEARSAY_LLM_MODEL=kimi-for-coding \
python -m m2_dialogue
```

密钥只从环境变量读，不写日志、不进响应。切到 Claude 不需要改前端。
`HEARSAY_LLM_API_KEY` 优先于 `HEARSAY_ANTHROPIC_API_KEY`；端点、密钥、模型
三个环境变量对批处理检测和 `exp_e_dialogue` 的测量脚本同样生效。

实测记录（2026-10-25，Kimi）：复习场景三轮对话通过——导师贴角色、按 G04 目标
追问过去时，并对 "Yesterday I go to the park" 自然 recast 成 "you went to the park"。
规则 recast 未覆盖该句（规则只有少量模式），LLM 纠错覆盖更广。

**实时 recast 结构化抽取已上线**：Anthropic 导师直接返回 `{"reply", "recasts"}` JSON，
经校验（G/L/I、observed 必须在学习者原文、confidence ≥ 0.6）形成
`detected_by=asr_llm_realtime` 的 provisional 实例，与规则命中按代码去重；
非 JSON 回复退化为纯文本不阻断对话。同日复测：学习者一句
"Yesterday I go to the park and see my friend" → 实时 G04 provisional →
批处理 confirmed 合并 1 条 + 新增 1 条、discarded 0、**小样本误报率 0.0**
（1 段会话，不是 M0 要求的 20 段正式测量），M3 入库 2 条。
批处理转写器改为惰性加载：无音频的会话不再要求安装 whisperX。

## 实时语音链路（realtime.py，未实测）

```bash
python -m pip install -r prototype/m2_dialogue/requirements-realtime.txt   # Python 3.11/3.12
HEARSAY_ANTHROPIC_API_KEY=... python -m m2_dialogue.realtime --host 127.0.0.1 --port 7860
```

pipecat 流水线：transport → Silero VAD → faster-whisper STT → Claude → Piper TTS。
STT 模型用 `HEARSAY_M2_STT_MODEL` 改（默认 base），LLM 模型用 `HEARSAY_LLM_MODEL`。
断开时把实时转写与规则 recast 写到 `prototype/runtime/m2-realtime-*.json`（已忽略，勿提交）。

**未实测**：本机没装依赖和模型，代码只过了编译检查。LLM 实时 recast 的结构化抽取
还没做，实时链路误报率因此还测不了。

## 一天的闭环（M2 ↔ M3 ↔ M4）

- **M4/M3 → M2**：点「复习对话（M3 到期卡）」或 `POST /api/session {"mode":"review"}`，
  直接用 M3 学习者存储生成复习场景，target_error_codes 会进入 mock 引导提问和
  Claude system prompt。存储路径 `HEARSAY_M3_STORE`（默认 `prototype/runtime/m3-learner.json`）。
- **M2 → M3**：`/api/end` 自动把复盘 ingest 进 M3（confirmed 才写入，幂等），
  响应带 `ingest` 结果；设 `HEARSAY_M3_INGEST=0` 关闭。
- **评分回流**：复习目标是否用对，到 M4 进度页给复习卡打 1–4 分，FSRS 推进到期时间。

## 交互

- 打字或点麦克风说话。麦克风同时做两件事：浏览器语音识别填文本（仅 Chromium 系，
  会归一化，不是权威转写），以及 MediaRecorder 录音（供事后批处理）。
  没有语音识别时可以录音 + 打字补转写。
- Agent 发言可用 speechSynthesis 朗读，页面可关。
- 「结束并复盘」给出：轮次与词数、学习者输出占比、objectives 覆盖、
  待核对 recast 清单、中文小结；启用批处理时还有权威转写与核对结果。

## 事后批处理（可选，默认关闭）

```bash
HEARSAY_M2_BATCH=whisperx python -m m2_dialogue
```

- 需要安装 whisperX（环境同 `experiments/`，torch/torchaudio 钉 2.8.0）和 ffmpeg
  （解码 MediaRecorder 的 webm）。模型默认 large-v3，`HEARSAY_M2_ASR_MODEL` 可改，
  首次转写才加载 / 下载。
- 转写用实验 A 验证过的 **verbatim prompt** 配置，产出权威文本；
  没有音频的话语退回实时文本并在复盘里标明 `realtime_fallback`。
- 核对（M0 §4.1 口径）：实时 recast（provisional）与批处理发现按「同一话语 + 同一代码」
  合并为 confirmed，对不上的 provisional 标 discarded，批处理新发现的直接 confirmed。
  复盘给出 confirmed / discarded 清单、误报率（discarded / provisional）和
  `batch.duration_sec` 计时。
- **错误检测分两层**：批处理发现默认在有 `HEARSAY_ANTHROPIC_API_KEY` 时走 **Claude LLM 检测**
  （`detected_by=asr_llm`），没 key 时用规则扫描；`HEARSAY_M2_DETECT=llm/rule` 可强制。
  LLM 输出逐条校验：只收 G/L/I 类代码（P 类拒收）、话语编号必须存在、observed 必须是
  原文连续片段、confidence ≥ 0.6；不合格静默丢弃。LLM 调用失败自动回退规则，
  复盘 `detection` 字段会写明实际用的检测器。启用 LLM 检测时转写文本会发给 Anthropic。
- **注意**：误报率衡量的是「实时规则 recast vs 批处理发现」；实时 LLM 纠错链路仍不存在，
  M0 §6 的 LLM 实时链路误报率还没测。60 秒预算也没用过真实长对话测过。
- 音频生命周期：仅在批处理启用时，每轮录音随 `/api/turn` 上传并写到系统临时目录，
  `/api/end` 先删除再返回复盘；批处理关闭时音频直接忽略，不落盘。不进仓库。

## 它故意不做什么

- 不是 pipecat 实时流水线；没有 VAD / 流式 ASR / 打断。
- 实时纠错只是 `detected_by=rule` 的 provisional 提示；没有 LLM 实时纠错。
  没有批处理时复盘里没有任何 confirmed 实例。
- 不写学习者模型、FSRS、CanDoEvidence；接口层强制 `error_instances: []`、音素字段为空。
- 会话只在内存，重启即丢。
- mock 的 objectives 覆盖判断是关键词启发式，只表示「说没说到」，不代表「说得好不好」。

## 测试

在仓库根目录：

```bash
python -m unittest discover -s prototype/tests
```

`test_dialogue.py` 覆盖 recast 规则、覆盖判断、会话状态机、复盘指标与 HTTP 接口；
`test_dialogue_batch.py` 覆盖核对合并 / 丢弃 / 新增、批处理转写（注入假转写器）、
音频落盘与清理。全部离线，不调外部 API、不加载模型。
