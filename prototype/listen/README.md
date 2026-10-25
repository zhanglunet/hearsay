# 听力理解题（listen）最小切片

「听 → 跟读 → 复述 → 对话」循环中的听力环节：逐句播放材料，做理解题，
规则判定后把 H 类错误和 can-do 证据写进 M3 同一存储。

## 怎么跑

```bash
cd prototype
python -m listen
```

浏览器打开 <http://127.0.0.1:8769/>（端口 `HEARSAY_LISTEN_PORT`）。
材料复用 M1 演示（espeak 合成六句 + 词级时间戳），音频按句切片播放。

## 题型与判定（M0 §2.8 的离线子集）

| 题型 | 判定 | 演示题 |
|---|---|---|
| gist / detail（选择） | 选项精确匹配 | q1 主旨（映射 L-A2-01） |
| detail（关键词简答） | 必需关键词全部出现 | q2 细节 |
| dictation（听写） | 逐词对比，difflib ≥0.85 容忍拼写，阈值默认 0.8 | q3（H02） |
| discrimination（二选一听辨） | 选项精确匹配 | q4 could/couldn't（H02，演示映射 L-B1-04） |

inference 与 spoken_response 需要 LLM 判，**未接**。
演示题的 can-do 映射只是演示证据流，完整协议的样本量要求见 can-do 清单。

## 结果与回流

- `/api/finish` 汇总得分与每题对错；同一 can-do 的通过率 ≥0.8 记 `demonstrated`、
  ≥0.64 记 `partial`、否则 `failed`，以 `source=rule` 写入 M4 进度存储。
- 答错且带 `error_codes` 的题生成 H 类 confirmed 错误（`detected_by=rule`），
  经 `ingest_recap` 写入 M3 错误档案与 FSRS 卡（`HEARSAY_M3_INGEST=0` 全部关闭）。
- 重复 finish 返回缓存，不重复写证据与错误；前端看不到答案字段。

## 边界

没有自定义材料与 LLM 出题、没有 inference/spoken_response、没有语速版本与
多口音；H 类判定是题目级规则，不证明具体听辨机理。

## 测试

```bash
python -m unittest discover -s prototype/tests   # 仓库根目录；test_listen.py 覆盖本切片
```
