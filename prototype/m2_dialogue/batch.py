"""M2 事后批处理：权威转写 + 实时 recast 核对。

默认关闭。只有 HEARSAY_M2_BATCH=whisperx 时才启用，首次转写才加载 / 下载模型。
转写配置沿用实验 A 结论：whisperX large-v3 + verbatim prompt（错误保留率 98.3%）。
音频是浏览器 MediaRecorder 的 webm/ogg，whisperX 解码需要本机有 ffmpeg。

核对口径（M0 §4.1）：实时 recast 全是 provisional；批处理在同一话语、同一代码上
找到的合并为 confirmed，找不到的 provisional 标 discarded，批处理新发现的直接
confirmed。本切片的批处理检测仍是规则扫描（不是 LLM 检测），所以这里的误报率
衡量的是规则 recast，不是 M0 §6 的 LLM 实时链路误报率；指标结构先跑通。
"""

import json
import os
import re
import time

from m2_dialogue.recast import observed_overlap, scan_recasts, validate_llm_errors
from m2_dialogue.tutor import (DEFAULT_MODEL, TutorError, anthropic_request,
                               llm_api_key, llm_endpoint, response_text)

BATCH_ENV = "HEARSAY_M2_BATCH"
MODEL_ENV = "HEARSAY_M2_ASR_MODEL"
DETECT_ENV = "HEARSAY_M2_DETECT"

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
        # av>=19 移除了 faster-whisper 还在传的 metadata_errors 参数，垫片兼容
        import av
        _orig_av_open = av.open

        def _av_open_compat(*a, **k):
            k.pop("metadata_errors", None)
            return _orig_av_open(*a, **k)

        av.open = _av_open_compat
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
    合并规则（M0 §4.1，v3）：同一话语且满足任一——同一代码；实时为 X00；
    observed 归一化后互相包含。合并以批处理代码与文本为准，其余 provisional 标 discarded。
    匹配前按「话语 + observed」去重，LLM 来源优先，避免一条批处理实例对账两次。
    返回 {confirmed, discarded, false_positive_rate}。"""
    deduped = []
    seen = set()
    for p in sorted(provisional,
                    key=lambda p: 0 if p.get("detected_by") == "asr_llm_realtime" else 1):
        key = (p["utterance_id"], " ".join(str(p.get("observed", "")).lower().split()))
        if key not in seen:
            seen.add(key)
            deduped.append(p)
    remaining = list(detected)
    confirmed, discarded = [], []
    for p in deduped:
        hit = next((d for d in remaining
                    if d["utterance_id"] == p["utterance_id"]
                    and (d["code"] == p["code"] or p["code"] == "X00"
                         or observed_overlap(p.get("observed", ""), d.get("observed", "")))), None)
        if hit is None:
            discarded.append(dict(p, status="discarded"))
        else:
            remaining.remove(hit)
            confirmed.append(dict(hit, status="confirmed", merged_provisional=True))
    for d in remaining:
        confirmed.append(dict(d, status="confirmed", merged_provisional=False))
    rate = round(len(discarded) / len(provisional), 3) if provisional else None
    return dict(confirmed=confirmed, discarded=discarded, false_positive_rate=rate)


def run_batch(session, transcribe=None, detect=None):
    """对会话的学习者话语做事后转写与核对。transcribe 可注入，测试不加载模型。
    没有音频的话语退回实时文本，并在 transcripts 里标 source=realtime_fallback。"""
    t0 = time.time()
    # 模型只在真正遇到带音频的话语时才加载；纯文本回退的会话不需要 whisperX
    factory = (lambda: transcribe) if transcribe is not None else whisperx_transcriber
    transcriber = None
    transcripts, detected = [], []
    for turn in session.turns:
        if turn["speaker"] != "learner":
            continue
        uid = turn["utterance_id"]
        if turn.get("audio_ref"):
            if transcriber is None:
                transcriber = factory()
            text = transcriber(turn["audio_ref"])
            source = "whisperx_verbatim"
        else:
            text = turn["text"]
            source = "realtime_fallback"
        turn["batch_text"] = text
        transcripts.append(dict(utterance_id=uid, realtime_text=turn["text"],
                                batch_text=text, source=source))
    if detect is None:
        detected, detection = detect_errors(transcripts)
    else:
        detected, detection = detect(transcripts), "injected"
    result = reconcile(session.recasts, detected)
    result.update(asr="whisperx_verbatim",
                  detection=detection,
                  duration_sec=round(time.time() - t0, 2),
                  transcripts=transcripts)
    return result


DETECT_SYSTEM_PROMPT = """你是英语错误检测器，分析中文母语学习者的逐字（verbatim）英语口语转写。
规则：
- 只标 G（语法）、L（用词）、I（互动/表达）类错误，代码用中文母语者错误清单编号，
  如 G01 冠词、G02 单复数、G03 主谓一致、G04 时态、G05 完成时误用、G06 缺动词、
  G07 名词数、G08 介词、G09 句式、G10 代词、G11 关联词、G12 there be、G13 比较级、
  G16 虚拟语气、L10 词性误用。不要标发音（P 类），不要评发音好坏。
