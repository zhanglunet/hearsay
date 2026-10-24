"""实验 A：转写对语法错误的保留率。
对每条植入错误，若转写中出现错误形式则记"保留"，出现纠正形式记"被纠正"，否则记"其他"。
比较：whisperX 默认 / whisperX + 逐字提示 / wav2vec2 CTC（无语言模型）。
"""
import json, re, time, csv, os, argparse
from pathlib import Path
import numpy as np, soundfile as sf, torch

# 兼容垫片：torch>=2.6 默认 weights_only=True，whisperX 自带的 pyannote VAD 权重（含 omegaconf 对象）加载会失败；
# 该权重由 whisperX 官方托管，这里把未显式指定的 weights_only 改回 False。
import torch as _torch
_orig_torch_load = _torch.load
def _torch_load_compat(*a, **k):
    if k.get("weights_only") is None: k["weights_only"] = False
    return _orig_torch_load(*a, **k)
_torch.load = _torch_load_compat

HERE = Path(__file__).parent
S = json.load(open(HERE / "sentences.json"))

def parse_args():
    p = argparse.ArgumentParser(description="实验 A：转写对语法错误的保留率（合成音或真人复测）")
    p.add_argument("configs", nargs="*", help="只跑指定配置名；缺省跑全部。带配置筛选时结果追加到输出 CSV")
    p.add_argument("--audio-root", type=Path,
                   help="真人录音根目录（issue #4），下面应有 Sxx/A_NN.wav；缺省用合成音 audio/*.wav。真人音频勿入库")
    p.add_argument("--out", help="输出 CSV 文件名（相对本目录），缺省 results.csv；真人复测建议 results_human.csv")
    return p.parse_args()

def list_audio(root):
    """返回 (path, sid, voice)。真人目录里 voice 为匿名说话人编号（Sxx），不是合成音名。"""
    if root is None:
        return [(p, int(p.stem.split("_")[0]), p.stem.split("_")[1])
                for p in sorted((HERE / "audio").glob("*.wav"))]
    items = [(p, int(p.stem.split("_")[1]), p.parent.name)
             for p in sorted(root.glob("S*/A_*.wav"))]
    if not items:
        raise SystemExit(f"{root} 下没有找到 Sxx/A_NN.wav，目录约定见 docs/ops/m1-recording-protocol.md 第 6 节")
    return items

def norm(t: str) -> str:
    t = t.lower().replace("’", "'")
    t = re.sub(r"[^a-z' ]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return " " + t + " "

def judge(transcript, errors):
    out = []
    n = norm(transcript)
    for wrong, right in errors:
        w, r = norm(wrong).strip(), norm(right).strip()
        if f" {w} " in n: out.append("retained")
        elif f" {r} " in n: out.append("corrected")
        else: out.append("other")
    return out

# ---------- 识别器 ----------
def make_whisperx(model_name, prompt=None):
    import whisperx
    opts = {"initial_prompt": prompt} if prompt else {}
    model = whisperx.load_model(model_name, device="cpu", compute_type="int8", language="en", asr_options=opts)
    def run(path):
        audio = whisperx.load_audio(str(path))
        res = model.transcribe(audio, batch_size=8, language="en")
        return " ".join(seg["text"] for seg in res["segments"])
    return run

def make_wav2vec(name="facebook/wav2vec2-large-960h"):
    from transformers import Wav2Vec2Processor, Wav2Vec2ForCTC
    proc = Wav2Vec2Processor.from_pretrained(name); m = Wav2Vec2ForCTC.from_pretrained(name).eval()
    def run(path):
        wav, sr = sf.read(str(path)); assert sr == 16000
        inp = proc(wav.astype(np.float32), sampling_rate=16000, return_tensors="pt")
        with torch.no_grad(): logits = m(**inp).logits
        return proc.batch_decode(torch.argmax(logits, -1))[0]
    return run

VERBATIM_PROMPT = ("Transcribe exactly what the speaker says, word for word, keeping all grammar mistakes "
                   "such as 'he go', 'two book', 'I very like', 'in Monday'. Do not correct anything.")

CONFIGS = {
    "whisperx_large-v3_default": lambda: make_whisperx("large-v3"),
    "whisperx_large-v3_verbatim_prompt": lambda: make_whisperx("large-v3", VERBATIM_PROMPT),
    "whisperx_medium.en_default": lambda: make_whisperx("medium.en"),
    "wav2vec2_large_960h_ctc": lambda: make_wav2vec(),
}
args = parse_args()
if args.configs: CONFIGS = {k: v for k, v in CONFIGS.items() if k in args.configs}
AUDIO = list_audio(args.audio_root)

rows = []
for cname, factory in CONFIGS.items():
    t0 = time.time(); run = factory(); print(f"[{cname}] loaded in {time.time()-t0:.0f}s", flush=True)
    for path, sid, voice in AUDIO:
        s = next(x for x in S if x["id"] == sid)
        tr = run(path); verdicts = judge(tr, s["errors"])
        for (wrong, right), code, v in zip(s["errors"], s["codes"], verdicts):
            rows.append(dict(config=cname, voice=voice, sid=sid, code=code, wrong=wrong, right=right, verdict=v, transcript=tr.strip()))
    print(f"[{cname}] done in {time.time()-t0:.0f}s", flush=True)

out = HERE / (args.out or "results.csv")
mode = "a" if out.exists() and args.configs else "w"
with open(out, mode, newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    if mode == "w": w.writeheader()
    w.writerows(rows)
print("wrote", out)
