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

用 Claude 当导师：

```bash
HEARSAY_LLM=anthropic HEARSAY_ANTHROPIC_API_KEY=... python -m m2_dialogue
# 模型默认 claude-haiku-4-5-20251001，用 HEARSAY_LLM_MODEL 覆盖
```

密钥只从环境变量读，不写日志、不进响应。切到 Claude 不需要改前端。

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
- **注意**：批处理检测目前也是规则扫描，不是 LLM 检测；这个误报率衡量的是规则
  recast，不是 M0 §6 的 LLM 实时链路误报率。60 秒预算也还没用真实长对话测过。
- 音频生命周期：仅在批处理启用时，每轮录音随 `/api/turn` 上传并写到系统临时目录，
  `/api/end` 后整目录删除；批处理关闭时音频直接忽略，不落盘。不进仓库。

## 它故意不做什么

- 不是 pipecat 实时流水线；没有 VAD / 流式 ASR / 打断。
- 实时纠错只是 `detected_by=rule` 的 provisional 提示；没有 LLM 实时纠错与
  LLM 事后检测。没有批处理时复盘里没有任何 confirmed 实例。
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
