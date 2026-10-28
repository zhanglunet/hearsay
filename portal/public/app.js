"use strict";
/*
 * 申请表单。申请人主要在大陆，Turnstile 脚本可能加载慢或加载不出来：
 * 提交时最多等 TOKEN_WAIT_MS 拿 token，拿不到也照样提交（服务端记为未验证）。
 */
(function () {
  const TOKEN_WAIT_MS = 5000;
  const $ = (id) => document.getElementById(id);
  const form = $("apply-form");
  const button = $("submit");
  const result = $("result");
  let token = "";
  let rendered = false;

  function renderTurnstile() {
    if (rendered || !window.turnstile) return;
    rendered = true;
    const box = $("turnstile");
    try {
      window.turnstile.render(box, {
        sitekey: box.dataset.sitekey,
        callback: (t) => { token = t; },
        "expired-callback": () => { token = ""; },
        "error-callback": () => { token = ""; },
      });
    } catch (_err) { /* 渲染失败就不带 token 提交 */ }
  }

  // 脚本是 async 加载的，轮询到它出现为止（最多 15 秒）
  const started = Date.now();
  const poll = setInterval(() => {
    renderTurnstile();
    if (rendered || Date.now() - started > 15000) clearInterval(poll);
  }, 300);

  function waitForToken() {
    if (token) return Promise.resolve(token);
    return new Promise((resolve) => {
      const deadline = Date.now() + TOKEN_WAIT_MS;
      const timer = setInterval(() => {
        if (token || Date.now() > deadline) { clearInterval(timer); resolve(token); }
      }, 200);
    });
  }

  function show(text, isError) {
    result.textContent = text;
    result.classList.toggle("error", Boolean(isError));
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (button.disabled) return;
    const email = $("email").value.trim();
    if (!email || !$("email").checkValidity()) { show("请填写正确的邮箱地址", true); $("email").focus(); return; }
    button.disabled = true;
    button.textContent = "提交中…";
    show("", false);
    try {
      const response = await fetch("/api/apply", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email,
          note: $("note").value,
          token: await waitForToken(),
          website: $("website").value,
        }),
      });
      const payload = await response.json().catch(() => ({}));
      if (response.ok && payload.ok) {
        form.hidden = true;
        show("已登记，开放时会发邮件通知你。", false);
        return;
      }
      show(payload.error || "提交失败，请稍后再试", true);
    } catch (_err) {
      show("网络不稳定，请稍后再试", true);
    }
    button.disabled = false;
    button.textContent = "提交申请";
    if (window.turnstile && rendered) { token = ""; try { window.turnstile.reset($("turnstile")); } catch (_e) { /* 忽略 */ } }
  });
})();
