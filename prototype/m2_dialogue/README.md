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

- 打字或点麦克风说话（浏览器语音识别，仅 Chromium 系；会归一化文本，不是权威转写）。
- Agent 发言可用 speechSynthesis 朗读，页面可关。
- 「结束并复盘」给出：轮次与词数、学习者输出占比、objectives 覆盖、
  待核对 recast 清单、中文小结。

## 它故意不做什么

- 不是 pipecat 实时流水线；没有 VAD / 流式 ASR / 打断。
- 没有事后 whisperX 批处理：recast 全是 `status=provisional`、`detected_by=rule` 的
  规则提示，没有 confirmed ErrorInstance，不计入错误统计。
- 不写学习者模型、FSRS、CanDoEvidence；接口层强制 `error_instances: []`、音素字段为空。
- 会话只在内存，重启即丢；语音不经过服务端，没有录音文件。
- mock 的 objectives 覆盖判断是关键词启发式，只表示「说没说到」，不代表「说得好不好」。

## 测试

在仓库根目录：

```bash
python -m unittest discover -s prototype/tests
```

`test_dialogue.py` 覆盖 recast 规则、覆盖判断、会话状态机、复盘指标与 HTTP 接口；
全部离线，不调外部 API。
