"use strict";

const $ = (id) => document.getElementById(id);
let startedAt = null;
let durationSec = null;

$("load-demo").addEventListener("click", async () => {
  const response = await fetch("api/demo");
  const payload = await response.json();
  $("material").value = payload.material_text;
  setStatus("已载入：" + payload.title);
});

function setStatus(text) { $("status").textContent = text; }

$("evaluate").addEventListener("click", async () => {
  setStatus("正在评估…");
  try {
    const response = await fetch("api/evaluate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        material_text: $("material").value,
        retell_text: $("retell").value,
        duration_sec: durationSec,
      }),
    });
    const payload = await response.json();
    if (!response.ok) { setStatus(payload.error); return; }
    $("result").hidden = false;
    $("summary").textContent = payload.summary_zh;
    const cov = payload.coverage;
    $("coverage-detail").textContent =
      `覆盖关键词：${cov.matched.join("、") || "无"} ｜ 检测器：${payload.detection}` +
      (payload.fluency.wpm ? ` ｜ ${payload.fluency.wpm} wpm` : "");
    $("errors").textContent = "";
    if (!payload.errors.length) {
      $("errors").textContent = "没有检出 G/L 类错误（不等于没有错误）。";
    }
    for (const e of payload.errors) {
      const div = document.createElement("div");
      div.className = "error";
      div.textContent = `${e.code}（${e.detected_by}）：你说 “${e.observed}”，更自然的说法：“${e.expected}”`;
      $("errors").appendChild(div);
    }
    $("ingest-note").textContent = payload.ingest
      ? `M3 回流：${payload.ingest.ingested ? `已写入 ${payload.ingest.instances} 条 confirmed 错误` : payload.ingest.reason}`
      : "M3 回流已关闭（HEARSAY_M3_INGEST=0）";
    setStatus("评估完成。");
  } catch (err) { setStatus(err.message); }
});

function startTimer() {
  startedAt = Date.now();
  durationSec = null;
  $("timer").textContent = "正在录音…再点停止";
  $("mic").textContent = "停止";
}

function stopTimer() {
  durationSec = (Date.now() - startedAt) / 1000;
  $("timer").textContent = `复述时长 ${durationSec.toFixed(1)} 秒（含停顿）`;
  startedAt = null;
  $("mic").textContent = "🎤 开始复述";
}

// 云端识别（Workers AI Whisper，原样转写、保留语法错误）：录音 → 停止后上传
function setupCloudMic() {
  const recorder = HearsayVoice.createRecorder();
  if (!recorder.supported) return false;
  $("mic").addEventListener("click", async () => {
    if (startedAt) {
      stopTimer();
      $("mic").disabled = true;
      setStatus("识别中…");
      try {
        const blob = await recorder.stop();
        const result = await HearsayVoice.transcribe(blob);
        $("retell").value = result.text;
        setStatus(result.text ? "识别完成，可修改后点「评估复述」。" : "没有识别到内容，可重录或打字。");
      } catch (err) {
        setStatus(`${err.message}。可重录或打字。`);
      }
      $("mic").disabled = false;
    } else {
      try {
        await recorder.start();
      } catch (err) {
        setStatus("麦克风不可用：" + err.message);
        return;
      }
      $("retell").value = "";
      startTimer();
      setStatus("正在录音，说完再点「停止」。");
    }
  });
  return true;
}

// 本地开发兜底：浏览器识别（会把语法错误自动改对，不是原样转写）
function setupBrowserMic() {
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!Recognition) {
    $("mic").textContent = "无语音识别，请打字";
    $("mic").disabled = true;
    return;
  }
  const recognition = new Recognition();
  recognition.lang = "en-US";
  recognition.continuous = true;
  recognition.interimResults = false;
  let finalText = "";
  recognition.onresult = (event) => {
    for (let i = event.resultIndex; i < event.results.length; i++) {
      if (event.results[i].isFinal) finalText += event.results[i][0].transcript + " ";
    }
    $("retell").value = finalText.trim();
  };
  recognition.onerror = () => setStatus("识别失败，可打字补充。");
  $("mic").addEventListener("click", () => {
    if (startedAt) {
      recognition.stop();
      stopTimer();
    } else {
      finalText = "";
      $("retell").value = "";
      startTimer();
      recognition.start();
    }
  });
}

HearsayVoice.cloudStatus().then((voice) => {
  if (!(voice.asr && setupCloudMic())) setupBrowserMic();
});
