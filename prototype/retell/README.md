# 复述（retell）最小切片

「听 → 跟读 → 复述 → 对话」循环中的复述环节：给一段材料，学习者用自己的话讲一遍，
得到内容覆盖、流利度和语法反馈，confirmed 错误回流 M3 变成复习卡。

## 怎么跑

```bash
cd prototype
python -m retell
```

浏览器打开 <http://127.0.0.1:8768/>（端口 `HEARSAY_RETELL_PORT`）。
演示材料复用 M1 的六句，也可以粘贴自己的原文。复述用语音（线上走云端 Whisper，
本地退回 Chromium 浏览器语音识别；计时含停顿）或直接打字，然后点「评估复述」。

## 反馈口径（都不是 LLM 判分，除了语法检测）

- **内容覆盖度**：抽取材料实义词（去停用词、简单词形归一），看复述里出现没有。
  给出比例、已覆盖与遗漏关键词。是词级启发式，不代表语义完整。
- **流利度**：词数；有录音计时时给 WPM（含停顿，不是纯发声时间）。
- **语法**：复用 M2 `detect_errors`——有 `HEARSAY_ANTHROPIC_API_KEY` 走 Claude
  （同样过校验），否则规则扫描；`detection` 字段标明实际检测器。
- **M3 回流**：每次评估生成新 session，confirmed 错误经 `ingest_recap` 写入
  （`HEARSAY_M3_INGEST=0` 关闭），错误档案与 FSRS 卡照常更新。

## 边界

不做语义覆盖度/内容结构评分、不做 SP 类 CanDoEvidence、不做发音反馈；
材料与复述文本不进仓库；M3 存储仍在 `prototype/runtime/`。

## 测试

```bash
python -m unittest discover -s prototype/tests   # 仓库根目录；test_retell.py 覆盖本切片
```
