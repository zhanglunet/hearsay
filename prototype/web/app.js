const state = {
  audio: new Audio(),
  ownedUrl: null,
  title: "",
  timingNote: "",
  warning: "",
  productRule: "",
  sentences: [],
  current: 0,
  takes: new Map(),
  recorder: null,
  recognition: null,
  recording: false,
  hypothesisDraft: "",
  // demo：演示材料（espeak 合成）；import：学习者导入的真人音频
  source: "demo",
  // 云端语音（Workers AI）是否可用；本地开发没有 Worker 时都是 false
  cloud: { tts: false, asr: false },
};

let playToken = 0;
let extraPlayer = null;

const $ = (id) => document.getElementById(id);

function setStatus(text) {
  $("status").textContent = text || "";
}

function stopExtra() {
  if (extraPlayer) {
    extraPlayer.pause();
    extraPlayer = null;
  }
}

function stopPlayback() {
  playToken += 1;
  state.audio.pause();
  stopExtra();
  if (window.HearsayVoice) HearsayVoice.stop();
}

function fmt(ms) {
  const tenths = Math.round(ms / 100);
  return (tenths / 10).toFixed(1) + "s";
}

function currentSentence() {
  return state.sentences[state.current] || null;
}

function setMaterial(payload, audioUrl, owned) {
  stopPlayback();
  stopRecording(false);
  if (state.ownedUrl) URL.revokeObjectURL(state.ownedUrl);
  for (const take of state.takes.values()) URL.revokeObjectURL(take.url);
  state.takes.clear();
  state.ownedUrl = owned ? audioUrl : null;
  // 导入的是真人原声，跟读要模仿它本身，不用合成音替换；只有演示材料改用云端人声
  state.source = owned ? "import" : "demo";
  state.audio.src = audioUrl;
  state.audio.load();
  state.title = payload.title || "导入的材料";
  state.timingNote = payload.timing_note_zh || "";
  state.warning = payload.warning || "";
  state.productRule = payload.product_rule || state.productRule;
  state.sentences = payload.sentences || [];
  state.current = 0;
  $("hypothesis").value = "";
  render();
}

async function loadDemo() {
  setStatus("正在加载演示材料…");
  const response = await fetch("api/demo");
  const payload = await response.json();
  if (!response.ok) {
    setStatus(payload.error || "演示材料加载失败");
    return;
  }
  setMaterial(payload, payload.audio_url, false);
  setStatus(state.cloud.tts
    ? "已载入演示材料。原句用云端人声朗读（Deepgram aura-2-en），不是学习者录音。"
    : "已载入演示材料。参考音是 espeak-ng 合成的，不是学习者录音。");
}

async function fileDurationMs(file) {
  const bytes = await file.arrayBuffer();
  if (window.AudioContext || window.webkitAudioContext) {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    const ctx = new Ctx();
    try {
      const buffer = await ctx.decodeAudioData(bytes.slice(0));
      return Math.round(buffer.duration * 1000);
    } catch (_err) {
      // 有的容器解码不了，下面改用 audio 元素。
    } finally {
      await ctx.close();
    }
  }
  const url = URL.createObjectURL(file);
  try {
    const probe = new Audio(url);
    await new Promise((resolve, reject) => {
      probe.onloadedmetadata = () => resolve();
      probe.onerror = () => reject(new Error("这段音频读不了"));
    });
    if (!Number.isFinite(probe.duration)) throw new Error("读不到音频时长");
    return Math.round(probe.duration * 1000);
  } finally {
    URL.revokeObjectURL(url);
  }
}

