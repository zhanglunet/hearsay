"""实验 B：OpenPronounce 对中文口音英语的评分稳定性。
数据：speechocean762 test 切分（中国学习者朗读英语，专家打分）。
稳定性：同一录音在 7 种条件下（原始×2、增益±6dB、白噪 SNR 30/20 dB、电话带宽、前置 100ms 静音）的分数标准差（分数归一到 0–1）。
有效性（附带）：原始分数与人工 total 的 Spearman 相关；被标记单词与人工单词分的精确率/召回率。
"""
import os, io, json, time, sys
os.environ.setdefault("OPENPRONOUNCE_TTS", "kokoro")
os.environ.setdefault("OPENPRONOUNCE_DEVICE", "cpu")
from pathlib import Path
import numpy as np, pandas as pd, soundfile as sf, librosa
from scipy.stats import spearmanr

HERE = Path(__file__).parent
N = int(sys.argv[1]) if len(sys.argv) > 1 else 40
SR = 16000
rng = np.random.default_rng(42)

df = pd.read_parquet(HERE.parent / "data" / "speechocean762_test.parquet")
df["nwords"] = df.text.str.split().str.len()
df = df[df.nwords >= 4].copy()
# 按 total 分三层、按 speaker 去重抽样
df["band"] = pd.cut(df.total, [-1, 5, 7, 10], labels=["low", "mid", "high"])
sample = (df.sort_values("total").groupby("band", observed=True, group_keys=False)
            .apply(lambda g: g.drop_duplicates("speaker").sample(min(len(g.drop_duplicates("speaker")), N // 3), random_state=1)))
sample = sample.head(N)
print("sampled", len(sample), "utterances; total score dist:", sample.total.value_counts().sort_index().to_dict(), flush=True)

def decode(a):
    b = a["bytes"] if isinstance(a, dict) else a
    wav, sr = sf.read(io.BytesIO(b))
    if wav.ndim > 1: wav = wav.mean(1)
    if sr != SR: wav = librosa.resample(wav.astype(np.float32), orig_sr=sr, target_sr=SR)
    return wav.astype(np.float32)

def add_noise(w, snr_db):
    p = np.mean(w**2) + 1e-12; n = rng.standard_normal(len(w)).astype(np.float32)
    n *= np.sqrt(p / (10 ** (snr_db / 10)) / (np.mean(n**2) + 1e-12)); return np.clip(w + n, -1, 1)
def telephone(w):
    lo = librosa.resample(w, orig_sr=SR, target_sr=8000); return librosa.resample(lo, orig_sr=8000, target_sr=SR)[:len(w)]
CONDS = {
    "orig": lambda w: w, "orig_repeat": lambda w: w,
    "gain+6dB": lambda w: np.clip(w * 2.0, -1, 1), "gain-6dB": lambda w: w * 0.5,
    "noise_snr30": lambda w: add_noise(w, 30), "noise_snr20": lambda w: add_noise(w, 20),
    "telephone_8k": telephone, "shift_100ms": lambda w: np.concatenate([np.zeros(int(0.1*SR), np.float32), w]),
}

from openpronounce import compare_audio_with_text
import inspect
sig = inspect.signature(compare_audio_with_text); print("compare_audio_with_text", sig, flush=True)
kw = {}
for cand in ("prosody", "with_prosody", "compute_prosody"):
    if cand in sig.parameters: kw[cand] = False

rows = []; words_rows = []
t_all = time.time()
for i, (_, r) in enumerate(sample.iterrows()):
    wav = decode(r["audio"]); text = r["text"]
    for cname, fn in CONDS.items():
        w = fn(wav); t0 = time.time()
        try:
            res = compare_audio_with_text(w, text, **kw)
        except TypeError:
            res = compare_audio_with_text(w, text)
        dt = time.time() - t0
        d = res.get("differences", {})
        rows.append(dict(idx=i, speaker=r["speaker"], text=text, human_total=r["total"], human_accuracy=r["accuracy"],
                         cond=cname, score=res["score"], per=d.get("phoneme_error_rate"), wer=d.get("word_error_rate"),
                         acoustic=res.get("acoustic_distance"), n_flagged=len(d.get("errors", [])), sec=round(dt, 2)))
        if cname == "orig":
            flagged = {e["word"].lower().strip(".,?!") for e in d.get("errors", [])}
            for wd in r["words"]:
                words_rows.append(dict(idx=i, word=wd["text"].lower(), human_acc=wd["accuracy"], flagged=wd["text"].lower() in flagged))
    print(f"{i+1}/{len(sample)} {text[:40]!r} orig={rows[-len(CONDS)]['score']:.1f} human={r['total']} ({time.time()-t_all:.0f}s)", flush=True)

R = pd.DataFrame(rows); W = pd.DataFrame(words_rows)
R.to_csv(HERE / "runs.csv", index=False); W.to_csv(HERE / "words.csv", index=False)
piv = R.pivot(index="idx", columns="cond", values="score") / 100
std_all = piv.std(axis=1)                      # 含全部 8 条件
std_no_tel = piv.drop(columns=["telephone_8k"]).std(axis=1)
det = (piv["orig"] - piv["orig_repeat"]).abs()
orig = R[R.cond == "orig"].set_index("idx")
rho_total = spearmanr(orig.score, orig.human_total).correlation
rho_per = spearmanr(-orig.per.astype(float), orig.human_accuracy).correlation
W["human_bad"] = W.human_acc <= 5
tp = (W.flagged & W.human_bad).sum(); fp = (W.flagged & ~W.human_bad).sum(); fn = (~W.flagged & W.human_bad).sum()
rep = {
    "n_utterances": int(len(piv)), "conditions": list(CONDS),
    "determinism_max_abs_diff": round(float(det.max()), 4),
    "score_std_mean_all_conds": round(float(std_all.mean()), 4), "score_std_p90_all_conds": round(float(std_all.quantile(.9)), 4),
    "frac_utts_std_lt_0.1_all_conds": round(float((std_all < 0.1).mean()), 3),
    "score_std_mean_excl_telephone": round(float(std_no_tel.mean()), 4),
    "frac_utts_std_lt_0.1_excl_telephone": round(float((std_no_tel < 0.1).mean()), 3),
    "mean_score_shift_by_cond": {c: round(float((piv[c] - piv["orig"]).mean()), 4) for c in CONDS},
    "spearman_score_vs_human_total": round(float(rho_total), 3),
    "spearman_negPER_vs_human_accuracy": round(float(rho_per), 3),
    "word_flag_precision": round(float(tp / max(tp + fp, 1)), 3), "word_flag_recall": round(float(tp / max(tp + fn, 1)), 3),
    "n_words": int(len(W)), "n_human_bad_words": int(W.human_bad.sum()),
    "median_sec_per_utt": round(float(R.sec.median()), 2),
}
json.dump(rep, open(HERE / "results.json", "w"), indent=1, ensure_ascii=False)
print(json.dumps(rep, indent=1, ensure_ascii=False))
