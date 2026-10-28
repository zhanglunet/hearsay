// 门户站 Worker 的逻辑测试：假的 D1、限流、通知，不发真实请求。
// 运行：npm run test:portal（先用 esbuild 把 portal/src/*.ts 编译成 ESM，再用 Node 跑）
import assert from "node:assert/strict";
import { pathToFileURL } from "node:url";

const dir = process.argv[2];
const load = (name) => import(pathToFileURL(`${dir}/${name}.js`).href);
const { normalizeEmail, validateNote, verifyTurnstile, handleApply, NOTE_MAX } = await load("apply");

// ---------- 规范化与校验 ----------
assert.equal(normalizeEmail("  Foo@Mail.COM "), "foo@mail.com");
assert.equal(normalizeEmail("not-an-email"), null);
assert.equal(normalizeEmail("a@b"), null);
assert.equal(normalizeEmail("x".repeat(250) + "@a.com"), null);
assert.equal(normalizeEmail(undefined), null);
assert.equal(NOTE_MAX, 200);
assert.deepEqual(validateNote(undefined), { ok: true, note: "" });
assert.deepEqual(validateNote("  练开会  "), { ok: true, note: "练开会" });
assert.equal(validateNote("😀".repeat(200)).ok, true); // 按字符（code point）计数
assert.equal(validateNote("😀".repeat(201)).ok, false);

// ---------- 假依赖 ----------
function fakeDb() {
  const rows = new Map();
  return {
    rows,
    prepare(sql) {
      assert.match(sql, /INSERT OR IGNORE INTO applications/);
      return { bind: (...v) => ({ async run() {
        if (rows.has(v[0])) return { meta: { changes: 0 } };
        rows.set(v[0], { email: v[0], note: v[1], created_at: v[2], country: v[3], verified: v[4] });
        return { meta: { changes: 1 } };
      } }) };
    },
  };
}
function fakeLimiter(max = 3) {
  const counts = new Map();
  const keys = [];
  return {
    keys,
    async limit({ key }) {
      keys.push(key);
      counts.set(key, (counts.get(key) || 0) + 1);
      return { success: counts.get(key) <= max };
    },
  };
}
function makeDeps(over = {}) {
  const sent = [];
  return {
    sent,
    deps: {
      db: fakeDb(),
      limiter: fakeLimiter(),
      verifyTurnstile: async (token) => token === "good",
      notify: async (subject, text) => { sent.push({ subject, text }); },
      now: () => new Date("2026-10-28T08:00:00Z"),
      ...over,
    },
  };
}
function post(body, { ip = "1.2.3.4", country = "CN", raw } = {}) {
  const headers = { "content-type": "application/json" };
  if (ip) headers["cf-connecting-ip"] = ip;
  const req = new Request("https://hearsay.fans/api/apply", {
    method: "POST", headers, body: raw ?? JSON.stringify(body),
  });
  Object.defineProperty(req, "cf", { value: { country } });
  return req;
}
const read = async (res) => ({ status: res.status, body: await res.json() });

// ---------- new application ----------
{
  const { deps, sent } = makeDeps();
  const r = await read(await handleApply(post({ email: "Learner@Example.com", note: "想练开会", token: "good" }), deps));
  assert.deepEqual(r, { status: 200, body: { ok: true } });
  const row = deps.db.rows.get("learner@example.com");
  assert.deepEqual(row, { email: "learner@example.com", note: "想练开会", created_at: "2026-10-28T08:00:00.000Z", country: "CN", verified: 1 });
  assert.equal(sent.length, 1);
  assert.equal(sent[0].subject, "Hearsay 新申请：learner@example.com");
  for (const s of ["learner@example.com", "想练开会", "CN"]) assert.ok(sent[0].text.includes(s), s);

  // duplicate email：大小写不同也算同一个，不覆盖、不再通知
  const d = await read(await handleApply(post({ email: " LEARNER@example.com", note: "别的", token: "good" }), deps));
  assert.deepEqual(d, { status: 200, body: { ok: true } });
  assert.equal(deps.db.rows.size, 1);
  assert.equal(deps.db.rows.get("learner@example.com").note, "想练开会");
  assert.equal(sent.length, 1);
}