async function onImport(event) {
  event.preventDefault();
  const file = $("import-audio").files[0];
  const text = $("import-text").value;
  const wordsFile = $("import-words").files[0];
  if (!file) {
    setStatus("先选一段参考音频。");
    return;
  }
  setStatus("正在切句…");
  let words = null;
  if (wordsFile) {
    try {
      words = JSON.parse(await wordsFile.text());
    } catch (_err) {
      setStatus("词级时间戳不是合法 JSON。");
      return;
    }
  }
  let durationMs;
  try {
    durationMs = await fileDurationMs(file);
  } catch (err) {
    setStatus(err.message || "这段音频读不了");
    return;
  }
  const response = await fetch("api/segment", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      text,
      duration_ms: durationMs,
      words,
      fallback: "proportional",
    }),
  });
  const payload = await response.json();
  if (!response.ok) {
    setStatus(payload.error || "切句失败");
    return;
  }
  const url = URL.createObjectURL(file);
  setMaterial({ ...payload, title: file.name }, url, true);
  if (payload.timing_source === "word_timestamps") {
    setStatus("已按词级时间戳切句。");
  } else if (payload.warning) {
    setStatus("词级时间戳对不上，已改用按词数比例切句。");
  } else {
    setStatus("没有词级时间戳，已按词数比例估计切句。");
  }
}

function renderSentences() {
  const list = $("sentences");
  list.replaceChildren();
  let lowCount = 0;
  let scored = 0;
  state.sentences.forEach((sentence, index) => {
    const take = state.takes.get(sentence.idx);
    if (take && take.feedback) {
      scored += 1;
      if (take.feedback.low_score) lowCount += 1;
    }
    const item = document.createElement("li");
    item.className = "sentence";
    if (index === state.current) item.classList.add("is-current");
    if (take && take.feedback && take.feedback.low_score) item.classList.add("is-low");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "sentence-select";
    button.addEventListener("click", () => selectSentence(index));
    const idx = document.createElement("span");
    idx.className = "idx";
    idx.textContent = String(index + 1);
    const text = document.createElement("span");
    text.className = "text";
    text.lang = "en";
    text.textContent = sentence.text;
    const meta = document.createElement("span");
    meta.className = "meta";
    const bits = [`${fmt(sentence.start_ms)}–${fmt(sentence.end_ms)}`];
    if (take && take.url) bits.push("已录音");
    if (take && take.feedback) {
      bits.push(`词召回 ${Math.round(take.feedback.word_recall * 100)}%`);
      if (take.feedback.low_score) bits.push("偏低");
    }
    meta.textContent = bits.join(" · ");
    button.append(idx, text, meta);
    item.append(button);
    list.append(item);
  });
  $("summary").textContent = scored
    ? `已算 ${scored} 句，其中 ${lowCount} 句词召回偏低。`
    : "还没有词级反馈。";
}

function renderTransport() {
  const sentence = currentSentence();
  $("material-title").textContent = state.title;
  $("timing-note").textContent = state.timingNote;
  $("product-rule").textContent = state.productRule;
  const warning = $("warning");
  warning.hidden = !state.warning;
  warning.textContent = state.warning || "";
  if (!sentence) {
    $("current-label").textContent = "当前句";
    $("current-text").textContent = "先载入演示材料，或导入一段音频。";
    $("play-ref").disabled = true;
    $("record").disabled = true;
    $("play-both").disabled = true;
    $("play-take").disabled = true;
    $("score").disabled = true;
    $("transcribe").disabled = true;
    return;
  }
  const take = state.takes.get(sentence.idx);
  $("current-label").textContent = `第 ${state.current + 1} / ${state.sentences.length} 句`;
  $("current-text").textContent = sentence.text;
  $("play-ref").disabled = state.recording;
  $("record").disabled = false;
  $("record").textContent = state.recording ? "停止录音" : "开始录音";
  $("record").setAttribute("aria-pressed", state.recording ? "true" : "false");
  const hasAudio = Boolean(take && take.url);
  $("play-both").disabled = !hasAudio || state.recording;
  $("play-take").disabled = !hasAudio || state.recording;
  $("score").disabled = state.recording;
  $("transcribe").disabled = !hasAudio || state.recording;
  $("transcribe").textContent = state.cloud.asr ? "重新识别（云端）" : "尝试本机 ASR";
  if (!state.recording) {
    $("hypothesis").value = take && take.hypothesis ? take.hypothesis : $("hypothesis").value;
  }
  renderFeedback(take && take.feedback);
}

