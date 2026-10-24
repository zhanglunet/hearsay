"""实验 C 真人复测：原文首末词匹配 whisperX 词级时间戳，对照人工句边界（issue #4）。

输入（本地私有目录，音频与标注原文件勿入库，见 docs/ops/m1-recording-protocol.md）：
  --audio-root  m1_human_audio/audio，含 Sxx/C_ll.wav（ll 为 sentences.txt 行号）
  --annot       m1_human_audio/annot，含每名说话人一个 Sxx_C_boundaries.csv

标注 CSV 列：clip,tmin,tmax,line
  clip         不带扩展名的音频文件名，如 C_03
  tmin,tmax    人工标注的句首 / 句尾，秒，相对该条 wav 起点
  line         sentences.txt 行号（1-based）
一条 clip 可有多行（多句连录），同一 clip 内按 line 排序后拼接原文做匹配。

方法：whisperX large-v3 transcribe + align 取 word_segments；用 difflib 把原文词序
对齐到识别词序，取每句首末词对应的识别词时间戳作为假设句边界，与人工边界比误差。
只有首末词都匹配上的句子计入误差统计，未匹配句单列计数。
阈值沿用 issue #4：句边界误差 < 150 ms 的比例 ≥ 90%。

输出（可入库，不含音频与身份信息）：
  results_human_boundaries.csv、results_human.json

核心函数不依赖 whisperX / torch，可用 test_retest_human.py 单独测试。
"""
import argparse, csv, difflib, json, re, statistics
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).parent
SENTS = [l.strip() for l in open(HERE / "sentences.txt") if l.strip()]
THRESHOLD_S = 0.15
PASS_FRAC = 0.90


def norm(w):
    return re.sub(r"[^a-z']", "", w.lower())


def ref_words(lines):
    """按行号拼原文，返回 (词表, 每句 (首词下标, 末词下标))。"""
    words, spans = [], []
    for line in lines:
        if not 1 <= line <= len(SENTS):
            raise ValueError(f"行号 {line} 超出 sentences.txt 范围（1–{len(SENTS)}）")
        ws = SENTS[line - 1].split()
        if not ws:
            raise ValueError(f"sentences.txt 第 {line} 行是空行")
        spans.append((len(words), len(words) + len(ws) - 1))
        words.extend(ws)
    return words, spans


def read_annotations(path):
    rows = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            rows.append(dict(clip=r["clip"].strip(), line=int(r["line"]),
                             tmin=float(r["tmin"]), tmax=float(r["tmax"])))
    if not rows:
        raise ValueError(f"{path} 没有标注行")
    return rows


def match_sentence_boundaries(words, spans, hyp):
    """原文首末词 → 识别词时间戳。hyp 为 whisperX word_segments（含 start/end）。
    返回每句 (h_start, h_end)，首末词任一未匹配则为 None。"""
    sm = difflib.SequenceMatcher(a=[norm(w) for w in words],
                                 b=[norm(w["word"]) for w in hyp], autojunk=False)
    mapping = {}
    for tag, a0, a1, b0, b1 in sm.get_opcodes():
        if tag == "equal":
            for k in range(a1 - a0):
                mapping[a0 + k] = b0 + k
    out = []
    for first, last in spans:
        if first in mapping and last in mapping:
            out.append((hyp[mapping[first]]["start"], hyp[mapping[last]]["end"]))
        else:
            out.append(None)
    return out


def summarize(rows):
    matched = [r for r in rows if r["ds"] is not None]
    starts = [r["ds"] for r in matched]
    ends = [r["de"] for r in matched]
    both = starts + ends

    def frac(xs):
        return round(sum(x < THRESHOLD_S for x in xs) / len(xs), 3) if xs else None

    def med(xs):
        return round(statistics.median(xs) * 1000, 1) if xs else None

    overall = frac(both)
    return dict(sentences=len(rows), matched=len(matched), unmatched=len(rows) - len(matched),
                sent_start_median_ms=med(starts), sent_end_median_ms=med(ends),
                sent_start_frac_lt_150ms=frac(starts), sent_end_frac_lt_150ms=frac(ends),
                sent_boundary_frac_lt_150ms=overall,
                threshold="句边界误差 < 150 ms 的比例 >= 0.90",
                passed=overall is not None and overall >= PASS_FRAC)


def evaluate_clip(annotations, hyp):
    """一条 clip 的标注行 + 识别词 → 误差行。annotations 须同属一个 clip。"""
    annotations = sorted(annotations, key=lambda r: r["line"])
    words, spans = ref_words([r["line"] for r in annotations])
    bounds = match_sentence_boundaries(words, spans, hyp)
    rows = []
    for r, b in zip(annotations, bounds):
        row = dict(clip=r["clip"], line=r["line"], tmin=r["tmin"], tmax=r["tmax"])
        if b is None:
            row.update(h_start=None, h_end=None, ds=None, de=None)
        else:
            row.update(h_start=round(b[0], 3), h_end=round(b[1], 3),
                       ds=abs(b[0] - r["tmin"]), de=abs(b[1] - r["tmax"]))
        rows.append(row)
    return rows


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--audio-root", type=Path, required=True)
    p.add_argument("--annot", type=Path, required=True)
    args = p.parse_args()

    # 兼容垫片：torch>=2.6 默认 weights_only=True，whisperX 的 pyannote VAD 权重加载会失败
    import torch
    _orig_torch_load = torch.load
    def _torch_load_compat(*a, **k):
        if k.get("weights_only") is None: k["weights_only"] = False
        return _orig_torch_load(*a, **k)
    torch.load = _torch_load_compat
    import whisperx

    model = whisperx.load_model("large-v3", device="cpu", compute_type="int8", language="en")
    align_model, meta = whisperx.load_align_model(language_code="en", device="cpu")

    rows = []
    for speaker_dir in sorted(args.audio_root.glob("S*")):
        if not speaker_dir.is_dir():
            continue
        annot_path = args.annot / f"{speaker_dir.name}_C_boundaries.csv"
        if not annot_path.exists():
            print(f"{speaker_dir.name}: 缺 {annot_path.name}，跳过")
            continue
        clips = defaultdict(list)
        for r in read_annotations(annot_path):
            clips[r["clip"]].append(r)
        for clip, annotations in sorted(clips.items()):
            wav = speaker_dir / f"{clip}.wav"
            audio = whisperx.load_audio(str(wav))
            res = model.transcribe(audio, batch_size=8, language="en")
            aligned = whisperx.align(res["segments"], align_model, meta, audio, "cpu",
                                     return_char_alignments=False)
            hyp = [w for w in aligned["word_segments"] if "start" in w]
            clip_rows = evaluate_clip(annotations, hyp)
            for r in clip_rows:
                r["speaker"] = speaker_dir.name
            rows.extend(clip_rows)
            n_unmatched = sum(r["ds"] is None for r in clip_rows)
            print(f"{speaker_dir.name}/{clip}: {len(clip_rows)} 句，{n_unmatched} 句首末词未匹配", flush=True)

    if not rows:
        raise SystemExit("没有任何评估行：检查 --audio-root / --annot 目录与命名")

    fields = ["speaker", "clip", "line", "tmin", "tmax", "h_start", "h_end", "ds", "de"]
    with open(HERE / "results_human_boundaries.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    per_speaker = {sp: summarize([r for r in rows if r["speaker"] == sp])
                   for sp in sorted({r["speaker"] for r in rows})}
    report = dict(summary=summarize(rows), per_speaker=per_speaker)
    json.dump(report, open(HERE / "results_human.json", "w"), indent=1, ensure_ascii=False)
    print(json.dumps(report, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
