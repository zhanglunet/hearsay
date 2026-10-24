"""可选的本机转写。

默认关闭。只有环境变量 HEARSAY_ASR 恰好等于 faster-whisper 时才导入模型。
CI 和普通启动都不会下载权重。不要把密钥放进参数；本模块也不打印环境变量。
"""

from __future__ import annotations

import os
from pathlib import Path

ASR_ENV = "HEARSAY_ASR"
ASR_VALUE = "faster-whisper"

_model = None
_model_name = None


class AsrDisabled(RuntimeError):
    """调用方应把这句话直接给用户，不要附带环境变量的其他内容。"""


def asr_enabled() -> bool:
    return os.environ.get(ASR_ENV) == ASR_VALUE


def transcribe_file(path: Path) -> str:
    if not asr_enabled():
        raise AsrDisabled(
            "未启用本机 ASR。只有把环境变量 HEARSAY_ASR 设为 faster-whisper"
            "并且安装了 faster-whisper 才会加载模型。默认不下载。"
        )
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise AsrDisabled(
            "HEARSAY_ASR 已设为 faster-whisper，但当前环境没有 faster-whisper 包。"
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
