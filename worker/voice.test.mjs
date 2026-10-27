// worker/voice.ts 的接口逻辑测试：假的 Workers AI 绑定与 Cache API，不发真实请求。
// 运行：npm run test:worker（先用 esbuild 把 voice.ts 编译成 ESM，再用 Node 跑）
import assert from "node:assert/strict";
import { pathToFileURL } from "node:url";
const { handleVoice, TTS_MODEL, ASR_MODEL, MAX_TTS_CHARS } = await import(pathToFileURL(process.argv[2]).href);

// 假的 Cache API（Node 没有 caches.default）。按真实规则：Cache-Control 含 private / no-store 的不存
const store = new Map();
globalThis.caches = { default: {
  async match(req) { const r = store.get(req.url); return r ? r.clone() : undefined; },
  async put(req, res) {
    if (/private|no-store/i.test(res.headers.get("cache-control") || "")) return;
    store.set(req.url, res);
  },
} };
const waits = [];
const ctx = { waitUntil: (p) => waits.push(p) };

const calls = [];
const env = { AI: { async run(model, input) {
  calls.push({ model, input });
  if (model === TTS_MODEL) return new Response(new Uint8Array([0x49, 0x44, 0x33, 1, 2])).body;
  if (model === ASR_MODEL) return { text: " Yesterday I go to the meeting. ", word_count: 6,
    segments: [{ start: 0, end: 2.1, text: " Yesterday I go to the meeting.", avg_logprob: -0.2 }] };
  throw new Error("unknown model");
} } };

const req = (path, init) => new Request(`https://hearsay.fans${path}`, init);
const json = (body) => ({ method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });

// 非语音路径交给容器
assert.equal(await handleVoice(req("/plan/"), env, ctx), null);
assert.equal(await handleVoice(req("/api/progress"), env, ctx), null);

// status
let r = await handleVoice(req("/voice/status"), env, ctx);
assert.equal(r.status, 200);
assert.deepEqual((await r.json()).asr, true);

// tts：参数、默认声音、MP3、缓存
r = await handleVoice(req("/voice/tts", json({ text: "  Hello there.  ", speaker: "not-a-voice" })), env, ctx);
assert.equal(r.status, 200);
assert.equal(r.headers.get("content-type"), "audio/mpeg");
assert.equal(r.headers.get("x-hearsay-tts-cache"), "MISS");
assert.match(r.headers.get("cache-control"), /^private/, "返回给浏览器的是 private");
assert.equal((await r.arrayBuffer()).byteLength, 5);
assert.deepEqual(calls.at(-1), { model: TTS_MODEL, input: { text: "Hello there.", speaker: "luna" } });
await Promise.all(waits);
assert.match(store.values().next().value.headers.get("cache-control"), /^public/, "存进边缘缓存的是 public");
r = await handleVoice(req("/voice/tts", json({ text: "Hello there." })), env, ctx);
assert.equal(r.status, 200);
assert.equal(r.headers.get("x-hearsay-tts-cache"), "HIT");
assert.match(r.headers.get("cache-control"), /^private/, "命中缓存时返回给浏览器的仍是 private");
assert.equal((await r.arrayBuffer()).byteLength, 5, "命中缓存时音频完整");
assert.equal(calls.filter((c) => c.model === TTS_MODEL).length, 1, "第二次应命中缓存，不再调模型");
r = await handleVoice(req("/voice/tts", json({ text: "Hi", speaker: "orion" })), env, ctx);
assert.equal(calls.at(-1).input.speaker, "orion");

// tts 边界
assert.equal((await handleVoice(req("/voice/tts", json({ text: "" })), env, ctx)).status, 400);
assert.equal((await handleVoice(req("/voice/tts", json({ text: "x".repeat(MAX_TTS_CHARS + 1) })), env, ctx)).status, 413);
assert.equal((await handleVoice(req("/voice/tts", { method: "POST", body: "not json" }), env, ctx)).status, 400);
assert.equal((await handleVoice(req("/voice/tts"), env, ctx)).status, 405);

// asr：base64、原样转写参数、响应整理
const audio = new Uint8Array(70000).map((_, i) => i % 251);
r = await handleVoice(req("/voice/asr", { method: "POST", headers: { "content-type": "audio/webm" }, body: audio }), env, ctx);
assert.equal(r.status, 200);
const body = await r.json();
assert.equal(body.text, "Yesterday I go to the meeting.");
assert.deepEqual(body.segments, [{ start: 0, end: 2.1, text: "Yesterday I go to the meeting." }]);
const asrCall = calls.at(-1);
assert.equal(asrCall.model, ASR_MODEL);
assert.equal(Buffer.from(asrCall.input.audio, "base64").equals(Buffer.from(audio)), true, "base64 往返一致（含 >32KB 分块）");
assert.equal(asrCall.input.language, "en");
assert.equal(asrCall.input.vad_filter, true);
assert.match(asrCall.input.initial_prompt, /keeping all grammar mistakes/);

// asr 边界与模型失败
assert.equal((await handleVoice(req("/voice/asr", { method: "POST" }), env, ctx)).status, 400);
const failing = { AI: { async run() { throw new Error("boom"); } } };
r = await handleVoice(req("/voice/asr", { method: "POST", body: new Uint8Array([1, 2, 3]) }), failing, ctx);
assert.equal(r.status, 502);
assert.doesNotMatch(await r.text(), /boom/, "不把内部错误透给前端");
assert.equal((await handleVoice(req("/voice/nope", { method: "POST" }), env, ctx)).status, 404);
console.log("voice.ts：全部断言通过");