- 转写里的语法错误是学习者真实说的，先原样接受，不要在心里改正后再分析。
- observed 必须是该话语原文里的连续片段（大小写可不同），expected 是更自然的说法。
- 只输出 JSON：{"errors":[{"utterance_id":1,"code":"G04","observed":"...","expected":"...","confidence":0.9}]}
- 没把握就不输出；没有错误就输出 {"errors":[]}。不要输出任何解释。"""


def rule_detect(transcripts):
    detected = []
    for t in transcripts:
        for hit in scan_recasts(t["batch_text"]):
            detected.append(dict(hit, utterance_id=t["utterance_id"]))
    return detected


def llm_detect(transcripts):
    """调 Anthropic 兼容的 LLM（Claude / Kimi）做批处理错误检测。转写文本会发给
    对应服务方，仅在启用批处理且有 API key 时发生。返回校验后的错误列表。"""
    api_key = llm_api_key()
    if not api_key:
        raise TutorError("LLM 检测需要 HEARSAY_LLM_API_KEY（或 HEARSAY_ANTHROPIC_API_KEY），"
                         "或设 HEARSAY_M2_DETECT=rule 用规则。")
    utterances = [dict(utterance_id=t["utterance_id"], text=t["batch_text"]) for t in transcripts]
    payload = dict(model=os.environ.get("HEARSAY_LLM_MODEL") or DEFAULT_MODEL,
                   max_tokens=4096, system=DETECT_SYSTEM_PROMPT,
                   messages=[dict(role="user", content=json.dumps(utterances, ensure_ascii=False))])
    data = anthropic_request(payload, api_key, llm_endpoint())
    text = response_text(data)
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise TutorError("LLM 检测没有返回 JSON。")
    try:
        parsed = json.loads(m.group(0))
        raw_errors = parsed["errors"]
        if not isinstance(raw_errors, list):
            raise ValueError("errors 不是数组")
    except (json.JSONDecodeError, KeyError, ValueError) as exc:
        raise TutorError("LLM 检测返回的 JSON 结构不合法。") from exc
    return validate_llm_errors(raw_errors, transcripts)


def detect_errors(transcripts):
    """选择检测器并返回 (detected, 名称)。HEARSAY_M2_DETECT=llm/rule 可强制；
    缺省有 key 用 LLM，没 key 用规则。LLM 失败回退规则并在名称里注明。"""
    mode = os.environ.get(DETECT_ENV, "auto")
    use_llm = mode == "llm" or (mode == "auto" and bool(llm_api_key()))
    if use_llm:
        for _attempt in range(2):  # 上游偶发 5xx 时先试一次再回退，减少假性 discarded
            try:
                return llm_detect(transcripts), "asr_llm"
            except (TutorError, ValueError):
                pass
        return rule_detect(transcripts), "rule_fallback_after_llm_error"
    return rule_detect(transcripts), "rule_on_batch_text"
