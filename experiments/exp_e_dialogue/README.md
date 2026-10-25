# experiments/exp_e_dialogue — M2 对话风险测量

对应 M0 §6 里 M2 相关的三个风险和 M2 设计草案 §4。
**2026-10-25 状态：脚本就绪，三项都还没实测**（本机无 API key，且网络只有
几十 KB/s，装不起 whisperX large-v3 等模型）。跑通后把结果写进本目录与状态清单。

| 脚本 | 测什么 | 阈值 | 实测 |
|---|---|---|---|
| `aggregate.py` | 实时 recast 被批处理 discarded 的比例 | ≤ 20% | **v3c 达到 0.0**（2026-10-25，Kimi，20 段，v3 对账口径。演进：v1 0.778 → v2 0.333 → v3b 0.286 → v3c 0.0；`results_recast_fpr_v1/v2/v3.json`） |
| `can_do_consistency.py` | 同一转写 LLM 判 can-do，5 次 verdict 一致率 | ≥ 80% | **demo 已测：1.0 达到**（2026-10-25，kimi-for-coding，5/5 pass，见 `results_cando.json`；真实学习者优先级待测） |
| `batch_latency.py` | 5 分钟对话：转写 + 检测 + 复盘 | < 60 秒（不含一次性模型加载） | 未测 |

补充：同日用 Kimi 实测了 M2 的 `detect_errors`（`detected_by=asr_llm`）：
两句含 G04/G13 错误的文本，返回 3 条正确错误（go→went、see→saw、more better→better），
全部通过 observed 原文校验。

**v1 测量分析（20 段，每段 2 轮，exp_a 错误句与 exp_c 干净句交替）**：
provisional 9 条、discarded 7 条、批处理新增 10 条。 discarded 几乎全是
**实时把各类语法错误错标成 G04（时态）**——G01 冠词、G02 单复数、G06 缺动词、
G10 代词都被标成 G04，与批处理的正确代码对不上。也就是说主要问题不是「不该纠的乱纠」，
而是**实时抽取的错误编码不可靠**。干净句 10 段没有产生实时 recast（无误报）。
改进：实时 prompt 加代码指引和「拿不准用 X00」，X00 在同一话语上可与任意代码合并；
X00 实例只留档，不进错误档案和复习卡。

**v2 复测（同一语料与流程）**：provisional 12 条、discarded 4 条、fpr 0.333，比 v1 明显
好转但仍高于 0.20。4 条 discarded 逐条看是三类口径问题，不是简单的乱纠错：
1. **粒度差异**：批处理把一句里的两个错误合并报一条，实时拆开报，多出的一条被丢弃；
2. **分类分歧**：实时 G09 vs 批处理 L10（am agree）、G09 vs G10（Is raining），
   两边都有道理但编码不同；
3. **规则与 LLM 编码不同**：同一句实时 L10 与规则 G09 并存，批处理只认 L10，
   规则的 G09 被丢弃。
**v3 复测（observed 重叠 + X00 口径）**：provisional 7、discarded 2、fpr 0.286，仍高于 0.20。
两条 discarded 揭示了口径之外的两个工程问题：
1. **批处理偶发回退规则导致漏检**：LLM 检测一次 5xx 后退回规则，规则不覆盖 G04，
   于是实时正确的 G04 也被丢弃。已改为**先试一次再回退**。
2. **一条批处理实例被对账两次**：实时 L10 与规则 G09 同指一处错误，批处理只有一条，
   先合并的占掉后另一条被误丢。已改为**对账前按「话语 + observed」去重，LLM 优先**。
**v3c（含去重与重试修复）**：20 段、provisional 9、**discarded 0、fpr 0.0，达到 ≤20% 阈值**
（`results_recast_fpr_v3.json`）。注意 v3 改了匹配口径（observed 重叠 + 去重），
与 v1/v2 不是同一标尺；M0 §4.1 已写明规则与「误报」定义。

**实时 recast 结构化抽取已上线（asr_llm_realtime）**，pipecat 链路仍未实测。

**实时导师也已实测（2026-10-25，Kimi / AnthropicTutor）**：复习场景（G04）三轮对话，
回复自然贴角色，主动追问过去时信息（"When did the team send the report…?"），
并对学习者的 "Yesterday I go to the park" 做出自然 recast（"Oh, you went to the park
yesterday?"）。注意：规则 recast 没扫到这句（规则只覆盖少数模式），LLM 纠错的覆盖
确实更广。实时 recast 的结构化抽取已上线（asr_llm_realtime），pipecat 链路仍未实测。

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
# 或者一条命令端到端跑 20 段（错误句与干净句交替，无音频走 realtime_fallback）：
python exp_e_dialogue/run_recast_sessions.py --sessions 20 --out /path/recaps
# 注意：实时 LLM recast 的结构化抽取已上线（asr_llm_realtime，2026-10-25），
# 20 段对话的正式误报率测量需带批处理的真实会话，尚未完成。

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
