"""M2 实时语音链路（pipecat）。可选入口，未在本机实测（依赖与模型未安装）。

运行（Python 3.11+，先装 requirements-realtime.txt 里的依赖）：

    HEARSAY_ANTHROPIC_API_KEY=... python -m m2_dialogue.realtime --host 127.0.0.1 --port 7860

流水线：transport → Silero VAD → faster-whisper STT（实时、带归一化）
→ Claude（导师 system prompt，与 mock 切片同场景）→ Piper TTS（本地）→ transport。
实时转写只驱动对话；权威转写仍属事后 whisperX 批处理（batch.py）。

TranscriptRecorder 把实时用户转写与 Agent 文本按轮记录下来，并对用户文本做
recast 规则扫描（provisional 占位；LLM 实时 recast 的结构化抽取还没做）。
客户端断开时写到 prototype/runtime/m2-realtime-<时间戳>.json（已 gitignore），
供 experiments/exp_e_dialogue/aggregate.py 统计误报率。密钥只走环境变量。
"""

import json
import os
import re
import time
from pathlib import Path

from m2_dialogue.recast import scan_recasts
from m2_dialogue.tutor import KEY_ENV, SYSTEM_PROMPT

try:
    from loguru import logger
    from pipecat.audio.vad.silero import SileroVADAnalyzer
    from pipecat.frames.frames import Frame, LLMFullResponseEndFrame, LLMRunFrame, LLMTextFrame, TextFrame, TranscriptionFrame
    from pipecat.pipeline.pipeline import Pipeline
    from pipecat.pipeline.worker import PipelineParams, PipelineWorker, ProcessorUnusablePolicy
    from pipecat.processors.aggregators.llm_context import LLMContext
    from pipecat.processors.aggregators.llm_response_universal import (
        LLMContextAggregatorPair,
        LLMUserAggregatorParams,
    )
    from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
    from pipecat.runner.types import RunnerArguments
    from pipecat.runner.utils import create_transport
    from pipecat.services.anthropic.llm import AnthropicLLMService
    from pipecat.services.piper.tts import PiperTTSService
    from pipecat.services.whisper.stt import WhisperSTTService
    from pipecat.transports.base_transport import BaseTransport, TransportParams
    from pipecat.workers.runner import WorkerRunner
except ImportError as exc:
    raise SystemExit(
        "实时链路需要额外依赖：python -m pip install -r "
        "prototype/m2_dialogue/requirements-realtime.txt（含 pipecat-ai、faster-whisper、"
        "piper 等；模型首次运行下载）。离线 mock 切片 python -m m2_dialogue 不需要它们。"
    ) from exc

RUNTIME_DIR = Path(__file__).resolve().parents[1] / "runtime"


def extract_reply(text):
    """导师约定输出 {"reply","recasts"}，只取 reply 给 TTS 和记录；非 JSON 原样返回。"""
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        try:
            reply = json.loads(m.group(0)).get("reply")
            if isinstance(reply, str) and reply.strip():
                return reply.strip()
        except (json.JSONDecodeError, AttributeError):
            pass
    return text


