// prototype/shared/voice.js 的播放结束与中断语义测试：在 Node 里模拟浏览器的 Audio / fetch。
// 运行：npm run test:voice-js
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const audios = [];
class FakeAudio {
  constructor(url) { this.url = url; this.paused = true; audios.push(this); }
  play() { this.paused = false; return Promise.resolve(); }
  pause() { this.paused = true; } // 与真实浏览器一致：pause 不触发 ended
}
const win = {
  speechSynthesis: { getVoices: () => [], cancel() {}, speak() {} },
};
const ctx = {
  window: win, Audio: FakeAudio, Promise, setTimeout, console, Blob,
  URL: { createObjectURL: () => "blob:x", revokeObjectURL() {} },
  navigator: {},
  fetch: async (path) => {
    if (path === "/voice/status") return { ok: true, json: async () => ({ tts: true, asr: true }) };
    if (path === "/voice/tts") return { ok: true, blob: async () => new Blob([new Uint8Array(3)]) };
    throw new Error("unexpected " + path);
  },
};
vm.createContext(ctx);
vm.runInContext(readFileSync(process.argv[2], "utf8"), ctx);
const V = win.HearsayVoice;
const settled = (p, ms = 300) => Promise.race([p.then(() => "done"), new Promise((r) => setTimeout(() => r("pending"), ms))]);
const tick = () => new Promise((r) => setTimeout(r, 20));

// 1. 正常播完
let p = V.speak("one"); await tick();
audios.at(-1).onended();
assert.equal(await settled(p), "done", "播完应结束");

// 2. 中途 stop
p = V.speak("two"); await tick();
V.stop();
assert.equal(await settled(p), "done", "被 stop 打断也应结束");
assert.equal(audios.at(-1).paused, true);

// 3. A 被打断后立刻开始 B：B 仍能被 stop
const a = V.speak("A"); await tick();
const b = V.speak("B"); // speak 内部先 stop() 打断 A
assert.equal(await settled(a), "done", "A 被 B 打断应结束");
await tick();
assert.equal(await settled(b, 100), "pending", "B 还在播");
V.stop();
assert.equal(await settled(b), "done", "B 仍能被 stop 结束（没被 A 的收尾误清）");
console.log("voice.js 中断语义：全部断言通过");
