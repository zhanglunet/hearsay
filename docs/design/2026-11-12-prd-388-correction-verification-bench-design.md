# PRD-388/T1：纠正验证台设计（纠正发音模型复核过才进陪练反馈）

> trend issue #1892。来源：2026-11-12 GitHub 趋势日报（digests/2026-11-12.md）第 16 条，用户 2026-11-13 指令「拍板」采纳。
> 设计日：2026-11-12 · 目标仓库：zhanglunet/hearsay
> 状态：T1 设计草案，待评审。仅设计文档（纯加法 .md）；验证台内核（T2）、闸门（T3）、划界断言（T4）、验收试运行（T5）按本设计后续落地。
> 示例全部虚构占位，不出现真实内部主机名、IP、账号或密钥。

## 0. PR 门槛自查（repos.yaml default_pr_gate）

| 门槛 | 落实 |
|---|---|
| require_integration_point | **接入点：`prototype/m1_shadow/feedback.py::word_feedback` 产出纠正（word_recall/error_instances）之后、陪练反馈出口（learner 会话把纠正递给学员）之前**——T2 验证台以注入式函数 `verify_correction(correction, corpus, recheck_fn)` 供陪练流程在反馈前调用；只把 VERIFIED 的纠正递给学员 |
| no_missing_channel | 只消费 word_feedback 既有纠正结构与参考句语料注入；复算=对同一参考句语料重跑同一发音模型复核（recheck_fn 注入，复用 word_feedback 既有对齐形态）；验证结论写本地 JSONL 账本（文件落库），零新外部渠道 |
| no_duplicate_module | main 上同类模块盘点：m1_shadow/feedback.py（纠正产出本体——word_feedback 对齐计算）/m3_learner/store.py（学习记录）。**本条不另起对齐模型**：复算=注入式重跑同一 word_feedback 形态对齐，比对纠正的 error_instances 与重跑一致才 VERIFIED |
| impl_requires_devlog | T2~T5 实现 PR 各附 docs/devlog/2026-11-13-prd-388-*.md 开发记录+合规核对；账本落 JSONL 文件（路径注入），不只存内存 |

## 1. 红线

| # | 红线 | 落地方式 |
|---|---|---|
| R1 | **纠正模型复核过才进陪练反馈** | 每条发音/表达纠正先按发音模型复核验证（同 reference+hypothesis 重跑对齐；重跑 error_instances 与纠正一致）；复核不过 → UNVERIFIED——误纠拦在陪练反馈外（防教错非母语学员） |
| R2 | **验证不产生新纠正** | 复算=重跑注入的同一对齐复核（参考句语料只读深拷贝），零新增对齐逻辑；复现不出=UNVERIFIED 不猜不补 |
| R3 | **机器可读落账** | 每次验证 `{correction_id, learner_id, kind, source_ref, corpus_fingerprint, correction, reproduce, verdict}` 八件套落 JSONL 账本；缺任一 BENCH_INCOMPLETE 拒绝入账 |
| R4 | **账本 append-only + 修复二次验证才关闭** | 验证账本只增不删；语料变更后二次验证落新记录，关闭以最新 VERIFIED 为准 |
| R5 | 占位符纪律 | T5 检查覆盖本文件 |
| R6 | 实现 PR 只开不合并 | 等用户 review |

## 2. 借鉴对象、许可证与不复用红线

openai/codex-security（Apache-2.0，实测）+ cloudflare/security-audit-skill（MIT，实测）——只借鉴「发现→验证→修复→再验证」控制面形态；条目 schema 按本仓陪练域自研，零代码复用，不引入原仓依赖。

## 3. 与既有机制划界

| 维度 | PRD-388（本条） | m1_shadow.feedback | m3_learner.store |
|---|---|---|---|
| 管什么 | 逐条 **纠正可复核** | 纠正产出 | 学习记录 |
| 比对 | 纠正 vs 重跑对齐 | 无 | 无 |
| 关系 | word_feedback 之后、反馈出口之前 | 被消费 | 下游 |

## 4. 验证台设计

### 4.1 条目 schema（T2 预埋）

```json
{"schema": "correction-verify-bench/v1",
 "items": [{"correction_id": "c-001",
   "learner_id": "learner-1（占位）",
   "kind": "word_recall",
   "source_ref": "m1-shadow-feedback/v1#corrections[0]（占位）",
   "corpus_fingerprint": "sha16:…（参考句语料快照）",
   "correction": {"reference": "…（占位）", "hypothesis": "…（占位）",
                  "error_instances": ["…（占位）"]},
   "reproduce": {"instances_match": true, "detail": "…（占位）"},
   "verdict": "VERIFIED|UNVERIFIED"}]}
```

### 4.2 流程（确定性）

word_feedback 纠正 → 重跑同一对齐（注入 recheck_fn，语料深拷贝）→ 重跑 error_instances 与纠正一致 → VERIFIED / 否则 UNVERIFIED → 落账 → 学员只收 VERIFIED。

## 5. 失败闸门（T3 落地）

| 错误码 | 触发 | 行为 |
|---|---|---|
| BENCH_INCOMPLETE | 八件套缺一/词表外 | 拒绝入账 |
| BENCH_REPRO_MISMATCH | 声称 VERIFIED 但重跑 error_instances 与纠正不一致（或反之） | 显形拒绝 |
| BENCH_STALE | 语料快照指纹与当前不符 | 拒绝复用旧验证 |

## 6. 衔接

T2 内核（verify_correction + JSONL 账本）；T3 闸门（三码+零网络 AST）；T4 划界（标准库-only 钉值+借鉴仓零符号+与 feedback/store 划界钉值）；T5 样例全链回放+UNVERIFIED 拦截演练+文档无密钥（基线声明：prototype/tests 既有 1 例环境性失败如实声明）。

## 7. 开放问题（留待评审/T2）

1. 发音（phoneme）级复现口径（m1 现为词级对齐；phoneme 写入已被 seal——倾向词级复算+phoneme 零触碰，待 T2）；
2. 陪练反馈出口的强制方式（倾向 verify_corrections 包装供 learner 会话显式接入——待 T2）。
