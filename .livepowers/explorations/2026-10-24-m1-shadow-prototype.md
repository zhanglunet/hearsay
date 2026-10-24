# ship m1 shadow prototype

日期：2026-10-24
意图：`ship m1 shadow prototype`
任务：`t_m1_shadow`
注册表：`lp registry find` 未命中。

## 假设

Hearsay 的本体在 M0 设计文档，不在 `.livepowers/concepts.json`（那是一套无关的通用词表）。这次只用 Material 的句级时间和 Session type `shadow`，不新增对象，不写 ErrorInstance / PhonemeProfile。

## 事实来源

- `docs/design/2026-10-23-m1-risk-validation.md`：A/B/C 通过，D 精确率 0.148（results.json 为 0.1481）
- `experiments/exp_d_phonemes/results.json`
- GitHub issue #4 仍开放，#8 仍开放，#1 与 #3 已关闭
- main `d22c0fb` 的 README 仍写「尚无代码」，与 `experiments/` 不符

## 落地

- 状态清单：`docs/design/2026-10-24-status-checklist.md`
- 原型：`prototype/m1_shadow/`，页面 `prototype/web/`，合成演示音 `prototype/fixtures/demo/`
- 词级切句、词召回 < 0.75 才标低分；接口强制清空音素写入
- 跟读录音不落盘。本机 ASR 仅当 `HEARSAY_ASR=faster-whisper`

## 核对

- `python -m unittest discover -s prototype/tests -v`：29 项通过
- 浏览器：演示句播放时间前进；错误转写标低分；正确转写取消低分；无时间戳导入走比例估计；有时间戳导入走词级切句；没有录音时并排按钮保持禁用；假麦克风录音后可以回放
- 桌面浏览器没有麦克风权限，录像只覆盖播放和粘贴转写。录音路径用假设备另测

## 未决

- #8 不关闭：默认不转写跟读，比例切句不是 whisperX，没有学习者模型
- #4 仍开放，没有真人录音
