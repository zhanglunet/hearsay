"use strict";
/*
 * 听力、复述、对话共用的语音模块：window.HearsayVoice。
 *
 * 线上（Cloudflare）走 Worker 的 Workers AI 接口：
 *   GET  /voice/status   探测是否可用
 *   POST /voice/tts      {text} → audio/mpeg（Deepgram aura-2-en）
 *   POST /voice/asr      录音原始字节 → {text, segments}（Whisper large-v3 turbo，原样转写）
 * 本地开发没有 Worker，/voice/status 探测失败时退回浏览器 speechSynthesis /
 * SpeechRecognition。见 worker/voice.ts。
 */
(function () {
  let statusPromise = null;
  let currentAudio = null;
  let finishCurrent = null; // 结束当前 speak() 的 Promise；被 stop() 打断时也要结束，否则调用方会一直等

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
    if (!("speechSynthesis" in window)) return Promise.resolve();
    return new Promise((resolve) => {
      const done = () => {
        if (finishCurrent === done) finishCurrent = null;
        resolve();
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
    if (currentAudio) {
      currentAudio.pause();
      currentAudio = null;
    }
    if (finishCurrent) {
      const finish = finishCurrent;
      finishCurrent = null;
      finish();
    }
    if ("speechSynthesis" in window) window.speechSynthesis.cancel();
  }

  // 朗读一段英文。云端失败时退回浏览器朗读，不让播放按钮“没反应”
  async function speak(text) {
    stop();
    const status = await cloudStatus();
    if (status.tts) {
      try {
        const r = await fetch("/voice/tts", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text }),
        });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const url = URL.createObjectURL(await r.blob());
        const audio = new Audio(url);
        currentAudio = audio;
        let mine = null;
        await new Promise((resolve) => {
          mine = resolve;
          finishCurrent = resolve;
          audio.onended = resolve;
          audio.onerror = resolve;
          audio.play().catch(resolve);
        });
        // 只清自己的：被打断后若已开始下一句，finishCurrent 指向的是下一句
        if (currentAudio === audio) currentAudio = null;
        if (finishCurrent === mine) finishCurrent = null;
        URL.revokeObjectURL(url);
        return;
      } catch (_err) {
        // 落到浏览器朗读
      }
    }
    await browserSpeak(text);
  }

  // 录音：start() 开始，stop() 结束并返回 Blob（webm/opus 等，按浏览器而定）
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

  window.HearsayVoice = { cloudStatus, speak, stop, createRecorder, transcribe };
})();
