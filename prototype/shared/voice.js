"use strict";
/*
 * 听力、跟读、复述、对话共用的语音模块：window.HearsayVoice。
 *
 * 线上（Cloudflare）走 Worker 的 Workers AI 接口：
 *   GET  /voice/status   探测是否可用
 *   POST /voice/tts      {text} → audio/mpeg（Deepgram aura-2-en）
 *   POST /voice/asr      录音原始字节 → {text, segments}（Whisper large-v3 turbo，原样转写）
 * 本地开发没有 Worker，/voice/status 探测失败时退回浏览器 speechSynthesis /
 * SpeechRecognition。见 worker/voice.ts。
 *
 * iPhone（iOS Safari）只允许在用户手势里开始播放。云端朗读要先联网取音频再播放，
 * 中间隔了一次网络请求，会被拦下（play() 抛 NotAllowedError，而且没有声音也不报错）。
 * 做法：所有朗读共用一个 <audio> 元素，用户第一次触摸/点击页面时用它播一段极短的静音
 * 把它“解锁”，之后再用它播放就不受限制。仍被拦时 speak() 返回 false，调用方可提示用户点一下。
 */
(function () {
  // 10 ms 静音 WAV，用于在用户手势里解锁共用播放器
  const SILENT_WAV = "data:audio/wav;base64,UklGRsQAAABXQVZFZm10IBAAAAABAAEAQB8AAIA+AAACABAAZGF0YaAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA";

  let statusPromise = null;
  let finishCurrent = null; // 结束当前 speak() 的 Promise；被 stop() 打断时也要结束，否则调用方会一直等
  let unlocked = false;
  const player = new Audio(); // 共用播放器：解锁一次，之后都用它播放
  player.preload = "auto";

  // 用根路径：线上 /voice/* 由 Worker 接住；本地网关和单独运行的切片都没有它，探测会失败
  function cloudStatus() {
    if (!statusPromise) {
      statusPromise = fetch("/voice/status", { cache: "no-store" })
        .then((r) => (r.ok ? r.json() : null))
        .then((s) => ({ tts: Boolean(s && s.tts), asr: Boolean(s && s.asr) }))
        .catch(() => ({ tts: false, asr: false }));
    }
    return statusPromise;
  }

  // 在用户手势里调用：解锁共用播放器与浏览器朗读（iOS 都要求首次在手势里启动）
  function unlock() {
    if (unlocked) return;
    unlocked = true;
    try {
      player.src = SILENT_WAV;
      const p = player.play();
      if (p && p.then) p.then(() => player.pause()).catch(() => { unlocked = false; });
    } catch (_err) {
      unlocked = false;
    }
    if ("speechSynthesis" in window) {
      try {
        const u = new SpeechSynthesisUtterance("");
        u.volume = 0;
        window.speechSynthesis.speak(u);
      } catch (_err) { /* 忽略 */ }
    }
  }

  if (typeof document !== "undefined" && document.addEventListener) {
    // 捕获阶段：在页面自己的点击处理之前完成解锁
    for (const type of ["pointerdown", "touchend", "click", "keydown"]) {
      document.addEventListener(type, unlock, { capture: true, passive: true });
    }
  }

  // 浏览器兜底朗读：尽量挑更自然的英文声音，而不是系统默认
  function pickBrowserVoice() {
    if (!("speechSynthesis" in window)) return null;
    const voices = window.speechSynthesis.getVoices().filter((v) => /^en(-|_)/i.test(v.lang));
    const prefer = [/Google US English/i, /Natural/i, /Neural/i, /Samantha/i, /Ava/i, /Allison/i];
    for (const re of prefer) {
      const v = voices.find((voice) => re.test(voice.name));
      if (v) return v;
    }
    return voices.find((v) => /en-US/i.test(v.lang)) || voices[0] || null;
  }

  function browserSpeak(text) {
    if (!("speechSynthesis" in window)) return Promise.resolve(false);
    return new Promise((resolve) => {
      const done = () => {
        if (finishCurrent === done) finishCurrent = null;
        resolve(true);
      };
      finishCurrent = done;
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = "en-US";
      const voice = pickBrowserVoice();
      if (voice) utterance.voice = voice;
      utterance.onend = done;
      utterance.onerror = done;
      window.speechSynthesis.cancel();
      window.speechSynthesis.speak(utterance);
    });
  }

  function stop() {
    player.pause();
    if (finishCurrent) {
      const finish = finishCurrent;
      finishCurrent = null;
      finish();
    }
    if ("speechSynthesis" in window) window.speechSynthesis.cancel();
  }

  // 朗读一段英文。返回 true 表示播出了声音；false 表示被浏览器拦下（iOS 未经手势）或无法播放。
  // 云端合成失败时退回浏览器朗读，不让播放按钮“没反应”。
  async function speak(text) {
    stop();
    const status = await cloudStatus();
    if (status.tts) {
      let url = null;
      try {
        const r = await fetch("/voice/tts", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text }),
        });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        url = URL.createObjectURL(await r.blob());
      } catch (_err) {
        return browserSpeak(text);
      }
      let mine = null;
      let blocked = false;
      await new Promise((resolve) => {
        mine = resolve;
        finishCurrent = resolve;
        player.onended = resolve;
        player.onerror = resolve;
        player.src = url;
        const p = player.play();
        if (p && p.catch) {
          p.catch((err) => {
            blocked = Boolean(err && err.name === "NotAllowedError");
            resolve();
          });
        }
      });
      // 只清自己的：被打断后若已开始下一句，finishCurrent 指向的是下一句
      if (finishCurrent === mine) finishCurrent = null;
      URL.revokeObjectURL(url);
      return !blocked;
    }
    return browserSpeak(text);
  }

  // 录音：start() 开始，stop() 结束并返回 Blob（Chrome 为 webm/opus，iPhone 为 mp4/aac）
  function createRecorder() {
    let recorder = null;
    let stream = null;
    let chunks = [];
    return {
      supported: Boolean(navigator.mediaDevices && navigator.mediaDevices.getUserMedia && window.MediaRecorder),
      async start() {
        stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        chunks = [];
        recorder = new MediaRecorder(stream);
        recorder.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
        recorder.start();
      },
      stop() {
        return new Promise((resolve) => {
          if (!recorder || recorder.state === "inactive") { resolve(null); return; }
          recorder.onstop = () => {
            const blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
            if (stream) stream.getTracks().forEach((t) => t.stop());
            resolve(blob);
          };
          recorder.stop();
        });
      },
    };
  }

  // 云端识别一段录音；失败抛错，调用方提示用户重录或打字
  async function transcribe(blob) {
    const r = await fetch("/voice/asr", {
      method: "POST",
      headers: { "Content-Type": blob.type || "audio/webm" },
      body: blob,
    });
    const payload = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(payload.error || `语音识别失败（HTTP ${r.status}）`);
    return payload;
  }

  // 预热声音列表（部分浏览器异步加载）
  if ("speechSynthesis" in window) window.speechSynthesis.getVoices();

  window.HearsayVoice = { cloudStatus, speak, stop, unlock, createRecorder, transcribe };
})();
