"use strict";

const $ = (id) => document.getElementById(id);
const state = { sessionId: null, ended: false, recognizing: false, audioBlob: null, recorder: null };

function setStatus(text) { $("status").textContent = text; }

async function api(path, body) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
  return payload;
}

function addMessage(speaker, text) {
  const div = document.createElement("div");
  div.className = `msg ${speaker}`;
  const who = document.createElement("span");
  who.className = "who";
  who.textContent = speaker === "agent" ? "Alex（Agent）" : "你";
  div.appendChild(who);
  div.appendChild(document.createTextNode(text));
  $("chat").appendChild(div);
  div.scrollIntoView({ block: "nearest" });
  if (speaker === "agent" && $("speak-agent").checked && "speechSynthesis" in window) {
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = "en-US";
    window.speechSynthesis.speak(utterance);
  }
}

function setConversationEnabled(enabled) {
  for (const id of ["input", "send", "mic", "end"]) $(id).disabled = !enabled;
  $("start").disabled = enabled;
}

async function startSession(mode) {
  setStatus("正在开始…");
  $("chat").textContent = "";
  $("recap-panel").hidden = true;
  state.ended = false;
  try {
    const payload = await api("/api/session", mode ? { mode } : {});
    if (payload.scenario) renderScenario(payload.scenario);
    state.sessionId = payload.session_id;
    addMessage("agent", payload.opening);
    setConversationEnabled(true);
    setStatus("轮到你了。用英语回答 Alex。");
    $("input").focus();
  } catch (err) { setStatus(err.message); }
}

async function sendTurn() {
  const text = $("input").value.trim();
  if (!text || !state.sessionId || state.ended) return;
  $("send").disabled = true;
  try {
    const body = { session_id: state.sessionId, text };
    if (state.audioBlob) {
      body.audio_b64 = await blobToBase64(state.audioBlob);
      body.audio_type = state.audioBlob.type;
    }
    const payload = await api("/api/turn", body);
    state.audioBlob = null;
    addMessage("learner", text);
    $("input").value = "";
    addMessage("agent", payload.agent_text);
    setStatus(payload.new_recasts.length
      ? `记下 ${payload.new_recasts.length} 条待核对提示，复盘里看。继续聊。`
      : `第 ${payload.n_learner_turns} 轮。继续，或点「结束并复盘」。`);
  } catch (err) { setStatus(err.message); }
  $("send").disabled = false;
  $("input").focus();
}

function blobToBase64(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result.split(",")[1]);
    reader.onerror = reject;
    reader.readAsDataURL(blob);
  });
}

async function endSession() {
  if (!state.sessionId) return;
  setStatus("正在整理复盘…");
  try {
    const recap = await api("/api/end", { session_id: state.sessionId });
    state.ended = true;
    setConversationEnabled(false);
    $("start").disabled = false;
    $("start").textContent = "再来一轮";
    renderRecap(recap);
    setStatus("复盘已生成。recast 提示未经批处理确认。");
  } catch (err) { setStatus(err.message); }
}

function renderRecap(recap) {
  $("recap-panel").hidden = false;
  $("recap-summary").textContent = recap.summary_zh;
  $("recap-metrics").textContent =
    `时长 ${recap.duration_sec}s ｜ 你 ${recap.n_learner_turns} 轮 / ${recap.learner_words} 词 ｜ ` +
    `Agent ${recap.n_agent_turns} 轮 / ${recap.agent_words} 词 ｜ 意外问题${recap.scripted_event_fired ? "已触发" : "未触发"}`;
  $("recap-objectives").textContent = "";
  for (const objective of recap.objectives) {
    const li = document.createElement("li");
    li.className = objective.covered ? "covered" : "missed";
    li.textContent = `${objective.covered ? "✓" : "○"} ${objective.text}`;
    $("recap-objectives").appendChild(li);
  }
  $("recap-recasts").textContent = "";
  if (!recap.recasts.length) {
    $("recap-recasts").textContent = "规则没有扫到典型迁移错误；这不等于没有错误。";
  }
  for (const r of recap.recasts) {
    const div = document.createElement("div");
    div.className = "recast";
    div.textContent = `${r.code}（${r.status} / ${r.detected_by}）：你说 “${r.observed}”，更自然的说法：“${r.expected}”`;
    $("recap-recasts").appendChild(div);
  }
  $("recap-notes").textContent = recap.notes;
  renderBatch(recap.batch);
  $("recap-panel").scrollIntoView({ block: "start" });
}

