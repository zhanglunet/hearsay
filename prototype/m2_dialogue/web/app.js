"use strict";

const $ = (id) => document.getElementById(id);
const state = { sessionId: null, ended: false, recognizing: false };

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

async function startSession() {
  setStatus("正在开始…");
  $("chat").textContent = "";
  $("recap-panel").hidden = true;
  state.ended = false;
  try {
    const payload = await api("/api/session");
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
    const payload = await api("/api/turn", { session_id: state.sessionId, text });
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
  $("recap-panel").scrollIntoView({ block: "start" });
}

function setupMic() {
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!Recognition) {
    $("mic").textContent = "无语音识别，请打字";
    return;
  }
  const recognition = new Recognition();
  recognition.lang = "en-US";
  recognition.interimResults = false;
  recognition.onresult = (event) => {
    $("input").value = event.results[0][0].transcript;
    setStatus("识别完成，可修改后发送。识别会归一化，不是权威转写。");
  };
  recognition.onerror = () => setStatus("语音识别失败，请打字。");
  recognition.onend = () => { state.recognizing = false; $("mic").textContent = "🎤 说话"; };
  $("mic").addEventListener("click", () => {
    if (state.recognizing) { recognition.stop(); return; }
    state.recognizing = true;
    $("mic").textContent = "正在听…再点停止";
    recognition.start();
  });
}

$("start").addEventListener("click", startSession);
$("send").addEventListener("click", sendTurn);
$("end").addEventListener("click", endSession);
$("input").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); sendTurn(); }
});
setupMic();

fetch("/api/scenario").then((r) => r.json()).then((payload) => {
  const scenario = payload.scenario;
  $("scenario-title").textContent = scenario.title;
  $("scenario-roles").textContent =
    `你：${scenario.learner_role} ｜ Agent：${scenario.agent_role} ｜ 水平 ${scenario.target_cefr}`;
  for (const text of scenario.objectives) {
    const li = document.createElement("li");
    li.textContent = text;
    $("scenario-objectives").appendChild(li);
  }
  $("tutor-note").textContent = `tutor 后端：${payload.tutor}。${payload.notes}`;
}).catch(() => setStatus("场景加载失败。确认是用 python -m m2_dialogue 打开的。"));