function renderFeedback(feedback) {
  const box = $("feedback");
  box.replaceChildren();
  if (!feedback) return;
  const line = document.createElement("p");
  line.className = "scoreline";
  const recall = Math.round(feedback.word_recall * 100);
  const precision = Math.round(feedback.word_precision * 100);
  line.textContent = feedback.low_score
    ? `词召回 ${recall}%，精确率 ${precision}%。这一句偏低，建议再跟一次。这不是音素错误。`
    : `词召回 ${recall}%，精确率 ${precision}%。没有标成低分句。`;
  box.append(line);
  for (const row of feedback.alignment || []) {
    const chip = document.createElement("span");
    chip.className = `token ${row.op}`;
    if (row.op === "match") chip.textContent = row.ref;
    else if (row.op === "substitution") chip.textContent = `${row.ref} → ${row.hyp}`;
    else if (row.op === "deletion") chip.textContent = `${row.ref}（未说出）`;
    else chip.textContent = `${row.hyp}（多说）`;
    box.append(chip);
  }
}

function render() {
  renderSentences();
  renderTransport();
}

function selectSentence(index) {
  if (state.recording) return;
  stopPlayback();
  state.current = index;
  const take = state.takes.get(currentSentence().idx);
  $("hypothesis").value = take && take.hypothesis ? take.hypothesis : "";
  render();
}

function playRange(startMs, endMs) {
  stopExtra();
  const token = ++playToken;
  const audio = state.audio;
  return new Promise((resolve) => {
    const start = startMs / 1000;
    const end = endMs / 1000;
    let settled = false;
    const finish = (completed) => {
      if (settled) return;
      settled = true;
      audio.removeEventListener("timeupdate", onTime);
      clearTimeout(timer);
      if (token === playToken) audio.pause();
      resolve(completed);
    };
    const onTime = () => {
      if (token !== playToken) finish(false);
      else if (audio.currentTime >= end - 0.03) finish(true);
    };
    audio.addEventListener("timeupdate", onTime);
    const timer = setTimeout(() => finish(token === playToken), Math.max(80, (end - start) * 1000 + 150));
    const begin = () => {
      if (token !== playToken) {
        finish(false);
        return;
      }
      try {
        audio.currentTime = start;
      } catch (_err) {
        finish(false);
        return;
      }
      audio.play().then(() => {
        if (token !== playToken) finish(false);
      }).catch(() => {
        setStatus("原句播放失败。");
        finish(false);
      });
    };
    if (audio.readyState >= 1) begin();
    else {
      audio.addEventListener("loadedmetadata", begin, { once: true });
      audio.addEventListener("error", () => finish(false), { once: true });
    }
  });
}

// 播放当前句的原句：演示材料在云端朗读可用时用自然人声，导入的真人音频播放原片段
async function playSentenceRef(sentence) {
  if (state.cloud.tts && state.source === "demo") {
    stopPlayback();
    const token = playToken;
    await HearsayVoice.speak(sentence.text);
    return token === playToken;
  }
  return playRange(sentence.start_ms, sentence.end_ms);
}

function playUrl(url) {
  stopExtra();
  const token = ++playToken;
  state.audio.pause();
  const player = new Audio(url);
  extraPlayer = player;
  return new Promise((resolve) => {
    const done = (ok) => {
      if (extraPlayer === player) extraPlayer = null;
      resolve(ok && token === playToken);
    };
    player.onended = () => done(true);
    player.onerror = () => done(false);
    player.play().catch(() => {
      setStatus("录音播放失败。");
      done(false);
    });
  });
}

function recognitionCtor() {
  return window.SpeechRecognition || window.webkitSpeechRecognition || null;
}

