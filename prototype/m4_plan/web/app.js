"use strict";

const $ = (id) => document.getElementById(id);
const KIND_NAMES = { listen: "听", shadow: "跟读", retell: "复述", converse: "对话" };
const SKILL_NAMES = { L: "听力", SP: "口语产出", SI: "口语互动", PH: "语音控制" };

async function loadPlan() {
  const response = await fetch(`/api/plan?minutes=${$("minutes").value}`);
  const plan = await response.json();
  if (!response.ok) { $("rationale").textContent = plan.error; return; }
  $("rationale").textContent = plan.rationale_zh;
  $("plan-notes").textContent = plan.notes;
  $("blocks").textContent = "";
  for (const block of plan.blocks) {
    const div = document.createElement("div");
    div.className = "block";
    const head = document.createElement("div");
    head.className = "kind";
    head.textContent = `${KIND_NAMES[block.type] || block.type} · ${block.minutes} 分钟`;
    const body = document.createElement("div");
    body.textContent = block.content_zh;
    div.appendChild(head);
    div.appendChild(body);
    $("blocks").appendChild(div);
  }
}

async function loadProgress() {
  const response = await fetch("/api/progress");
  const payload = await response.json();
  const s = payload.summary;
  $("progress-summary").textContent =
    `共 ${s.total} 条：demonstrated ${s.demonstrated} ｜ emerging ${s.emerging} ｜ not_started ${s.not_started}`;
  $("progress-items").textContent = "";
  const table = document.createElement("table");
  let lastSkill = null;
  for (const item of payload.items) {
    if (item.skill !== lastSkill) {
      lastSkill = item.skill;
      const tr = document.createElement("tr");
      tr.className = "skill-head";
      const td = document.createElement("td");
      td.colSpan = 4;
      td.textContent = SKILL_NAMES[item.skill] || item.skill;
      tr.appendChild(td);
      table.appendChild(tr);
    }
    const tr = document.createElement("tr");
    const values = [
      item.id + (item.schedulable ? "" : "（保留）"),
      item.zh,
      `证据 ${item.evidence}（demonstrated ${item.demonstrated} / partial ${item.partial}）`,
    ];
    for (const value of values) {
      const td = document.createElement("td");
      td.textContent = value;
      tr.appendChild(td);
    }
    const td = document.createElement("td");
    const badge = document.createElement("span");
    badge.className = `badge ${item.status}`;
    badge.textContent = item.status;
    td.appendChild(badge);
    tr.appendChild(td);
    table.appendChild(tr);
  }
  $("progress-items").appendChild(table);
}

$("reload").addEventListener("click", loadPlan);
$("add-evidence").addEventListener("click", async () => {
  const response = await fetch("/api/evidence", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ can_do_id: $("evidence-id").value.trim(),
                           verdict: $("evidence-verdict").value }),
  });
  const payload = await response.json();
  $("evidence-status").textContent = response.ok ? "已记录" : payload.error;
  if (response.ok) loadProgress();
});

loadPlan();
loadProgress();
