# PRD-457/T5 开发记录：陪练监督台验收试运行（2026-11-16）

## 交付

- `prototype/tests/test_prd457_t5_supervision_acceptance.py`：T1 §6 验收试运行，6 例全绿（见下）。
- 本文件：试运行记录。

## 验收（T1 §6：全链两遍逐字节一致 + 失败演练 + 链复跑子进程实测 + 文档无密钥）

- ① 全链跑通：出纠正 → 批注「换说法」→ 一键发回 → agent 改完回来（v2，旧批注原样带回、发回轮次记下回版对照）→ 教练复核点头 → 账本落账 4 条（pending/returned/revised/approved）→ 闸门放行 v2 → 陪练反馈出口只放行已点头的纠正（passed 1，blocked 1）；账本文件与内存条目逐行一致。
- ② 全链两遍逐字节一致：同一条链（固定时间戳）在两个隔离账本目录各跑一遍，账本条目 + 闸门裁决 + 出口结果的规范 JSON 逐字节一致。
- ③ 失败演练：无记录出口 → SUPERVISION_OUTLET_BYPASS 拦截并告警；未点头 → NOT_APPROVED；旧点头不放行新版 → VERSION_MISMATCH；账本首条被删 → LEDGER_DRIFT 全批拒绝。
- ④ 链复跑：失败演练后在全新账本 + 全新闸门上重跑全链仍跑通；另在子进程里把本验收文件完整重跑一遍（环境变量守卫防递归），证明链路不依赖本进程内存状态。
- ⑤ 文档无密钥：T1 设计文档 + 本 PRD 的 T2/T3/T4/T5 开发记录扫描无密钥赋值、私网 IP、令牌字面量（占位写法除外）。
- 未改动 T1–T4 的设计与实现：本 PR 只加验收测试与本记录；T2/T3/T4 旧测试同跑全过（见测试结果）。

## 测试结果

- 本地：`python3 -m unittest discover prototype/tests -p "test_prd457_t5_supervision_acceptance.py"`：6 例全绿（含子进程复跑）。
- 旧测试同跑：`python3 -m unittest discover prototype/tests`：T2/T3/T4 旧测试 57 例 + T5 新测 6 例，共 63 例全过。全量套件以 CI 为准。
- 零网络零子进程（除④的子进程复跑一项）；示例全虚构占位。

## PR 门槛合规核对（repos.yaml default_pr_gate）

| 门槛 | 落实 |
|---|---|
| require_integration_point | 接入点=陪练 agent 出纠正之后、陪练反馈出口之前；本 PR 在该接入点上把 T2–T4 全链实测跑通，不新增接入点 |
| no_missing_channel | 验收只用 T2/T3 已有本地 JSONL 账本与闸门审计，零新外部渠道；子进程复跑只跑本地测试 |
| no_duplicate_module | 不新增监督模块，只加验收测试与开发记录 |
| impl_requires_devlog | 本文件即 T5 开发记录 |

## 借鉴与许可证

- 只借形态：plannotator（Apache-2.0）、ag-ui（MIT）——本测试为原创代码，未复用其代码；LoopForge（无 LICENSE）只借「人工批准门」形态，零代码零文本复用。
- 只开 PR 不合并，等用户 review。
