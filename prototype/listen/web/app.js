"use strict";

const $ = (id) => document.getElementById(id);
const state = { sessionId: null, sentences: [], questions: [], answers: {} };

function setStatus(text) { $("status").textContent = text; }

function playSentence(sentence) {
  const audio = $("audio");
  audio.currentTime = sentence.start_ms / 1000;
  audio.play();
  const stopAt = sentence.end_ms / 1000;
  const timer = setInterval(() => {
    if (audio.currentTime >= stopAt || audio.paused) {
      audio.pause();
      clearInterval(timer);
    }
  }, 60);
}

async function loadMaterial() {
  const response = await fetch("/api/material");
  const material = await response.json();
  $("material-title").textContent = material.title;
  $("audio").src = material.audio_url;
  state.sentences = material.sentences;
  state.questions = material.questions;
  for (const s of material.sentences) {
    const div = document.createElement("div");
    div.className = "row";
    const button = document.createElement("button");
    button.textContent = `▶ 第 ${s.idx + 1} 句`;
    button.addEventListener("click", () => playSentence(s));
    const span = document.createElement("span");
    span.textContent = s.text;
    div.appendChild(button);
    div.appendChild(span);
    $("sentences").appendChild(div);
  }
  for (const q of material.questions) renderQuestion(q);
}

function renderQuestion(q) {
  const div = document.createElement("div");
  div.className = "question";
  const title = document.createElement("p");
  title.textContent = `${q.id}（${q.type}）${q.q_zh}`;
  div.appendChild(title);
  const inputWrap = document.createElement("div");
  inputWrap.className = "row";
  if (q.options) {
    for (let i = 0; i < q.options.length; i++) {
      const label = document.createElement("label");
      const radio = document.createElement("input");
      radio.type = "radio";
      radio.name = q.id;
      radio.value = i;
      label.appendChild(radio);
      label.appendChild(document.createTextNode(" " + q.options[i]));
      inputWrap.appendChild(label);
    }
  } else {
    const input = document.createElement("input");
    input.type = "text";
    input.id = `answer-${q.id}`;
    inputWrap.appendChild(input);
  }
  div.appendChild(inputWrap);
  const button = document.createElement("button");
  button.textContent = "提交";
  const outcome = document.createElement("span");
  outcome.className = "note";
  button.addEventListener("click", async () => {
    let answer;
    if (q.options) {
      const checked = document.querySelector(`input[name="${q.id}"]:checked`);
      if (!checked) { setStatus(`${q.id} 还没选`); return; }
      answer = Number(checked.value);
    } else {
      answer = $(`answer-${q.id}`).value.trim();
    }
    const response = await fetch("/api/answer", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: state.sessionId, question_id: q.id, answer }),
    });
    const payload = await response.json();
    if (!response.ok) { setStatus(payload.error); return; }
    state.sessionId = payload.session_id;
    state.answers[q.id] = true;
    outcome.className = payload.passed ? "pass" : "fail";
    outcome.textContent = ` ${payload.passed ? "✓" : "✗"} 得分 ${payload.score} ｜ 参考：${payload.expected}`;
    setStatus(`${q.id} 已判定（规则）`);
  });
  div.appendChild(button);
  div.appendChild(outcome);
  $("questions").appendChild(div);
}

$("finish").addEventListener("click", async () => {
  if (!state.sessionId) { setStatus("先至少作答一题"); return; }
  const response = await fetch("/api/finish", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: state.sessionId }),
  });
  const payload = await response.json();
  if (!response.ok) { setStatus(payload.error); return; }
  $("result").hidden = false;
  $("summary").textContent =
    `答对 ${payload.passed}/${payload.answered}（共 ${payload.total} 题），平均得分 ${payload.score}。`;
  $("detail").textContent = "";
  for (const [cid, verdict] of Object.entries(payload.can_do)) {
    const p = document.createElement("p");
    p.className = "note";
    p.textContent = `can-do ${cid}：${verdict}（source=rule，已写入进度页）`;
    $("detail").appendChild(p);
  }
  $("ingest-note").textContent = payload.ingest
    ? `M3 回流：H 类错误 ${payload.h_errors} 条，${payload.ingest.reason}`
    : "M3 回流已关闭";
  setStatus(payload.note);
});

loadMaterial().catch((err) => setStatus(err.message));