function renderBatch(batch) {
  const container = $("recap-batch");
  container.textContent = "";
  if (!batch) return;
  const title = document.createElement("h3");
  title.textContent = "事后批处理（权威转写与核对）";
  container.appendChild(title);
  const line = document.createElement("p");
  line.className = "note";
  line.textContent = `用时 ${batch.duration_sec}s ｜ confirmed ${batch.confirmed.length} 条 ｜ ` +
    `discarded ${batch.discarded.length} 条 ｜ 实时提示误报率 ` +
    (batch.false_positive_rate === null ? "—（无实时提示）" : `${Math.round(batch.false_positive_rate * 100)}%（规则口径）`);
  container.appendChild(line);
  for (const item of batch.discarded) {
    const div = document.createElement("div");
    div.className = "recast";
    div.textContent = `已丢弃：第 ${item.utterance_id} 轮 ${item.code} “${item.observed}”——批处理未找到对应错误`;
    container.appendChild(div);
  }
  for (const t of batch.transcripts) {
    const div = document.createElement("div");
    div.className = "note";
    div.textContent = `第 ${t.utterance_id} 轮（${t.source}）：${t.batch_text}` +
      (t.batch_text !== t.realtime_text ? ` ｜ 实时文本曾是：${t.realtime_text}` : "");
    container.appendChild(div);
  }
}

function setupMic() {
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  const canRecord = Boolean(navigator.mediaDevices && navigator.mediaDevices.getUserMedia &&
                            window.MediaRecorder);
  if (!Recognition && !canRecord) {
    $("mic").textContent = "无语音输入，请打字";
    return;
  }
  let recognition = null;
  if (Recognition) {
    recognition = new Recognition();
    recognition.lang = "en-US";
    recognition.interimResults = false;
    recognition.onresult = (event) => {
      $("input").value = event.results[0][0].transcript;
      setStatus("识别完成，可修改后发送。识别会归一化，不是权威转写。");
    };
    recognition.onerror = () => setStatus("语音识别失败。录音仍在，可打字补转写后发送。");
  }

  async function start() {
    state.audioBlob = null;
    if (canRecord) {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        const chunks = [];
        state.recorder = new MediaRecorder(stream);
        state.recorder.ondataavailable = (event) => { if (event.data.size) chunks.push(event.data); };
        state.recorder.onstop = () => {
          state.audioBlob = new Blob(chunks, { type: state.recorder.mimeType || "audio/webm" });
          stream.getTracks().forEach((track) => track.stop());
          setStatus("录音完成。发送时随本轮一起上传（仅批处理启用时才落盘，复盘后删除）。");
        };
        state.recorder.start();
      } catch (err) {
        setStatus("麦克风不可用：" + err.message);
        return;
      }
    }
    if (recognition) recognition.start();
    state.recognizing = true;
    $("mic").textContent = "正在听…再点停止";
  }

  function stop() {
    if (state.recorder && state.recorder.state !== "inactive") state.recorder.stop();
    if (recognition) recognition.stop();
    state.recognizing = false;
    $("mic").textContent = "🎤 说话";
  }

  $("mic").addEventListener("click", () => {
    if (state.recognizing) stop();
    else start();
  });
}

$("start").addEventListener("click", () => startSession());
$("start-review").addEventListener("click", () => startSession("review"));
$("send").addEventListener("click", sendTurn);
$("end").addEventListener("click", endSession);
$("input").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); sendTurn(); }
});
setupMic();

function renderScenario(scenario) {
  $("scenario-title").textContent = scenario.title;
  $("scenario-roles").textContent =
    `你：${scenario.learner_role} ｜ Agent：${scenario.agent_role} ｜ 水平 ${scenario.target_cefr}`;
  $("scenario-objectives").textContent = "";
  for (const text of scenario.objectives) {
    const li = document.createElement("li");
    li.textContent = text;
    $("scenario-objectives").appendChild(li);
  }
}

fetch("/api/scenario").then((r) => r.json()).then((payload) => {
  renderScenario(payload.scenario);
  $("tutor-note").textContent = `tutor 后端：${payload.tutor}。${payload.notes}`;
}).catch(() => setStatus("场景加载失败。确认是用 python -m m2_dialogue 打开的。"));