// ---------- unverified：Turnstile 没拿到或没通过，仍入库 ----------
{
  const { deps, sent } = makeDeps();
  const r = await read(await handleApply(post({ email: "a@b.cn", token: "" }), deps));
  assert.equal(r.status, 200);
  assert.equal(deps.db.rows.get("a@b.cn").verified, 0);
  assert.ok(sent[0].subject.startsWith("[未验证] "));
  assert.ok(sent[0].text.includes("（未填写）"));
}

// ---------- honeypot ----------
{
  const { deps, sent } = makeDeps();
  const log = console.log; console.log = () => {};
  const r = await read(await handleApply(post({ email: "bot@spam.com", website: "http://x" }), deps));
  console.log = log;
  assert.deepEqual(r, { status: 200, body: { ok: true } });
  assert.equal(deps.db.rows.size, 0);
  assert.equal(sent.length, 0);
}

// ---------- rate limit ----------
{
  const { deps } = makeDeps();
  for (let i = 0; i < 3; i++) {
    assert.equal((await handleApply(post({ email: `u${i}@a.com` }), deps)).status, 200);
  }
  const r = await read(await handleApply(post({ email: "u9@a.com" }), deps));
  assert.deepEqual(r, { status: 429, body: { ok: false, error: "提交太频繁，请稍后再试" } });
  assert.equal(deps.db.rows.has("u9@a.com"), false);
}

// ---------- 邮箱写错不消耗限流额度：先报「邮箱不对」，不是「太频繁」 ----------
{
  const { deps } = makeDeps();
  for (let i = 0; i < 5; i++) {
    const r = await read(await handleApply(post({ email: "a@b" }), deps));
    assert.deepEqual(r, { status: 400, body: { ok: false, error: "请填写正确的邮箱地址" } });
  }
  assert.equal((await handleApply(post({ email: "fixed@b.com" }), deps)).status, 200);
}

// ---------- 蜜罐命中要留日志（真实用户被浏览器自动填充时可追查） ----------
{
  const { deps } = makeDeps();
  const logs = []; const log = console.log; console.log = (m) => logs.push(String(m));
  await handleApply(post({ email: "Real@User.com", website: "x" }), deps);
  console.log = log;
  assert.ok(logs.some((m) => m.includes("honeypot") && m.includes("real@user.com")), logs.join("|"));
}

// ---------- missing ip：没有来访 IP、没有限流绑定都不崩 ----------
{
  const { deps } = makeDeps();
  await handleApply(post({ email: "n@a.com" }, { ip: null }), deps);
  assert.deepEqual(deps.limiter.keys, ["unknown"]);
  const { deps: d2 } = makeDeps({ limiter: undefined });
  assert.equal((await handleApply(post({ email: "m@a.com" }, { ip: null }), d2)).status, 200);
}

// ---------- bad input ----------
{
  const { deps, sent } = makeDeps();
  const e1 = await read(await handleApply(post({ email: "nope" }), deps));
  assert.deepEqual(e1, { status: 400, body: { ok: false, error: "请填写正确的邮箱地址" } });
  const e2 = await read(await handleApply(post({ email: "a@b.com", note: "字".repeat(201) }), deps));
  assert.deepEqual(e2, { status: 400, body: { ok: false, error: "想练什么最多 200 个字" } });
  const e3 = await read(await handleApply(post(null, { raw: "{not json" }), deps));
  assert.deepEqual(e3, { status: 400, body: { ok: false, error: "请求格式不对" } });
  assert.equal(deps.db.rows.size, 0);
  assert.equal(sent.length, 0);
}

// ---------- notify failure：发信失败不影响申请 ----------
{
  const { deps } = makeDeps({ notify: async () => { throw new Error("smtp down"); } });
  const log = console.log; console.log = () => {};
  const r = await read(await handleApply(post({ email: "x@y.com", token: "good" }), deps));
  console.log = log;
  assert.deepEqual(r, { status: 200, body: { ok: true } });
  assert.equal(deps.db.rows.has("x@y.com"), true);
}

// ---------- method ----------
{
  const { deps } = makeDeps();
  assert.equal((await handleApply(new Request("https://hearsay.fans/api/apply"), deps)).status, 405);
}

