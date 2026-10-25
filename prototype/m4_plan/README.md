# M4 每日计划与 can-do 进度页（最小切片）

读 M3 的本地学习者存储：错误档案和 FSRS 到期卡决定今天练什么；
can-do 进度展示 109 条清单与各自的证据计数。**没有宝石，也不自动判 can-do。**

## 怎么跑

```bash
cd prototype
python -m m4_plan --demo   # 种入样例数据并打开进度页
python -m m4_plan          # 直接用现有 M3 数据
```

浏览器打开 <http://127.0.0.1:8767/>（端口 `HEARSAY_M4_PORT`，存储路径 `HEARSAY_M3_STORE`）。

命令行：

```bash
python -m m4_plan --plan --minutes 20           # 打印今日计划 JSON
python -m m4_plan --evidence SI-A2-01 --verdict partial   # 手动记一条证据
```

## 每日计划（M0 §5.3 离线版）

- 模板：听 3 / 跟读 4 / 复述 3 / 对话 5（B2 听 5），按时间预算缩放，
  总时长收敛回预算，差额由对话块吸收。
- 对话块直接用 M3 的复习场景：到期错误代码强制注入，其余按近 30 天频率取前 3。
- `rationale_zh` 回答「为什么今天是这个」：近 30 天高频错误、到期卡数、时间预算。
- 材料生成、跟读自动选材、复述自动评测、`target_can_do_ids` 选取都未接，
  对应块写明用哪个现成切片完成。

## can-do 进度

- 解析 `docs/design/cefr-can-do-listening-speaking.md` 的 109 条（ID 稳定，含等级与技能）。
- 状态：`demonstrated`（有达标证据）/ `emerging`（有证据未达标）/ `not_started`。
  证据计数含 demonstrated / partial 分列；C1/C2 标「保留」，不参与 v1 编排。
- 证据只来自**显式记录**（页面或 `--evidence`）。LLM 判 can-do 的一致性（M0 §6）
  未验证，所以本切片不做自动判定，也不写 CanDoEvidence 到任何统计。

## 边界

没有 Learner 分技能等级更新、没有读写技能 can-do、没有多设备同步；
计划是静态模板的个性化，不是自由编排。

## 测试

```bash
python -m unittest discover -s prototype/tests   # 仓库根目录；test_plan.py 覆盖本切片
```