class JsonReplyProcessor(FrameProcessor):
    """LLM → TTS 之间：攒完整一轮，提取 reply 再合成，避免把 recasts JSON 读出来。"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.buffer = ""

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        if isinstance(frame, LLMTextFrame):
            self.buffer += frame.text
            return
        reply = extract_reply(self.buffer)
        self.buffer = ""
        if reply:
            await self.push_frame(TextFrame(reply), direction)
        await self.push_frame(frame, direction)


class TranscriptRecorder(FrameProcessor):
    """记录实时用户转写与 Agent 文本，断开时落盘（本地私有目录）。
    放在 STT 之后，因为 user_aggregator 会消费 TranscriptionFrame；
    Agent 文本从 LLMContext 取。"""

    def __init__(self, context=None, **kwargs):
        super().__init__(**kwargs)
        self.context = context
        self.utterances = []
        self.recasts = []

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, TranscriptionFrame):
            text = frame.text.strip()
            if text:
                self.utterances.append(dict(speaker="learner", text=text, at=time.time()))
                for hit in scan_recasts(text):
                    self.recasts.append(dict(hit, utterance_id=len(self.utterances)))
        elif isinstance(frame, LLMTextFrame):
            self.utterances.append(dict(speaker="agent", text=frame.text, at=time.time()))
        await self.push_frame(frame, direction)

    def dump(self):
        if self.context is not None:
            get_messages = getattr(self.context, "get_messages", None)
            messages = get_messages() if get_messages else getattr(self.context, "messages", [])
            for message in messages:
                if isinstance(message, dict):
                    role, content = message.get("role"), message.get("content", "")
                else:
                    role, content = getattr(message, "role", None), getattr(message, "content", "")
                if role == "assistant":
                    self.utterances.append(dict(speaker="agent", text=extract_reply(content)))
        RUNTIME_DIR.mkdir(exist_ok=True)
        path = RUNTIME_DIR / f"m2-realtime-{time.strftime('%Y%m%d-%H%M%S')}.json"
        path.write_text(json.dumps(dict(utterances=self.utterances, recasts=self.recasts),
                                   ensure_ascii=False, indent=1))
        logger.info(f"实时会话记录已写入 {path}（本地私有，勿提交）")


transport_params = {
    "webrtc": lambda: TransportParams(audio_in_enabled=True, audio_out_enabled=True),
}


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments):
    stt = WhisperSTTService(
        model=os.environ.get("HEARSAY_M2_STT_MODEL", "base"),
        device="cpu",
        compute_type="int8",
    )
    llm_settings = {"system_instruction": SYSTEM_PROMPT,
                    "thinking": AnthropicLLMService.ThinkingConfig(type="disabled")}
    if os.environ.get("HEARSAY_LLM_MODEL"):
        llm_settings["model"] = os.environ["HEARSAY_LLM_MODEL"]
    llm = AnthropicLLMService(
        api_key=os.environ.get(KEY_ENV, ""),
        settings=AnthropicLLMService.Settings(**llm_settings),
    )
    _orig_push_llm_text = llm._push_llm_text
    _orig_push_frame = llm.push_frame

    async def _push_llm_text_logged(text):
        logger.debug(f"LLM 产出文本块：{text[:60]!r}")
        await _orig_push_llm_text(text)

    llm._push_llm_text = _push_llm_text_logged

    async def _push_frame_logged(frame, direction=FrameDirection.DOWNSTREAM):
        logger.debug(f"LLM push_frame: {type(frame).__name__}")
        await _orig_push_frame(frame, direction)

    llm.push_frame = _push_frame_logged
    tts = PiperTTSService(settings=PiperTTSService.Settings(voice="en_US-ryan-high"))

    context = LLMContext()
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context, user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer()))
    recorder = TranscriptRecorder(context)

    pipeline = Pipeline([
        transport.input(),
        stt,
        recorder,
        user_aggregator,
        llm,
        tts,
        transport.output(),
        assistant_aggregator,
    ])
    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(enable_metrics=True, enable_usage_metrics=True),
        idle_timeout_secs=runner_args.pipeline_idle_timeout_secs,
        processor_unusable_policy=ProcessorUnusablePolicy.END,
    )
    runner = WorkerRunner(handle_sigint=runner_args.handle_sigint)
    await runner.add_workers(worker)

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info("Client connected")
        context.add_message({"role": "developer",
                             "content": "You are Alex. Greet the learner and ask how the report is going."})
        await worker.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Client disconnected")
        recorder.dump()
        await runner.cancel()

    await runner.run()


async def bot(runner_args: RunnerArguments):
    transport = await create_transport(runner_args, transport_params)
    await run_bot(transport, runner_args)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
