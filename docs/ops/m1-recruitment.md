# M1 真人录音：招募话术与开录清单（issue #4）

配合 [同意书](m1-consent.md) 和 [采集规范](m1-recording-protocol.md) 使用。
复测脚本已就绪，录音到齐后按规范 §8 两条命令出结果。

## 招募话术（可直接转发）

> 我在做一个英语听说练习工具的开源实验，想请你帮个忙录几段英文朗读，大约 20 分钟。
>
> - 录什么：24 个短句（有的句子故意写错了语法，请**照着读，不要改**），
>   再加 10 句左右的日常英语。
> - 怎么录：手机录音机就行，安静房间，别开降噪。我会告诉你每句怎么存。
> - 数据怎么用：只用于语音识别准确率测试。**你的录音默认不会公开、不会上传 GitHub**；
>   公开的只有不含姓名的统计数字。保存 30 天，之后删除；你随时可以要求提前删除或撤回。
> - 需要你：年满 18 岁、中文母语、英语大约 A2–B2（能朗读短句即可，不要求口音好）。
>
> 愿意的话我把知情同意书发你，确认后再开始。

## 开录前（组织方）

- [ ] 找齐 ≥3 人，水平不要全在同一档；同意书联系人占位已换成真人
- [ ] 每人先签同意书（或电子确认），再分配匿名编号 S01、S02…
- [ ] 说好两件事：**照读错误句不要纠正**；读错可以整句重录一条，不用追求完美
- [ ] 手机开勿扰，导出 WAV 或 m4a 后转 16 kHz 单声道 WAV（规范 §2 有 ffmpeg 命令）
- [ ] 一条命令建好目录与标注模板：
  `python experiments/exp_c_timestamps/scaffold_human.py --root /path/m1_human_audio --speakers S01 S02 S03`

## 录制与整理

- [ ] A 组：24 句，存 `m1_human_audio/audio/Sxx/A_01.wav … A_24.wav`
- [ ] C 组：≥10 句（`experiments/exp_c_timestamps/sentences.txt` 行号），存 `C_ll.wav`
- [ ] 场记：日期、设备、环境、C 组行号、有无重录（只存本地）
- [ ] 句边界标注：Praat 标句首句尾，导出 CSV，列 `clip,tmin,tmax,line`，放 `annot/Sxx_C_boundaries.csv`
- [ ] `m1_human_audio/` 已在 `.gitignore`，**音频、签署件、花名册都不提交**

## 复测（在 experiments/ 环境，torch 钉 2.8.0）

```bash
python exp_a_grammar/run.py --audio-root /path/m1_human_audio/audio --out results_human.csv
python exp_a_grammar/report_human.py
python exp_c_timestamps/retest_human.py --audio-root /path/m1_human_audio/audio --annot /path/m1_human_audio/annot
```

报告写清：真人 vs 合成保留率、verbatim prompt 是否仍有效、句边界 <150ms 比例是否 ≥90%，
每个阈值写「达到 / 未达到」和数字。
