"use strict";

const $ = (id) => document.getElementById(id);
const KIND = { listen: "听", shadow: "跟读", retell: "复述", converse: "对话" };

async function loadPlan() {
  const response = await fetch(`/api/plan?minutes=${$("minutes").value}`);
  const plan = await response.json();
  if (!response.ok) { $("rationale").textContent = plan.error; return; }
  $("rationale").textContent = plan.rationale_zh;
  $("blocks").textContent = "";
  for (const block of plan.blocks) {
    const div = document.createElement("div");
    div.className = "block";
    const head = document.createElement("span");
    head.className = "kind";
    head.textContent = `${KIND[block.type] || block.type} · ${block.minutes} 分钟`;
    const body = document.createElement("span");
    body.textContent = block.content_zh;
    div.appendChild(head);
    div.appendChild(body);
    $("blocks").appendChild(div);
  }
  const due = $("due-cards");
  due.textContent = "";
  if (plan.due_items && plan.due_items.length) {
    const title = document.createElement("p");
    title.className = "note";
    title.textContent = "到期复习卡：去「对话 / 复习」用一遍，然后到 M4 进度页评分";
    due.appendChild(title);
    for (const item of plan.due_items) {
      const div = document.createElement("div");
      div.className = "due";
      div.textContent = `${item.item_id}（stability ${item.stability} / difficulty ${item.difficulty}）`;
      due.appendChild(div);
    }
  }
}

async function loadProgress() {
  const response = await fetch("/api/progress");
  const payload = await response.json();
  const s = payload.summary;
  $("progress-summary").textContent =
    `共 ${s.total} 条：demonstrated ${s.demonstrated} ｜ emerging ${s.emerging} ｜ not_started ${s.not_started}`;
  const links = $("slices");
  for (const slice of payload.slices) {
    const a = document.createElement("a");
    a.href = `http://127.0.0.1:${slice.port}/`;
    a.target = "_blank";
    a.textContent = slice.title;
    links.appendChild(a);
  }
}

$("reload").addEventListener("click", loadPlan);
loadPlan();
loadProgress();
