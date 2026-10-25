# experiments/exp_e_dialogue — M2 对话风险测量

对应 M0 §6 里 M2 相关的三个风险和 M2 设计草案 §4。
**2026-10-25 状态：脚本就绪，三项都还没实测**（本机无 API key，且网络只有
几十 KB/s，装不起 whisperX large-v3 等模型）。跑通后把结果写进本目录与状态清单。

| 脚本 | 测什么 | 阈值 | 实测 |
|---|---|---|---|
| `aggregate.py` | 实时 recast 被批处理 discarded 的比例 | ≤ 20% | 未测 |
| `can_do_consistency.py` | 同一转写 LLM 判 can-do，5 次 verdict 一致率 | ≥ 80% | **demo 已测：1.0 达到**（2026-10-25，kimi-for-coding，5/5 pass，见 `results_cando.json`；真实学习者优先级待测） |
| `batch_latency.py` | 5 分钟对话：转写 + 检测 + 复盘 | < 60 秒（不含一次性模型加载） | 未测 |

补充：同日用 Kimi 实测了 M2 的 `detect_errors`（`detected_by=asr_llm`）：
两句含 G04/G13 错误的文本，返回 3 条正确错误（go→went、see→saw、more better→better），
全部通过 observed 原文校验。

**实时导师也已实测（2026-10-25，Kimi / AnthropicTutor）**：复习场景（G04）三轮对话，
回复自然贴角色，主动追问过去时信息（"When did the team send the report…?"），
并对学习者的 "Yesterday I go to the park" 做出自然 recast（"Oh, you went to the park
yesterday?"）。注意：规则 recast 没扫到这句（规则只覆盖少数模式），LLM 纠错的覆盖
确实更广；实时 recast 的结构化抽取与误报率统计仍未做，pipecat 链路仍未实测。

## 环境

- Python 3.11/3.12，whisperX 与 ffmpeg（同 `experiments/README.md`，torch 钉 2.8.0）
- `HEARSAY_ANTHROPIC_API_KEY` 或 `HEARSAY_LLM_API_KEY`（can-do 一致性必须；
  错误检测缺 key 时退回规则口径）
- 也支持 Kimi 的 Anthropic 兼容端点：
  `HEARSAY_LLM_BASE_URL=https://api.kimi.com/coding/v1/messages` +
  `HEARSAY_LLM_API_KEY` + `HEARSAY_LLM_MODEL=kimi-for-coding`
- 模型默认 `claude-haiku-4-5-20251001`，`HEARSAY_LLM_MODEL` 可改

## 跑法

```bash
# 1) 误报率：先跑若干次 M2 会话（HEARSAY_M2_BATCH=whisperx），把每次 /api/end
#    的响应各存成一个 JSON 放进同一目录（如 recaps/01.json …），然后：
python exp_e_dialogue/aggregate.py /path/recaps/
# 注意：实时 LLM recast 链路（realtime.py）目前只有规则 recast，
# 所以这里先得到规则口径的误报率；LLM 实时链路误报率仍待结构化抽取。

# 2) can-do 一致性（同一转写判 5 次）：
python exp_e_dialogue/can_do_consistency.py --demo
python exp_e_dialogue/can_do_consistency.py --transcript /path/session.json \
    --id SI-A2-01 --statement "能解释延期原因并提出新日期"

# 3) 批处理延迟：一条约 5 分钟的对话音频（整条按一个话语处理，偏乐观口径）
python exp_e_dialogue/batch_latency.py --audio /path/dialogue-5min.wav
```

结果文件：`aggregate_fpr.json`（在输入目录）、`results_cando.json`、`results_latency.json`。

## 报告模板（跑完填）

| 指标 | 阈值 | 数字 | 达到 / 未达到 | 口径与限制 |
|---|---|---|---|---|
| recast 误报率 | ≤ 20% | — | 未测 | 规则 / LLM 实时链路要分开写 |
| can-do 一致率 | ≥ 80% | — | 未测 | 哪条 can-do、哪份转写、模型名 |
| 批处理延迟 | < 60 s | — | 未测 | 音频时长、是否含模型加载、整条 vs 逐轮 |
