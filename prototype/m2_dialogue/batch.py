"""M2 事后批处理：权威转写 + 实时 recast 核对。

默认关闭。只有 HEARSAY_M2_BATCH=whisperx 时才启用，首次转写才加载 / 下载模型。
转写配置沿用实验 A 结论：whisperX large-v3 + verbatim prompt（错误保留率 98.3%）。
音频是浏览器 MediaRecorder 的 webm/ogg，whisperX 解码需要本机有 ffmpeg。

核对口径（M0 §4.1）：实时 recast 全是 provisional；批处理在同一话语、同一代码上
找到的合并为 confirmed，找不到的 provisional 标 discarded，批处理新发现的直接
confirmed。本切片的批处理检测仍是规则扫描（不是 LLM 检测），所以这里的误报率
衡量的是规则 recast，不是 M0 §6 的 LLM 实时链路误报率；指标结构先跑通。
"""

import os
import time

from m2_dialogue.recast import scan_recasts

BATCH_ENV = "HEARSAY_M2_BATCH"
MODEL_ENV = "HEARSAY_M2_ASR_MODEL"

VERBATIM_PROMPT = ("Transcribe exactly what the speaker says, word for word, keeping all grammar mistakes "
                   "such as 'he go', 'two book', 'I very like', 'in Monday'. Do not correct anything.")

_model = None


def batch_enabled():
    return os.environ.get(BATCH_ENV) == "whisperx"


def whisperx_transcriber():
    """惰性加载 whisperX。返回 transcribe(path) -> text。"""
    global _model
    if _model is None:
        import torch
        _orig_torch_load = torch.load

        def _torch_load_compat(*a, **k):
            if k.get("weights_only") is None:
                k["weights_only"] = False
            return _orig_torch_load(*a, **k)

        torch.load = _torch_load_compat
        import whisperx
        name = os.environ.get(MODEL_ENV, "large-v3")
        _model = whisperx.load_model(name, device="cpu", compute_type="int8", language="en",
                                     asr_options={"initial_prompt": VERBATIM_PROMPT})

    import whisperx

    def transcribe(path):
        audio = whisperx.load_audio(str(path))
        res = _model.transcribe(audio, batch_size=8, language="en")
        return " ".join(seg["text"] for seg in res["segments"]).strip()

    return transcribe


def reconcile(provisional, detected):
    """provisional：实时 recast；detected：批处理发现。两者都带 utterance_id 与 code。
    返回 {confirmed, discarded, false_positive_rate}。"""
    remaining = list(detected)
    confirmed, discarded = [], []
    for p in provisional:
        hit = next((d for d in remaining
                    if d["utterance_id"] == p["utterance_id"] and d["code"] == p["code"]), None)
        if hit is None:
            discarded.append(dict(p, status="discarded"))
        else:
            remaining.remove(hit)
            confirmed.append(dict(hit, status="confirmed", merged_provisional=True))
    for d in remaining:
        confirmed.append(dict(d, status="confirmed", merged_provisional=False))
    rate = round(len(discarded) / len(provisional), 3) if provisional else None
    return dict(confirmed=confirmed, discarded=discarded, false_positive_rate=rate)


def run_batch(session, transcribe=None):
    """对会话的学习者话语做事后转写与核对。transcribe 可注入，测试不加载模型。
    没有音频的话语退回实时文本，并在 transcripts 里标 source=realtime_fallback。"""
    t0 = time.time()
    if transcribe is None:
        transcribe = whisperx_transcriber()
    transcripts, detected = [], []
    for turn in session.turns:
        if turn["speaker"] != "learner":
            continue
        uid = turn["utterance_id"]
        if turn.get("audio_ref"):
            text = transcribe(turn["audio_ref"])
            source = "whisperx_verbatim"
        else:
            text = turn["text"]
            source = "realtime_fallback"
        turn["batch_text"] = text
        transcripts.append(dict(utterance_id=uid, realtime_text=turn["text"],
                                batch_text=text, source=source))
        for hit in scan_recasts(text):
            detected.append(dict(hit, utterance_id=uid))
    result = reconcile(session.recasts, detected)
    result.update(asr="whisperx_verbatim",
                  detection="rule_on_batch_text",
                  duration_sec=round(time.time() - t0, 2),
                  transcripts=transcripts)
    return result
