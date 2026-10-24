"""可选的本机转写。

默认行为：环境里装了 faster-whisper 就启用，没装就拒绝并给出安装提示。
环境变量 HEARSAY_ASR 设为 faster-whisper 可显式打开，设为其他值可强制关闭。
只有首次转写才下载模型权重，启动和 CI 都不会下载。
不要把密钥放进参数；本模块也不打印环境变量的值。
"""

from __future__ import annotations

import os
from importlib.util import find_spec
from pathlib import Path

ASR_ENV = "HEARSAY_ASR"
ASR_VALUE = "faster-whisper"

_model = None
_model_name = None


class AsrDisabled(RuntimeError):
    """调用方应把这句话直接给用户，不要附带环境变量的其他内容。"""


def faster_whisper_installed() -> bool:
    try:
        return find_spec("faster_whisper") is not None
    except (ImportError, ValueError):
        return False


def asr_enabled() -> bool:
    value = os.environ.get(ASR_ENV)
    if value is not None:
        return value == ASR_VALUE
    return faster_whisper_installed()


def asr_disabled_reason() -> str | None:
    if asr_enabled():
        return None
    if os.environ.get(ASR_ENV) is not None:
        return (
            "本机 ASR 被 HEARSAY_ASR 强制关闭。把它设为 faster-whisper 或删掉这个变量，"
            "重启本服务后再试。也可以直接把跟读内容粘贴到转写框。"
        )
    return (
        "未安装 faster-whisper，本机 ASR 不可用。安装：python -m pip install faster-whisper，"
        "重启本服务后自动启用（首次转写才下载模型）。"
        "也可以直接把跟读内容粘贴到转写框。"
    )


def transcribe_file(path: Path) -> str:
    reason = asr_disabled_reason()
    if reason is not None:
        raise AsrDisabled(reason)
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise AsrDisabled(
            "本机 ASR 已启用，但当前环境没有 faster-whisper 包。"
            "请运行 python -m pip install faster-whisper。"
        ) from exc

    model_name = os.environ.get("HEARSAY_ASR_MODEL", "tiny.en")
    model = _load_model(WhisperModel, model_name)
    segments, _info = model.transcribe(str(path), language="en")
    return " ".join(segment.text.strip() for segment in segments).strip()


def _load_model(whisper_model, model_name: str):
    global _model, _model_name
    if _model is None or _model_name != model_name:
        _model = whisper_model(model_name, device="cpu", compute_type="int8")
        _model_name = model_name
    return _model
