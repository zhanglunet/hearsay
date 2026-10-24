# M1 跟读原型

对应 [issue #8](https://github.com/zhanglunet/hearsay/issues/8)。这是一条能在本机跑起来的竖切，不是学习者模型，也不是可勾选的 M1。

状态对照：[2026-10-24 状态清单](../docs/design/2026-10-24-status-checklist.md)。

## 它做什么

1. 打开页面就有一段合成演示材料：六句日常英语，按词级时间戳切成句。
2. 也可以导入自己的参考音频和原文。有词级时间戳 JSON 时按词序切句；没有就按词数比例估计，页面会标明。
3. 逐句播放原句。
4. 用麦克风录跟读，和原句先后播放。录音只留在浏览器内存里。
5. 有转写时计算词级召回 / 精确率，召回低于 0.75 的句子高亮。恰好 0.75 不高亮。

转写从三条路来，默认都不下载模型：

- 浏览器的语音识别（Chromium 系才有，而且会归一化，不是实验 A 的 verbatim whisperX）
- 自己把跟读内容粘贴进去
- 本机 faster-whisper：安装了对应包就自动启用，不用手动配置；想强制关闭可把 `HEARSAY_ASR` 设为其他值，显式打开则设为 `faster-whisper`。只有首次转写才下载模型，启动不会下载。没安装时 `/api/transcribe` 直接拒绝并给出安装提示，不会加载模型

## 它故意不做什么

实验 D 没过。OpenPronounce 音素级精确率 **0.148**（召回率 0.759，替换方向准确率 0.351，见 [风险报告 §6](../docs/design/2026-10-23-m1-risk-validation.md)）。

所以这个原型：

- 不产生 P 类 `ErrorInstance`
- 不填 `PhonemeProfile.accuracy_mean_30d`
- 不写 `common_substitution`
- 不调用 OpenPronounce
- 也不把任何结果写进学习者模型（没有 Learner、没有 FSRS、没有 can-do 证据、没有每日计划）

低分句只表示「参考词没说全」，不是「某个音素错了」。接口层会把请求里夹带的音素字段丢掉。

句尾留白沿用报告 §4.4：末词终点后再加最多 250ms，并且不超过下一词起点。没有用 whisperX 的 VAD 分段来切句。

## 怎么跑

需要 Python 3.11 或 3.12，只用标准库。

```bash
cd prototype
python -m m1_shadow
```

浏览器打开 <http://127.0.0.1:8765/> 。服务只监听 `127.0.0.1`。换端口用 `HEARSAY_M1_PORT`。不要把 HTML 文件直接双击打开，麦克风和接口都走这个本地服务。

跟读录音不要提交。已签署的同意书也不要提交。`prototype/runtime/` 已忽略；正常使用时录音根本不会落盘。

演示音频是 espeak-ng 合成的参考音，在 `fixtures/demo/reference.wav`，不是学习者录音，可以留在仓库里。重新生成（需要本机有 espeak-ng，CI 不跑这一步）：

```bash
cd prototype
python -m m1_shadow.build_demo
```

## 词级时间戳格式

`start_ms` / `end_ms`，或者 whisperX 那种以秒为单位的 `start` / `end`：

```json
{
  "words": [
    {"word": "I", "start_ms": 0, "end_ms": 180},
    {"word": "usually", "start_ms": 180, "end_ms": 640}
  ]
}
```

词序必须和原文一致。对不上就报错；导入界面会退回比例切句，并留下警告。比例切句不是 whisperX 对齐。

## 测试

```bash
python -m unittest discover -s prototype/tests -v
```

在仓库根目录执行。测试不下载模型，也不跑 `experiments/` 里的 A/B/C/D。

## 相对 #8 还缺什么

- 默认路径的自动转写依赖本机安装 faster-whisper（装了才启用）。没装、没有浏览器识别、也没有粘贴时，只能并排回放，算不出词级相似度。
- 导入材料若没有词时间戳，切句是比例估计。
- 演示声音是逐句 espeak-ng，句内词时间是按孤立词时长比例铺进去的，不是自然语流上的 whisperX 对齐。
- 没有会话存储，没有学习者模型，没有音素反馈。
- 真人录音复测仍是 [issue #4](https://github.com/zhanglunet/hearsay/issues/4)，这个原型不采集录音。

因此路线图上的 M1 仍不勾选，#8 也不应关闭。
