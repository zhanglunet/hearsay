# GitHub 开源项目调研：英语听说学习

调研日期：2026-10-22
方法：`gh search repos` 按星数检索约 30 组关键词（中英文），再对已知项目用 `gh repo view` 核对星数、许可证与最近推送时间。星数为调研当日数值。

## 1. 语音识别（ASR）

| 项目 | 星数 | 许可证 | 最近推送 | 说明 |
|---|---|---|---|---|
| openai/whisper | 111k | MIT | 2026-08 | 基础模型，多语种鲁棒 |
| ggml-org/whisper.cpp | 54.6k | MIT | 2026-10 | C/C++ 移植，端侧与移动端可用 |
| SYSTRAN/faster-whisper | 26.1k | MIT | 2026-10 | CTranslate2 加速，服务端首选 |
| m-bain/whisperX | 24.8k | BSD-2 | 2026-10 | **词级时间戳** + 说话人分离，跟读对齐必需 |
| k2-fsa/sherpa-onnx | 15.4k | Apache-2.0 | 2026-10 | ASR/TTS/VAD/说话人一体，支持 iOS/Android/浏览器离线 |
| KoljaB/RealtimeSTT | 10.2k | MIT | 2026-10 | 低延迟流式识别 + VAD |

## 2. 语音合成（TTS）

| 项目 | 星数 | 许可证 | 最近推送 | 说明 |
|---|---|---|---|---|
| fishaudio/fish-speech | 33.4k | 见仓库 | 2026-10 | 音质好，模型较大 |
| SWivid/F5-TTS | 15.4k | MIT | 2026-10 | 流匹配，零样本音色克隆 |
| rhasspy/piper | 11.3k | MIT | 2025-08 | 轻量本地 TTS，已归档维护 |
| hexgrad/kokoro | 9.6k | Apache-2.0 | 2025-08 | 82M 参数，实时友好，有 JS 版 |
| espeak-ng/espeak-ng | 7.0k | GPL-3 | 2026-09 | 规则型，主要用途是 G2P / 音标 |
| KoljaB/RealtimeTTS | 4.0k | MIT | 2026-10 | 流式 TTS 封装 |

## 3. 发音评测与对齐

| 项目 | 星数 | 许可证 | 最近推送 | 说明 |
|---|---|---|---|---|
| nishuzumi/gemini-teacher | 1.2k | 无 | 2026-08 | 用 Gemini 做发音纠正，思路可借鉴，无许可证不可直接用 |
| MontrealCorpusTools/Montreal-Forced-Aligner | 1.9k | MIT | 2026-10 | Kaldi 强制对齐，音素级 |
| strob/gentle | 1.7k | MIT | 2026-07 | 强制对齐，部署简单 |
| bootphon/phonemizer | 1.6k | GPL-3 | 2026-09 | 文本转音素 |
| Kyubyong/g2p | 934 | Apache-2.0 | 2026-10 | 英文 G2P |
| open-dict-data/ipa-dict | 817 | 多 | 2026-10 | 多语种 IPA 词表 |
| Thiagohgl/ai-pronunciation-trainer | 525 | AGPL-3 | 2025-08 | 完整的发音打分 Web 应用（Whisper + 音素对比） |
| YuanGongND/gopt | 233 | 见仓库 | 2026-10 | ICASSP 2022 多粒度发音评估论文代码 |
| Halleck45/OpenPronounce | 149 | MIT | 2026-08 | **音素级发音评测**，Wav2Vec2 + DTW，自托管替代 Azure |
| frank613/CTC-based-GOP | 42 | 见仓库 | 2026-10 | CTC 版 GOP（Goodness of Pronunciation） |

## 4. 间隔重复

| 项目 | 星数 | 许可证 | 最近推送 | 说明 |
|---|---|---|---|---|
| ankitects/anki | 32.2k | AGPL-3 | 2026-10 | 参考实现；AGPL 不适合直接嵌入 |
| open-spaced-repetition/fsrs4anki | 4.1k | MIT | 2026-08 | FSRS 算法说明与 Anki 调度器 |
| nagisanzenin/engram | 1.5k | MIT | 2026-08 | FSRS 驱动的学习引擎，带自由回忆验证 |
| open-spaced-repetition/ts-fsrs | 829 | MIT | 2026-10 | TypeScript 实现 |
| open-spaced-repetition/py-fsrs | 515 | MIT | 2026-08 | Python 实现 |
| open-spaced-repetition/fsrs-rs | 450 | MIT | 2026-10 | Rust 实现，含优化器 |

