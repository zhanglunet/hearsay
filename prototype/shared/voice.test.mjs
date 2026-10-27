// prototype/shared/voice.js 的播放结束与中断语义测试：在 Node 里模拟浏览器的 Audio / fetch。
// 运行：npm run test:voice-js
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const audios = [];
let blockPlay = false; // 模拟 iOS 未经手势时拒绝播放
const played = [];
class FakeAudio {
  constructor(url) { this.src = url || ""; this.paused = true; audios.push(this); }
  play() {
    if (blockPlay && !this.src.startsWith("data:")) {
      const err = new Error("not allowed"); err.name = "NotAllowedError";
      return Promise.reject(err);
    }
    played.push(this.src);
    this.paused = false;
    return Promise.resolve();
  }
  pause() { this.paused = true; } // 与真实浏览器一致：pause 不触发 ended
}
const listeners = {};
const doc = { addEventListener: (type, fn) => { (listeners[type] ||= []).push(fn); } };
const win = {
  speechSynthesis: { getVoices: () => [], cancel() {}, speak() {} },
};
const ctx = {
  window: win, document: doc, Audio: FakeAudio, Promise, setTimeout, console, Blob,
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

assert.equal(audios.length, 1, "只建一个共用播放器");
const player = audios[0];

// 0. 第一次触摸页面时解锁：在手势里播一段静音，之后不再重复
listeners.pointerdown[0]();
assert.ok(played.at(-1).startsWith("data:audio/wav"), "手势里播放了静音");
const unlockPlays = played.length;
listeners.click[0]();
assert.equal(played.length, unlockPlays, "只解锁一次");

// 1. 正常播完
let p = V.speak("one"); await tick();
player.onended();
assert.equal(await settled(p), "done", "播完应结束");
assert.equal(await p, true, "播出了声音时返回 true");

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
// 4. iOS 未经手势：play 被拒绝时返回 false，而不是静默“成功”
blockPlay = true;
p = V.speak("blocked");
assert.equal(await settled(p), "done", "被拦也应结束");
assert.equal(await p, false, "被浏览器拦下时返回 false");
blockPlay = false;
console.log("voice.js 播放、中断与 iOS 解锁语义：全部断言通过");