// ---------- verifyTurnstile ----------
{
  let called = 0;
  const ok = async (url, init) => {
    called++;
    assert.equal(url, "https://challenges.cloudflare.com/turnstile/v0/siteverify");
    const form = init.body;
    assert.equal(form.get("secret"), "sec");
    assert.equal(form.get("response"), "tok");
    assert.equal(form.get("remoteip"), "1.2.3.4");
    return new Response(JSON.stringify({ success: true }));
  };
  assert.equal(await verifyTurnstile("sec", "", "1.2.3.4", ok), false);
  assert.equal(called, 0);
  assert.equal(await verifyTurnstile("sec", "tok", "1.2.3.4", ok), true);
  assert.equal(await verifyTurnstile("sec", "tok", "1.2.3.4", async () => new Response(JSON.stringify({ success: false }))), false);
  assert.equal(await verifyTurnstile("sec", "tok", "1.2.3.4", async () => { throw new Error("blocked"); }), false);
}

// ---------- redirectTarget ----------
{
  const { redirectTarget, APP_ORIGIN, PORTAL_ORIGIN } = await load("routes");
  assert.equal(APP_ORIGIN, "https://app.hearsay.fans");
  assert.equal(PORTAL_ORIGIN, "https://hearsay.fans");
  const t = (u) => redirectTarget(new URL(u));
  assert.equal(t("https://www.hearsay.fans/abc?x=1"), "https://hearsay.fans/abc?x=1");
  assert.equal(t("https://www.hearsay.fans/listen/"), "https://hearsay.fans/listen/");
  assert.equal(t("https://hearsay.fans/listen/"), "https://app.hearsay.fans/listen/");
  assert.equal(t("https://hearsay.fans/plan/api/plan?minutes=15"), "https://app.hearsay.fans/plan/api/plan?minutes=15");
  assert.equal(t("https://hearsay.fans/converse"), "https://app.hearsay.fans/converse");
  for (const p of ["shadow", "retell"]) assert.equal(t(`https://hearsay.fans/${p}/x`), `https://app.hearsay.fans/${p}/x`);
  assert.equal(t("https://hearsay.fans/listening"), null);
  assert.equal(t("https://hearsay.fans/"), null);
  assert.equal(t("https://hearsay.fans/api/apply"), null);
  assert.equal(t("https://hearsay.fans/style.css"), null);
}

// ---------- buildMime ----------
{
  const { buildMime } = await load("mail");
  const text = "邮箱：a@b.com\n想练什么：" + "开会".repeat(60);
  const mime = buildMime("noreply@hearsay.fans", "zhanglu.net@gmail.com",
    "[未验证] Hearsay 新申请：a@b.com", text, new Date("2026-10-28T00:00:00Z"));
  assert.match(mime, /^From: noreply@hearsay\.fans\r\n/m);
  assert.match(mime, /^To: zhanglu\.net@gmail\.com\r\n/m);
  const subj = mime.match(/^Subject: =\?UTF-8\?B\?([A-Za-z0-9+/=]+)\?=\r\n/m);
  assert.ok(subj, "中文标题按 RFC 2047 编码");
  assert.equal(Buffer.from(subj[1], "base64").toString("utf8"), "[未验证] Hearsay 新申请：a@b.com");
  assert.match(mime, /^Date: Wed, 28 Oct 2026 00:00:00 GMT\r\n/m);
  assert.match(mime, /^Message-ID: <[^>\s]+@hearsay\.fans>\r\n/m);
  assert.match(mime, /^MIME-Version: 1\.0\r\n/m);
  assert.match(mime, /Content-Type: text\/plain; charset=UTF-8\r\n/);
  assert.match(mime, /Content-Transfer-Encoding: base64\r\n/);
  const [, bodyPart] = mime.split("\r\n\r\n");
  for (const line of bodyPart.split("\r\n")) assert.ok(line.length <= 76, "正文每行不超过 76 字符");
  assert.equal(Buffer.from(bodyPart.replace(/\r\n/g, ""), "base64").toString("utf8"), text);
}

console.log("portal：全部断言通过");
