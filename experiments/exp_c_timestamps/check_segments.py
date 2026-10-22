"""实验 C 补充：whisperX 的 segment 能否直接当句边界。
复用 run.py 生成的 audio/para_*.{wav,json}（先跑 run.py），配置与 run.py 相同（large-v3 / int8 / CPU）。
分别检查 transcribe 输出的 segments 和 align 之后（按标点分句）的 segments 与真值句是否一一对应：
每个真值句只与 1 个 segment 在时间上重叠 > 50 ms，且每个 segment 只覆盖 1 句。结果写 segments.json。
"""
import json, glob
from pathlib import Path
import numpy as np, torch

# 同 run.py：torch>=2.6 默认 weights_only=True，whisperX 自带的 pyannote VAD 权重加载会失败
_orig_torch_load = torch.load
def _torch_load_compat(*a, **k):
    if k.get("weights_only") is None: k["weights_only"] = False
    return _orig_torch_load(*a, **k)
torch.load = _torch_load_compat
import whisperx

HERE = Path(__file__).parent

def match(segs, sents):
    per_sent = [[k for k, g in enumerate(segs) if min(g["end"], s["end"]) - max(g["start"], s["start"]) > 0.05] for s in sents]
    per_seg = [sum(1 for ov in per_sent if k in ov) for k in range(len(segs))]
    one2one = len(segs) == len(sents) and all(len(o) == 1 for o in per_sent) and all(c == 1 for c in per_seg)
    return one2one, per_sent, per_seg

model = whisperx.load_model("large-v3", device="cpu", compute_type="int8", language="en")
am, meta = whisperx.load_align_model(language_code="en", device="cpu")
paras = []; ds, de = [], []
for wav in sorted(glob.glob(str(HERE / "audio" / "para_*.wav"))):
    truth = json.load(open(wav.replace(".wav", ".json"))); audio = whisperx.load_audio(wav)
    res = model.transcribe(audio, batch_size=8, language="en")
    al = whisperx.align(res["segments"], am, meta, audio, "cpu", return_char_alignments=False)
    tseg = res["segments"]; aseg = [g for g in al["segments"] if "start" in g]
    t_ok, _, t_per_seg = match(tseg, truth["sents"])
    a_ok, a_per_sent, a_per_seg = match(aseg, truth["sents"])
    if a_ok:
        for s, g in zip(truth["sents"], aseg): ds.append(abs(g["start"] - s["start"])); de.append(abs(g["end"] - s["end"]))
    paras.append(dict(para=Path(wav).stem, n_sents=len(truth["sents"]),
                      transcribe_segments=len(tseg), transcribe_one2one=t_ok, transcribe_sents_per_seg=t_per_seg,
                      aligned_segments=len(aseg), aligned_one2one=a_ok, aligned_sent_to_segs=a_per_sent,
                      aligned_texts=[g["text"].strip() for g in aseg]))
    print(paras[-1]["para"], "sents", len(truth["sents"]), "| transcribe segs", len(tseg), t_ok, "| aligned segs", len(aseg), a_ok, flush=True)
ds, de = np.array(ds), np.array(de)
summary = {
    "paragraphs": len(paras), "sentences": sum(p["n_sents"] for p in paras),
    "transcribe_segments": sum(p["transcribe_segments"] for p in paras),
    "transcribe_one2one_paragraphs": sum(p["transcribe_one2one"] for p in paras),
    "aligned_segments": sum(p["aligned_segments"] for p in paras),
    "aligned_one2one_paragraphs": sum(p["aligned_one2one"] for p in paras),
    "aligned_one2one_sentences": int(len(ds)),
    "aligned_sent_start_median_ms": round(float(np.median(ds)) * 1000, 1),
    "aligned_sent_start_frac_lt_150ms": round(float((ds < 0.15).mean()), 3),
    "aligned_sent_end_median_ms": round(float(np.median(de)) * 1000, 1),
    "aligned_sent_end_frac_lt_150ms": round(float((de < 0.15).mean()), 3),
}
json.dump(dict(summary=summary, paragraphs=paras), open(HERE / "segments.json", "w"), indent=1, ensure_ascii=False)
print(json.dumps(summary, indent=1))
