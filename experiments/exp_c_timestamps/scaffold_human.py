"""issue #4 本地目录与标注模板生成（不创建任何音频或签署件）。

    python exp_c_timestamps/scaffold_human.py --root /path/m1_human_audio \
        --speakers S01 S02 S03 --lines 3 7 12 15 18 21 24 27 30 33

生成：
  audio/Sxx/（空目录，放 A_NN.wav / C_ll.wav）
  annot/Sxx_C_boundaries.csv（clip,tmin,tmax,line 模板，时间留空待 Praat 填）
  manifests/speakers.csv（匿名登记表头）
  README_LOCAL.md（命名、转码、复测命令）
m1_human_audio/ 已在 .gitignore；不要把本目录提交到公开仓。
"""
import argparse
from pathlib import Path

HEADER = "clip,tmin,tmax,line\n"


def scaffold(root, speakers, lines):
    root = Path(root)
    made = []
    for speaker in speakers:
        (root / "audio" / speaker).mkdir(parents=True, exist_ok=True)
        annot = root / "annot" / f"{speaker}_C_boundaries.csv"
        annot.parent.mkdir(parents=True, exist_ok=True)
        annot.write_text(HEADER + "".join(f"C_{line:02d},,,{line}\n" for line in lines))
        made.append(annot)
    (root / "consents").mkdir(exist_ok=True)
    (root / "manifests").mkdir(exist_ok=True)
    (root / "manifests" / "speakers.csv").write_text(
        "speaker_id,level_self,consent_date,consent_form_version,notes\n"
        + "".join(f"{s},,,,\n" for s in speakers))
    (root / "README_LOCAL.md").write_text(f"""# 本地真人录音目录（勿提交公开仓）

- 录音者：{', '.join(speakers)}（匿名编号；先签同意书再录）
- A 组：`audio/Sxx/A_01.wav … A_24.wav`（对应 exp_a_grammar/sentences.json 的 id）
- C 组：`audio/Sxx/C_ll.wav`（ll 为 exp_c_timestamps/sentences.txt 行号）
- 标注：Praat 标句首句尾，填进 `annot/Sxx_C_boundaries.csv` 的 tmin/tmax（秒）
- 转码：`ffmpeg -i input.m4a -ac 1 -ar 16000 -sample_fmt s16 output.wav`
- 复测命令见 docs/ops/m1-recording-protocol.md §8；音频与签署件不入库
""")
    return made


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--root", required=True)
    p.add_argument("--speakers", nargs="+", default=["S01", "S02", "S03"])
    p.add_argument("--lines", nargs="+", type=int,
                   default=[3, 7, 12, 15, 18, 21, 24, 27, 30, 33])
    args = p.parse_args()
    made = scaffold(args.root, args.speakers, args.lines)
    print(f"已在 {args.root} 建好目录与 {len(made)} 份标注模板（{len(args.lines)} 句/人）")


if __name__ == "__main__":
    main()