## 5. 实时语音 Agent 框架

| 项目 | 星数 | 许可证 | 最近推送 | 说明 |
|---|---|---|---|---|
| pipecat-ai/pipecat | 16.7k | BSD-2 | 2026-10 | VAD → ASR → LLM → TTS 流水线，供应商可插拔 |
| livekit/agents | 14.9k | Apache-2.0 | 2026-10 | 基于 WebRTC，适合多端 |
| huggingface/speech-to-speech | 13.5k | Apache-2.0 | 2026-10 | 纯开源模型的语音对语音 |
| openai/openai-realtime-agents | 7.0k | MIT | 2026-01 | Realtime API 的 Agent 模式示例 |

## 6. 词典、词库、语法

| 项目 | 星数 | 许可证 | 最近推送 | 说明 |
|---|---|---|---|---|
| languagetool-org/languagetool | 15.2k | LGPL-2.1 | 2026-10 | 规则型语法检查 |
| skywind3000/ECDICT | 8.5k | MIT | 2025-03 | 英汉词典数据库，含词频、柯林斯星级、考试标签 |
| yvoronoy/awesome-english | 4.3k | 见仓库 | 2026-10 | 学习资源清单 |
| kajweb/dict | 3.7k | 无 | 2024-04 | 四六级/考研/雅思/托福词库 JSON |

## 7. 同类产品（可借鉴交互或代码）

| 项目 | 星数 | 许可证 | 最近推送 | 说明 |
|---|---|---|---|---|
| ZuodaoTech/everyone-can-use-english | 39.2k | GPL-3 | 2026-06 | 李笑来《人人都能用英语》+ Enjoy App：桌面跟读软件，Whisper 对齐 |
| RealKai42/qwerty-learner | 23.5k | GPL-3 | 2026-09 | 打字背单词，交互轻快 |
| mengxi-ream/read-frog | 10.2k | GPL-3 | 2026-10 | 浏览器沉浸式阅读 + 闪卡 |
| kantord/LibreLingo | 2.6k | AGPL-3 | 2026-06 | 多邻国式开源课程平台 |
| LuteOrg/lute-v3 | 1.6k | MIT | 2026-09 | 通过阅读学语言，词汇状态标记 |
| asbplayer/asbplayer | 1.5k | AGPL-3 | 2026-10 | 字幕句子挖掘播放器 |
| xiaochong/hi-kid | 1.2k | MIT | 2026-04 | 儿童英语口语陪练桌面应用（React + TS） |
| maverickgao8848/kouyu | 200 | 无 | 2026-09 | 以 Claude Code Skill 形式做口语陪练 + 本地复盘 |
| iwangjie/English-Chunks | 106 | 无 | 2026-01 | 英语词块练习 |
| huytd/speech | 83 | BSD-3 | 2026-05 | 口语练习小工具 |
| 1599570912/IELTS-Speaking-AI | 31 | 见仓库 | 2026-07 | 雅思口语：实时识别 + 打分 + 题库 |
| TideSparrow/shadowing-english | 30 | MIT | 2026-10 | 本地优先跟读 App（Flutter），导入自己的视频与字幕 |
| chippeddog/english.now | 13 | 见仓库 | 2026-10 | WIP 的 AI 自学英语应用 |
| PrivaGlot-app/PrivaGlot | 2 | MIT | 2026-10 | 隐私优先口语陪练，FastAPI + WebSocket |

## 8. 结论

1. **底层能力齐备**：ASR（whisperX / sherpa-onnx）、TTS（Kokoro / F5）、发音评测（OpenPronounce）、对齐（MFA）、间隔重复（FSRS）、实时对话流水线（pipecat / livekit）都有活跃且许可证友好的实现。
2. **缺的是编排层**：现有同类项目要么是单点工具（只跟读、只打分、只背单词），要么是固定课程平台。没有一个项目把"学习者模型 → 内容生成 → 听说循环 → 错误回流复习"串成闭环。这是 Hearsay 的差异点。
3. **许可证注意**：Anki、LibreLingo、asbplayer、ai-pronunciation-trainer 是 AGPL；everyone-can-use-english、read-frog、qwerty-learner 是 GPL。只借鉴思路，不直接拷代码。
4. **一个值得深看的近邻**：kouyu 和 oral-english-agent 等项目把"口语陪练"做成了 Claude Code / Codex 的 Skill，说明 Agent 形态的口语陪练已有需求与雏形，但都缺少语音层和学习者模型。
