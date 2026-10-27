"use strict";

const $ = (id) => document.getElementById(id);
const state = { sessionId: null, sentences: [], questions: [], materialId: "demo", useTts: false };

function setStatus(text) { $("status").textContent = text; }

async function playSentence(sentence) {
  // 云端朗读可用时，演示材料（原为 espeak 合成音频）和生成材料都逐句用自然人声；
  // 不可用时：生成材料退回浏览器朗读，演示材料播放原音频片段
  const voice = await HearsayVoice.cloudStatus();
  if (voice.tts || state.useTts) {
    $("audio").pause();
    HearsayVoice.speak(sentence.text);
    return;
  }
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

function renderMaterial(material) {
  state.sessionId = null;
  state.materialId = material.material_id;
  state.useTts = material.use_tts;
  state.sentences = material.sentences;
  state.questions = material.questions;
  $("material-title").textContent = material.title;
  $("audio").src = material.audio_url || "";
  $("sentences").textContent = "";
  $("questions").textContent = "";
  $("result").hidden = true;
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

async function loadMaterial() {
  const response = await fetch("api/material");
  renderMaterial(await response.json());
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
    const response = await fetch("api/answer", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: state.sessionId, material_id: state.materialId,
                             question_id: q.id, answer }),
    });
    const payload = await response.json();
    if (!response.ok) { setStatus(payload.error); return; }
    state.sessionId = payload.session_id;
    outcome.className = payload.passed ? "pass" : "fail";
    outcome.textContent = ` ${payload.passed ? "✓" : "✗"} 得分 ${payload.score} ｜ 参考：${payload.expected}`;
    setStatus(`${q.id} 已判定（规则）`);
  });
  div.appendChild(button);
  div.appendChild(outcome);
  $("questions").appendChild(div);
}

$("generate").addEventListener("click", async () => {
  const topic = $("gen-topic").value.trim();
  if (!topic) { setStatus("先写一个话题"); return; }
  setStatus("正在生成材料与题目（LLM，约十几秒）…");
  try {
    const response = await fetch("api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ level: $("gen-level").value, topic }),
    });
    const payload = await response.json();
    if (!response.ok) { setStatus(payload.error); return; }
    renderMaterial(payload);
    setStatus("新材料已生成，逐句听（浏览器 TTS 朗读）。");
  } catch (err) { setStatus(err.message); }
});

$("finish").addEventListener("click", async () => {
  if (!state.sessionId) { setStatus("先至少作答一题"); return; }
  const response = await fetch("api/finish", {
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
