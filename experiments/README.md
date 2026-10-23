# experiments — M1 技术风险验证

对应设计文档 [第 6 节](../docs/design/2026-10-22-m0-learner-model.md#6-m1-需要验证的风险)。

| 目录 | 验证什么 | 阈值 |
|---|---|---|
| `exp_a_grammar/` | 转写是否保留学习者的语法错误（24 句、29 个植入错误、4 个 macOS 合成音，含 2 个中文语音读英文模拟口音） | 错误保留率 ≥ 80% |
| `exp_b_pronounce/` | OpenPronounce 对中文口音英语评分的稳定性（speechocean762 test 切分，8 种扰动条件） | 同一录音扰动后分数标准差 < 0.1（0–1 归一） |
| `exp_d_phonemes/` | OpenPronounce 音素级输出对照 speechocean762 音素标注（test 切分全部 2500 条；实验 B 的 39 条单独汇总） | 音素级精确率 ≥ 0.60 且召回率 ≥ 0.50；替换方向准确率 ≥ 0.70 |
| `exp_c_timestamps/` | whisperX 词级时间戳精度（Kokoro 合成 50 句，token 时间戳为真值） | 边界误差 < 150 ms 的比例 ≥ 90% |

## 运行

```bash
cd experiments
uv venv --python 3.11 .venv && source .venv/bin/activate
uv pip install torch torchaudio whisperx kokoro openpronounce soundfile numpy scipy pandas pyarrow librosa
# torch>=2.9 的 torchaudio 删掉了 pyannote.audio 3.x 还在用的 AudioMetaData，whisperX 会导入失败；CPU 机器钉到 2.8.0
uv pip install "torch==2.8.0" "torchaudio==2.8.0" --index-url https://download.pytorch.org/whl/cpu
source run_env.sh            # 设置 espeak-ng 库路径等；国内镜像需 HEARSAY_USE_CN_MIRRORS=1
mkdir -p data && curl -L -o data/speechocean762_test.parquet \
  https://huggingface.co/datasets/mispeech/speechocean762/resolve/main/data/test-00000-of-00001.parquet
python exp_a_grammar/run.py && python exp_a_grammar/report.py
python exp_c_timestamps/run.py
python exp_b_pronounce/run.py 40
python exp_d_phonemes/run.py   # 音素级；不跑 8 种扰动。模型加载后中位 0.25 s/条，2500 条约 12 分钟（4 vCPU）
```

`exp_a_grammar/audio/` 里的 wav 由 macOS `say` 生成，已入库（Linux 上无法重新生成）。

结果与结论见 [`docs/design/2026-10-23-m1-risk-validation.md`](../docs/design/2026-10-23-m1-risk-validation.md)（2026-10-23，CPU 运行）。

GitHub Actions（[`.github/workflows/ci.yml`](../.github/workflows/ci.yml)）只做语法检查，不跑上面的 A/B/C/D，也不下载模型或数据集。
