# M3 学习者模型 + FSRS（最小切片）

把 M2 复盘里的 **confirmed** 错误变成 FSRS 复习卡，并把到期错误代码注入新场景的
objectives，让复习以「在新对话里再用对一次」的方式发生，而不是翻卡片。

## 怎么跑

```bash
cd prototype
python -m m3_learner --demo        # 离线演示：样例复盘 → 错误档案 → 复习计划

# 接真实数据：把 M2 /api/end 的响应存成 recap.json
python -m m3_learner --recap /path/recap.json
python -m m3_learner --plan                       # 当前到期卡与复习场景
python -m m3_learner --review error:G04 --rating 3 # 复习后评分（1/2/3/4）
python -m m3_learner --export                     # 整体导出 JSON
python -m m3_learner --delete                     # 删除全部学习者数据
```

默认数据文件 `prototype/runtime/m3-learner.json`（已 gitignore），`--store` 可改。
命令在仓库根目录运行时先 `cd prototype`，或直接 `PYTHONPATH=prototype python -m m3_learner`。

## 数据流

```text
M2 /api/end 复盘（batch.confirmed）
  → ingest：ErrorInstance（confirmed）+ ErrorPattern（count_total / 30d / 7d）
  → 每个错误代码一张 FSRS 卡（remediation.status = scheduled）
  → review_plan：到期代码强制入选，其余按 count_30d 取前 3
  → build_review_scenario：基于 M2 场景生成带 target_error_codes 的复习场景
  → 复习后 --review 评分，FSRS 推进 stability / difficulty / due
```

口径：**discarded 不计入任何统计**；没有 batch 的复盘不产生写入；
同一 `session_id` 重复导入自动跳过。

## 边界（与完整 M3 的差距）

- FSRS 是 **FSRS-4.5 新卡 + 复习态核心公式**（19 个默认权重，90% 可提取率），
  不含短期学习态和参数自定义；单学习者、单 JSON 文件、原子写入。
- `ErrorPattern` 没有 opportunities / error_rate / tier_weight / stubbornness，
  `trend` 一律 `insufficient_data`；场景选取是简化版 M0 §5.2。
- 没有 LexicalItem / 词项卡、SkillEstimate 更新、CanDoEvidence、DailyPlan 编排（M4），
  也没有把复习场景接回 M2 导师的在线通道（目前输出 scenario JSON，人工/脚本对接）。
- 评分由用户或组织方给出；LLM 自动判「这次用对了吗」还没做。

## 测试

```bash
python -m unittest discover -s prototype/tests   # 仓库根目录；test_learner.py 覆盖本切片
```

FSRS 不变量（R(S)=0.9、I(90%)=S、good 升 stability、again 降 stability 升 difficulty）、
导入幂等、discarded 豁免、窗口计数、到期强制入选与场景注入都有断言。