function startRecognition() {
  const Ctor = recognitionCtor();
  state.hypothesisDraft = "";
  if (!Ctor) return;
  try {
    const recognition = new Ctor();
    recognition.lang = "en-US";
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.onresult = (event) => {
      let text = "";
      for (let i = 0; i < event.results.length; i += 1) {
        text += event.results[i][0].transcript;
      }
      state.hypothesisDraft = text.trim();
      if (state.recording) $("hypothesis").value = state.hypothesisDraft;
    };
    recognition.onerror = () => {
      setStatus("浏览器语音识别不可用。可以自己粘贴转写。");
    };
    recognition.onend = () => {
      if (state.recording && state.recognition === recognition) {
        try { recognition.start(); } catch (_err) { /* 有的浏览器拒绝立刻重开 */ }
      }
    };
    recognition.start();
    state.recognition = recognition;
  } catch (_err) {
    state.recognition = null;
  }
}

function stopRecognition() {
  const recognition = state.recognition;
  state.recognition = null;
  if (!recognition) return;
  try { recognition.onend = null; recognition.stop(); } catch (_err) { /* 已经停了 */ }
}

async function toggleRecord() {
  if (state.recording) {
    stopRecording(true);
    return;
  }
  const sentence = currentSentence();
  if (!sentence) return;
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    setStatus("这个浏览器不能录音。");
    return;
  }
  stopPlayback();
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch (_err) {
    setStatus("没有拿到麦克风权限。你仍然可以粘贴转写来算词级相似度。");
    return;
  }
  const mime = window.MediaRecorder && MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
    ? "audio/webm;codecs=opus"
    : "";
  const recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
  const chunks = [];
  recorder.ondataavailable = (event) => {
    if (event.data && event.data.size) chunks.push(event.data);
  };
  recorder.onstop = () => {
    stream.getTracks().forEach((track) => track.stop());
    const blob = new Blob(chunks, { type: recorder.mimeType || "audio/webm" });
    const url = URL.createObjectURL(blob);
    const previous = state.takes.get(sentence.idx);
    if (previous) URL.revokeObjectURL(previous.url);
    const hypothesis = ($("hypothesis").value || state.hypothesisDraft || "").trim();
    state.takes.set(sentence.idx, { url, blob, hypothesis, feedback: null });
    state.recording = false;
    state.recorder = null;
    $("hypothesis").value = hypothesis;
    render();
    if (state.cloud.asr) {
      transcribeCurrent();
      return;
    }
    setStatus(hypothesis ? "录音留在本页。正在计算词级相似度。" : "录音留在本页。还没有转写，可以粘贴后再计算。");
    if (hypothesis) scoreCurrent();
  };
  state.recorder = recorder;
  state.recording = true;
  if (state.cloud.asr) {
    // 云端识别：停止后整段上传，录音时不再开浏览器识别（它会把语法错误自动改对）
    state.hypothesisDraft = "";
    $("hypothesis").value = "";
  } else {
    startRecognition();
  }
  recorder.start();
  render();
  setStatus("正在录音。再说一次当前句，说完点停止。");
}

function stopRecording(save) {
  stopRecognition();
  const recorder = state.recorder;
  if (recorder && recorder.state === "recording") {
    if (!save) recorder.onstop = null;
    recorder.stop();
  }
  if (!save) {
    state.recording = false;
    state.recorder = null;
  }
}

async function scoreCurrent() {
  const sentence = currentSentence();
  if (!sentence) return;
  const hypothesis = $("hypothesis").value.trim();
  const response = await fetch("api/feedback", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      idx: sentence.idx,
      reference: sentence.text,
      hypothesis,
    }),
  });
  const payload = await response.json();
  if (!response.ok) {
    setStatus(payload.error || "算不了词级相似度");
    return;
  }
  const take = state.takes.get(sentence.idx) || { url: "", blob: null, hypothesis, feedback: null };
  take.hypothesis = hypothesis;
  take.feedback = payload;
  state.takes.set(sentence.idx, take);
  render();
  setStatus(payload.low_score ? "这一句词召回偏低。" : "这一句没有标成低分。");
}

