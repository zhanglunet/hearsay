"""实验 C：词级时间戳精度。
用 Kokoro 合成句子并取其 token 级时间戳作为真值（音频本身由这些时长生成），
把 5 句拼成一段（句间静音 300–600 ms），用 whisperX transcribe+align 得到词边界，
统计词边界误差与句边界误差。
"""
import json, re, random, time
from pathlib import Path
import numpy as np, soundfile as sf

HERE = Path(__file__).parent
random.seed(7)
SENTS = [l.strip() for l in open(HERE / "sentences.txt") if l.strip()]
assert len(SENTS) >= 50
SR = 16000

def synth_all():
    from kokoro import KPipeline
    import torch
    pipe = KPipeline(lang_code="a", repo_id="hexgrad/Kokoro-82M")
    items = []
    for i, text in enumerate(SENTS[:50]):
        for r in pipe(text, voice="af_heart", speed=1.0):
            audio = r.audio.numpy() if hasattr(r.audio, "numpy") else np.asarray(r.audio)
            # 24 kHz → 16 kHz
            import librosa
            audio16 = librosa.resample(audio.astype(np.float32), orig_sr=24000, target_sr=SR)
            words = []
            cur = None
            for tok in r.tokens:
                if tok.start_ts is None or tok.end_ts is None: continue
                txt = re.sub(r"[^A-Za-z']", "", tok.text)
                if not txt: continue
                if cur is None: cur = dict(word=txt, start=float(tok.start_ts), end=float(tok.end_ts))
                else: cur["word"] += txt; cur["end"] = float(tok.end_ts)
                if tok.whitespace:  # 词结束
                    words.append(cur); cur = None
            if cur: words.append(cur)
            items.append(dict(text=text, audio=audio16, words=words))
            break
    return items

def build_paragraphs(items, per=5):
    paras = []
    for p in range(0, len(items), per):
        chunk = items[p:p+per]; buf = []; t = 0.0; words = []; sents = []
        for it in chunk:
            gap = random.uniform(0.3, 0.6); buf.append(np.zeros(int(gap*SR), np.float32)); t += gap
            s0 = t
            for w in it["words"]: words.append(dict(word=w["word"], start=w["start"]+t, end=w["end"]+t))
            buf.append(it["audio"]); t += len(it["audio"])/SR
            sents.append(dict(text=it["text"], start=s0, end=t))
        audio = np.concatenate(buf + [np.zeros(int(0.4*SR), np.float32)])
        paras.append(dict(audio=audio, words=words, sents=sents, text=" ".join(it["text"] for it in chunk)))
    return paras

def norm(w): return re.sub(r"[^a-z']", "", w.lower())

def run():
    t0 = time.time(); items = synth_all(); print(f"synth {len(items)} sentences in {time.time()-t0:.0f}s", flush=True)
    paras = build_paragraphs(items)
    (HERE / "audio").mkdir(exist_ok=True)
    import whisperx, difflib
    model = whisperx.load_model("large-v3", device="cpu", compute_type="int8", language="en")
    align_model, meta = whisperx.load_align_model(language_code="en", device="cpu")
    word_errs = []; sent_errs = []; n_matched = 0; n_truth = 0
    for i, p in enumerate(paras):
        wav = HERE / "audio" / f"para_{i:02d}.wav"; sf.write(wav, p["audio"], SR)
        json.dump(dict(words=p["words"], sents=p["sents"], text=p["text"]), open(wav.with_suffix(".json"), "w"), indent=1)
        audio = whisperx.load_audio(str(wav))
        res = model.transcribe(audio, batch_size=8, language="en")
        aligned = whisperx.align(res["segments"], align_model, meta, audio, "cpu", return_char_alignments=False)
        hyp = [w for w in aligned["word_segments"] if "start" in w]
        truth = p["words"]; n_truth += len(truth)
        sm = difflib.SequenceMatcher(a=[norm(w["word"]) for w in truth], b=[norm(w["word"]) for w in hyp], autojunk=False)
        for tag, a0, a1, b0, b1 in sm.get_opcodes():
            if tag != "equal": continue
            for k in range(a1 - a0):
                tw, hw = truth[a0+k], hyp[b0+k]; n_matched += 1
                word_errs.append(dict(word=tw["word"], ds=abs(hw["start"]-tw["start"]), de=abs(hw["end"]-tw["end"])))
        # 句边界：真值句首词 / 句末词 对应的假设词
        for s in p["sents"]:
            first = min(truth, key=lambda w: abs(w["start"]-s["start"])); last = max(truth, key=lambda w: w["end"] if w["end"] <= s["end"]+1e-3 else -1)
            def find(tw):
                cands = [h for h in hyp if norm(h["word"]) == norm(tw["word"]) and abs(h["start"]-tw["start"]) < 1.0]
                return min(cands, key=lambda h: abs(h["start"]-tw["start"])) if cands else None
            hf, hl = find(first), find(last)
            if hf and hl: sent_errs.append(dict(ds=abs(hf["start"]-s["start"]), de=abs(hl["end"]-s["end"])))
        print(f"para {i}: truth {len(truth)} words, hyp {len(hyp)}", flush=True)
    import pandas as pd
    W = pd.DataFrame(word_errs); Sd = pd.DataFrame(sent_errs)
    b = np.concatenate([W.ds.values, W.de.values])
    rep = {
        "truth_words": n_truth, "matched_words": n_matched, "match_rate": round(n_matched/n_truth, 3),
        "word_boundary_median_ms": round(float(np.median(b))*1000, 1),
        "word_boundary_p90_ms": round(float(np.percentile(b, 90))*1000, 1),
        "word_boundary_frac_lt_150ms": round(float((b < 0.15).mean()), 3),
        "word_start_frac_lt_150ms": round(float((W.ds < 0.15).mean()), 3),
        "word_end_frac_lt_150ms": round(float((W.de < 0.15).mean()), 3),
        "sent_boundaries": int(len(Sd)),
        "sent_start_median_ms": round(float(Sd.ds.median())*1000, 1), "sent_end_median_ms": round(float(Sd.de.median())*1000, 1),
        "sent_boundary_frac_lt_150ms": round(float((np.concatenate([Sd.ds, Sd.de]) < 0.15).mean()), 3),
    }
    json.dump(rep, open(HERE / "results.json", "w"), indent=1, ensure_ascii=False); W.to_csv(HERE / "word_errors.csv", index=False)
    print(json.dumps(rep, indent=1))

if __name__ == "__main__": run()
