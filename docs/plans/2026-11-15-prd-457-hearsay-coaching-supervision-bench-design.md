# PRD-457/T1：陪练监督台设计（教练全程看纠正出炉，批注发回 agent，未点头不进陪练反馈）

> 来源：trend issue [#2205](https://github.com/zhanglunet/trend/issues/2205)。2026-11-15 GitHub 趋势日报（digests/2026-11-15.md），用户 23/23 逐条采纳。
> 设计日：2026-11-15 · 目标仓库：zhanglunet/hearsay
> 状态：T1 设计草案，待评审。仅设计文档（纯加法 .md）；最小实现（T2）、监督回路闸门（T3）、划界断言（T4）、验收试运行（T5）按本设计后续落地。
> 示例全部虚构占位，不出现真实内部主机名、IP、账号或密钥。

## 0. PR 门槛自查

| 门槛 | 落实 |
|---|---|
| require_integration_point | **接入点：陪练 agent 出纠正之后、陪练反馈出口之前**——T2 以 `supervise(correction)` + `outlet` 供陪练反馈流程在出口前调用；教练未点头的纠正不进下游 |
| no_missing_channel | 只消费既有纠正记录结构注入；批注与反馈写本地 JSONL 账本（路径注入文件落库），零新外部渠道；发回 agent 走既有 agent 调用面，不另起通道 |
| no_duplicate_module | main 上同类模块盘点：PRD-388（纠正验证台）/PRD-411（陪练复盘会话）/PRD-434（评审流水线）。**本条不另起纠正引擎、不验单条纠正真假、不做协同改稿**：只管「出纠正的全程有没有人盯着、批注有没有发回 agent」 |
| impl_requires_devlog | T2~T5 实现 PR 各附 devlog 开发记录+合规核对；监督记录落 JSONL 文件（路径注入），不只存内存 |

## 1. 红线

| # | 红线 | 落地方式 |
|---|---|---|
| R1 | **未点头的纠正不进陪练反馈** | 监督结论=approved/returned/pending 三态：只有 approved 放行出口；pending 与 returned 一律拦截 |
| R2 | **人看、agent 改** | 教练只批注和裁决，不下场改纠正文本；改由 agent 接反馈重出，改完再回来复核 |
| R3 | **进度 + 批注 + 发回反馈三件套落账** | 每条纠正 {correction_id, progress, annotations, feedback_rounds, verdict} 落 JSONL 账本；缺件 SUPERVISION_INCOMPLETE 拒绝入账；append-only |
| R4 | **批注与反馈全程留痕** | 每轮批注带署名与时间戳；每轮发回带反馈原文与 agent 回版对照；删改账本即 LEDGER_DRIFT |
| R5 | 占位符纪律 | 本文件示例全为占位；T5 检查覆盖本文件 |
| R6 | 实现 PR 只开不合并 | 等用户 review |

## 2. 借鉴对象、许可证与不复用红线

- backnotprop/plannotator（Apache-2.0，实测）——agent 监督工作台形态：批注、裁决、一键把反馈发回 agent；代码复用需署名。
- ag-ui-protocol/ag-ui（MIT，实测）——agent 与用户交互协议形态：监督台上「批注发回 agent」落到前端应用里的交互方式；代码复用需署名。
- Tencent/LoopForge（无 LICENSE 文件）——只借「人工批准门」形态，**绝不复用其文本或代码**。

本设计草稿为原创文字；借鉴只借形态，不引入原仓依赖，不复制原文与代码。

## 3. 与既有机制划界

| 维度 | PRD-457（本条） | 验证台（PRD-388） | 协同会话（PRD-411） | 评审流水线（PRD-434） |
|---|---|---|---|---|
| 管什么 | **出纠正全程有没有人盯着、批注有没有发回 agent** | 单条纠正真假可复现验证 | 人动手一起改 | 整份脚本过不过机器评审 |
| 比对 | 纠正 vs 教练批注与裁决 | 纠正 vs 复核 | 纠正 vs 协同修订 | 脚本 vs 确定性规则+LLM 判定 |
| 关系 | 陪练反馈出口前的监督关口 | 相邻不相干 | 本条人不下场改 | 下游（本条不碰） |

## 4. 监督台设计

### 4.1 监督对象与数据模型（T2 预埋）

监督对象是陪练 agent 出的每条纠正：纠正文本、出错点定位、建议说法、难度档位、出纠过程（agent 依据了哪条规则/哪段学员语音转写，占位描述）。

```json
{"schema": "hearsay-coaching-supervision-bench/v1",
 "correction": {"correction_id": "c-001", "learner_utterance": "…（占位）",
   "error_span": "…（占位）", "suggestion": "…（占位）", "level": "A1|B1（占位）",
   "provenance": {"rule": "R-PLACEHOLDER", "evidence": "…（占位）"}},
 "progress": [{"step": "drafted|returned|revised|approved", "at": "2026-11-15T00:00:00Z"}],
 "annotations": [{"annotation_id": "a-001", "author": "coach-placeholder",
   "text": "换说法，太难（占位）", "at": "2026-11-15T00:00:00Z"}],
 "feedback_rounds": [{"round": 1, "feedback": "换说法/降难度（占位）",
   "revised_correction_id": "c-001-r1"}],
 "verdict": "approved|returned|pending"}
```

### 4.2 流程（确定性）

agent 出纠正 → 纠正带出纠过程进监督台（pending）→ 教练看进度、随手批注 → 一键把反馈发回 agent（「换说法/降难度」二选一或自由文本，占位）→ agent 改完以新版纠正回来（returned → revised，轮次 +1）→ 教练复核点头（approved）才放行进陪练反馈；未点头的一律拦截，只留痕。

### 4.3 工作台界面（形态，不含实现）

- 队列：待看 / 待复核 / 已点头三列，纠正按出炉时间倒序。
- 单条视图：纠正全文、出纠过程、批注串、发回历史轮次对照（旧版 vs 新版并列）。
- 操作：批注、发回（附反馈文本）、点头、驳回（附理由）；每步操作即时落账，刷新不丢。

## 5. 失败闸门（T3 落地）

| 错误码 | 触发 | 行为 |
|---|---|---|
| SUPERVISION_INCOMPLETE | 进度/批注/发回反馈三件套缺件 | 拒绝入账 |
| SUPERVISION_VERDICT_MISMATCH | 有未处理批注却 approved（或反之） | 显形拒绝 |
| SUPERVISION_OUTLET_BYPASS | 陪练反馈出口收到无监督记录的纠正 | 拦截并告警 |
| LEDGER_DRIFT | 账本被删/改首条 | 显形拒绝 |

## 6. 衔接

T2 最小实现（supervise + outlet + SupervisionLedger 三件套落账）；T3 闸门（append_only + verdict 双向对账 + 出口拦截 + 一票否决）；T4 划界（标准库-only 钉值 + 借鉴仓零符号仅代码标识符扫描 + R1~R4 红线钉值）；T5 验收（全链两遍逐字节一致 + 失败演练 + 链复跑子进程实测 + 文档无密钥）。

## 7. 开放问题（留待评审/T2）

1. 发回轮次上限（倾向：不设硬上限，轮次留痕可查——待 T2）；
2. 批注是否允许教练之间互相可见（倾向：同教练组可见，带署名——待评审）。

## 8. 验收标准

- 设计评审通过：本文件覆盖接入点、数据模型、流程、闸门、划界、红线六项；
- 监督对象、关口、留痕口径与 PRD-457 一致：未点头的纠正不进陪练反馈；
- 本文件无真实内部主机名、IP、账号或密钥。