async function transcribeCurrent() {
  const sentence = currentSentence();
  const take = sentence && state.takes.get(sentence.idx);
  if (!take || !take.blob) {
    setStatus("先录一段，才能识别。");
    return;
  }
  if (state.cloud.asr) {
    setStatus("识别中…");
    $("transcribe").disabled = true;
    try {
      const result = await HearsayVoice.transcribe(take.blob);
      take.hypothesis = result.text || "";
      $("hypothesis").value = take.hypothesis;
      if (take.hypothesis) {
        await scoreCurrent();
        setStatus("已识别（云端 Whisper，原样转写）并计算了词级相似度。");
      } else {
        setStatus("没有识别到内容，可以重录或粘贴转写。");
      }
    } catch (err) {
      setStatus(`${err.message}。可以重录或粘贴转写。`);
    }
    render();
    return;
  }
  setStatus("正在请求本机转写…");
  const response = await fetch("api/transcribe", {
    method: "POST",
    headers: { "Content-Type": take.blob.type || "application/octet-stream" },
    body: take.blob,
  });
  const payload = await response.json();
  if (!response.ok) {
    setStatus(payload.error || "本机转写没有跑起来");
    return;
  }
  $("hypothesis").value = payload.text || "";
  setStatus(payload.text ? "本机转写已填入，可以再计算相似度。" : "本机转写是空的。");
}

async function playReference() {
  const sentence = currentSentence();
  if (!sentence) return;
  setStatus("正在播放原句。");
  const ok = await playSentenceRef(sentence);
  if (ok) setStatus("原句播完了。");
}

async function playTakeOnly() {
  const sentence = currentSentence();
  const take = sentence && state.takes.get(sentence.idx);
  if (!take || !take.url) return;
  setStatus("正在播放你的录音。");
  await playUrl(take.url);
}

async function playBoth() {
  const sentence = currentSentence();
  const take = sentence && state.takes.get(sentence.idx);
  if (!sentence || !take || !take.url) return;
  setStatus("先听原句，再听你的录音。");
  const ok = await playSentenceRef(sentence);
  if (!ok) return;
  await playUrl(take.url);
  setStatus("对照播完了。");
}

$("load-demo").addEventListener("click", () => {
  loadDemo().catch(() => setStatus("演示材料加载失败"));
});
$("toggle-import").addEventListener("click", () => {
  const form = $("import-form");
  form.hidden = !form.hidden;
});
$("import-form").addEventListener("submit", (event) => {
  onImport(event).catch(() => setStatus("导入失败"));
});
$("play-ref").addEventListener("click", () => { playReference(); });
$("record").addEventListener("click", () => { toggleRecord(); });
$("play-both").addEventListener("click", () => { playBoth(); });
$("play-take").addEventListener("click", () => { playTakeOnly(); });
$("score").addEventListener("click", () => { scoreCurrent(); });
$("transcribe").addEventListener("click", () => { transcribeCurrent(); });

const initialRule = "实验 D 未通过，本页不写音素级错误。完整说明会在材料加载后显示。";
$("product-rule").textContent = initialRule;
state.productRule = initialRule;
render();

// 先探测云端语音，再加载演示材料（加载提示与原句播放方式取决于它）
(window.HearsayVoice ? HearsayVoice.cloudStatus() : Promise.resolve({ tts: false, asr: false }))
  .then((cloud) => {
    state.cloud = cloud;
    if (cloud.asr) {
      $("asr-hint").textContent = "识别走云端 Whisper（Workers AI）：录完自动上传，原样转写，保留语法错误；演示材料的原句用云端人声朗读，导入的音频仍播放原声。";
    }
    render();
  })
  .then(() => loadDemo())
  .catch(() => setStatus("演示材料加载失败。确认是用 python -m m1_shadow 打开的。"));
