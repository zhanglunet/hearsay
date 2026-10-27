/**
 * 语音接口：在 Worker 里直接调 Workers AI，不进容器。
 *
 *   GET  /voice/status  → {"tts": true, "asr": true}；前端用它判断能不能走云端语音
 *   POST /voice/tts     → body {"text": "...", "speaker"?: "..."}，返回 audio/mpeg
 *   POST /voice/asr     → body 是录音原始字节（Content-Type 如 audio/webm），返回
 *                         {"text": "...", "segments": [{start, end, text}], "word_count": n}
 *
 * 为什么不用浏览器自带的 speechSynthesis / SpeechRecognition：
 *   - 朗读：系统默认英文声音机械、生硬（2026-10-27 真人试用反馈）。
 *   - 识别：Chrome 把录音发到 Google 识别，从国内访问慢且常不完整；而且会把语法错误
 *     自动“改对”（he go → he goes），纠错就失去依据。Whisper 原样转写保留率高
 *     （M1 实验 A：whisperX large-v3 加 verbatim 提示 98.3%）。
 *
 * 这些路径和网站同域名，同样受 Cloudflare Access 保护。本地开发没有 Worker，
 * 前端探测 /voice/status 失败时退回浏览器接口（prototype/shared/voice.js）。
 */

export const TTS_MODEL = "@cf/deepgram/aura-2-en";
export const ASR_MODEL = "@cf/openai/whisper-large-v3-turbo";

// aura-2-en 的女声，清晰自然；其余可选值见模型文档
export const DEFAULT_SPEAKER = "luna";
const SPEAKERS = new Set([
  "amalthea", "andromeda", "apollo", "arcas", "aries", "asteria", "athena", "atlas", "aurora",
  "callista", "cora", "cordelia", "delia", "draco", "electra", "harmonia", "helena", "hera",
  "hermes", "hyperion", "iris", "janus", "juno", "jupiter", "luna", "mars", "minerva", "neptune",
  "odysseus", "ophelia", "orion", "orpheus", "pandora", "phoebe", "pluto", "saturn", "thalia",
  "theia", "vesta", "zeus",
]);

export const MAX_TTS_CHARS = 1000;        // 一句或一轮回复；按字符计费，防止误传长文
export const MAX_ASR_BYTES = 8 * 1024 * 1024; // opus 录音约 8 分钟，远超一次复述

// 与 M1 实验 A 的 verbatim 提示一致：要求原样转写、保留语法错误
const VERBATIM_PROMPT =
  "Transcribe exactly what the speaker says, word for word, keeping all grammar mistakes " +
  "such as 'he go', 'two book', 'I very like', 'in Monday'. Do not correct anything.";

interface VoiceEnv {
  AI: Ai;
}

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" },
  });
}

async function sha256Hex(text: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function toBase64(bytes: Uint8Array): string {
  let binary = "";
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
  }
  return btoa(binary);
}

async function handleTts(request: Request, env: VoiceEnv, ctx: ExecutionContext): Promise<Response> {
  let body: { text?: unknown; speaker?: unknown };
  try {
    body = await request.json();
  } catch {
    return json(400, { error: "请求体不是 JSON" });
  }
  const text = typeof body.text === "string" ? body.text.trim() : "";
  if (!text) return json(400, { error: "text 不能为空" });
  if (text.length > MAX_TTS_CHARS) return json(413, { error: `text 超过 ${MAX_TTS_CHARS} 个字符` });
  const speaker = typeof body.speaker === "string" && SPEAKERS.has(body.speaker)
    ? body.speaker : DEFAULT_SPEAKER;

  // 同一句话反复点播放很常见（逐句听），按 模型+声音+文本 缓存，省钱也更快
  const cache = caches.default;
  const cacheKey = new Request(
    `https://voice-cache.hearsay.internal/tts/${await sha256Hex(`${TTS_MODEL}|${speaker}|${text}`)}`);
  const cached = await cache.match(cacheKey);
  if (cached) return cached;

  let audio: ReadableStream;
  try {
    audio = (await env.AI.run(TTS_MODEL as any, { text, speaker } as any)) as unknown as ReadableStream;
  } catch (err) {
    console.log(`voice tts failed: ${err instanceof Error ? err.message : String(err)}`);
    return json(502, { error: "语音合成失败，请稍后重试" });
  }
  const bytes = await new Response(audio).arrayBuffer();
  const response = new Response(bytes, {
    headers: {
      "content-type": "audio/mpeg",
      "cache-control": "private, max-age=86400",
    },
  });
  ctx.waitUntil(cache.put(cacheKey, response.clone()));
  return response;
}

async function handleAsr(request: Request, env: VoiceEnv): Promise<Response> {
  const declared = Number(request.headers.get("content-length") || "0");
  if (declared > MAX_ASR_BYTES) return json(413, { error: "录音太长" });
  const bytes = new Uint8Array(await request.arrayBuffer());
  if (bytes.length === 0) return json(400, { error: "没有收到录音" });
  if (bytes.length > MAX_ASR_BYTES) return json(413, { error: "录音太长" });

  let result: any;
  try {
    result = await env.AI.run(ASR_MODEL as any, {
      audio: toBase64(bytes),
      task: "transcribe",
      language: "en",
      vad_filter: true,
      initial_prompt: VERBATIM_PROMPT,
    } as any);
  } catch (err) {
    console.log(`voice asr failed: ${err instanceof Error ? err.message : String(err)}`);
    return json(502, { error: "语音识别失败，请重录或打字" });
  }
  const segments = Array.isArray(result?.segments)
    ? result.segments.map((s: any) => ({ start: s.start, end: s.end, text: String(s.text ?? "").trim() }))
    : [];
  return json(200, {
    text: String(result?.text ?? "").trim(),
    segments,
    word_count: typeof result?.word_count === "number" ? result.word_count : null,
  });
}

/** 是语音路径就处理并返回 Response；不是就返回 null，交给容器。 */
export async function handleVoice(
  request: Request, env: VoiceEnv, ctx: ExecutionContext,
): Promise<Response | null> {
  const { pathname } = new URL(request.url);
  if (!pathname.startsWith("/voice/")) return null;
  if (pathname === "/voice/status") {
    return request.method === "GET"
      ? json(200, { tts: true, asr: true, tts_model: TTS_MODEL, asr_model: ASR_MODEL })
      : json(405, { error: "只支持 GET" });
  }
  if (request.method !== "POST") return json(405, { error: "只支持 POST" });
  if (pathname === "/voice/tts") return handleTts(request, env, ctx);
  if (pathname === "/voice/asr") return handleAsr(request, env);
  return json(404, { error: "没有这个语音接口" });
}
