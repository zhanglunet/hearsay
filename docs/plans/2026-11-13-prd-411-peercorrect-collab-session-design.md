# PRD-411/T1：陪练复盘会话 设计（学员与教练同屏回看同一份纠正记录，追问/订正带署名，未接受不进陪练反馈）

> trend issue #1975。来源：2026-11-13 GitHub 趋势日报（digests/2026-11-13.md），用户 23/23 逐条采纳。
> 设计日：2026-11-13 · 目标仓库：zhanglunet/hearsay
> 状态：T1 设计草案，待评审。仅设计文档（纯加法 .md）；内核（T2）、闸门（T3）、划界断言（T4）、验收试运行（T5）按本设计后续落地。
> 示例全部虚构占位，不出现真实内部主机名、IP、账号或密钥。

## 0. PR 门槛自查（repos.yaml default_pr_gate）

| 门槛 | 落实 |
|---|---|
| require_integration_point | **接入点：纠正追问/订正提出 之后、陪练反馈 出口之前**——T2 以 `propose/accept/reject` 会话原语 + `outlet` 出口包装供 陪练反馈 流程在出口前调用；只把已接受（accepted）的改动写进下游 |
| no_missing_channel | 只消费既有 纠正记录 产物结构注入；署名/时间/接受状态写本地 JSONL 会话日志（路径注入文件落库）；同屏=同一份日志回放视图，零新外部渠道、零真实外呼 |
| no_duplicate_module | main 上同类模块盘点：PRD-388（验证台）。**本条不另起 纠正引擎**：只管"改的过程看得见"——谁改的、改了什么、接受没有 |
| impl_requires_devlog | T2~T5 实现 PR 各附 devlog 开发记录+合规核对；会话日志落 JSONL 文件（路径注入），不只存内存 |

## 1. 红线

| # | 红线 | 落地方式 |
|---|---|---|
| R1 | **未接受的改动不进 陪练反馈** | 每条改动先经会话提出（propose）→ 接受（accept）才生效；陪练反馈 出口只收 accepted；rejected/proposed 一律拦在下游外留痕 |
| R2 | **改动带署名** | 每个会话事件（propose/accept/reject）必须带 author+at；缺一 SESSION_INCOMPLETE 拒绝入账——"谁改的留名" |
| R3 | **会话日志 append-only 可回放** | 事件流 JSONL 只增不删不可改写；`replay(events)` 对同一事件流两遍回放逐条一致（确定性）；破坏 LEDGER_DRIFT 显形 |
| R4 | **状态机封闭** | proposed→accepted/rejected 单向；重复接受、接受/拒绝不存在的条目、对 rejected 再接受均 SESSION_STATE_CONFLICT 显形拒绝 |
| R5 | 占位符纪律 | T5 检查覆盖本文件 |
| R6 | 实现 PR 只开不合并 | 等用户 review |

## 2. 借鉴对象、许可证与不复用红线

zed-industries/zed（双许可证含 GPL-3.0，实测）——只借鉴多人实时协作形态，绝不复用代码；vercel-labs/agent-browser + agent-desktop（Apache-2.0）agent 操作真机形态；CopilotKit/OpenBot（MIT）动作事前已定、事后已记录形态。零代码零文本复用，不引入原仓依赖。

## 3. 与既有机制划界

| 维度 | PRD-411（本条） | PRD-388（验证台） | 收件箱机制 | 重放包机制 |
|---|---|---|---|---|
| 管什么 | **改的过程看得见** | 纠正可复现验证 | 等人拍板的异步待办 | 重放可复算 |
| 比对 | 改动 vs 接受状态 | 无 | 无 | 无 |
| 关系 | 陪练反馈 出口前的现场 | 被会话消费 | 下游（本条不碰） | 相邻不相干 |

## 4. 会话设计

### 4.1 事件 schema（T2 预埋）

```json
{"schema": "peercorrect-collab-session/v1",
 "events": [{"seq": 1, "event": "propose",
   "entry_id": "e-001",
   "kind": "followup",
   "author": "coach-a（占位）",
   "at": "2026-11-13T09:00:00Z",
   "payload": {"target": "纠正[4]（占位）", "change": "订正建议（占位）"},
   "status": "proposed"},
  {"seq": 2, "event": "accept", "entry_id": "e-001",
   "author": "coach-b（占位）", "at": "…", "status": "accepted"}]}
```

### 4.2 流程（确定性）

提出改动（propose 带署名）→ 同屏可见（日志回放视图）→ 接受/拒绝（accept/reject 带署名）→ 陪练反馈 出口只收 accepted（`outlet` 包装）→ 全过程落 JSONL append-only。

## 5. 失败闸门（T3 落地）

| 错误码 | 触发 | 行为 |
|---|---|---|
| SESSION_INCOMPLETE | 会话事件缺 author/at/entry_id 或 event 词表外 | 拒绝入账 |
| SESSION_STATE_CONFLICT | 状态机违规（重复接受/unknown id/rejected 再接受） | 显形拒绝 |
| LEDGER_DRIFT | 会话日志被删/改首条/accepted 条目无 accept 事件 | 显形拒绝 |

## 6. 衔接

T2 内核（propose/accept/reject + CollabSessionLedger JSONL + outlet + replay）；T3 闸门（append_only+accept 双向对账+出口拦截+一票否决，ERROR_CODES 随模块导出）；T4 划界（标准库-only 钉值+借鉴仓零符号仅代码标识符扫描+R1~R4 红线钉值）；T5 验收（全链两遍逐字节一致+失败演练+链复跑子进程实测+文档无密钥）。

## 7. 开放问题（留待评审/T2）

1. accepted 条目是否要求 accept 人 ≠ propose 人（倾向不强制——单人会话合法，留 T2 按不强制实现）；
2. 回放视图的排序口径（倾向按 seq 稳定排序——待 T2）。

## 8. 领域备注

- 纠正带发音复核+署名落账：误纠在会话里当场可见，学员只收到会话里确认的纠正。
- 基线声明：prototype/tests 既有 1 例环境性失败与本链无关（388 同款口径）。

