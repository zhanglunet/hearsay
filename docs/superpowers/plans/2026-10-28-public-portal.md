# 公开门户站 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** hearsay.fans 变成任何人可打开的门户站（介绍 + 申请试用登记），应用搬到 app.hearsay.fans 继续受 Access 保护。

**Architecture:** 新建独立 Worker `hearsay-portal`（目录 `portal/`）：Workers 静态资源托管单页，`POST /api/apply` 写 D1 并通过 Email Routing 的 `send_email` 绑定通知作者；Turnstile 只作加分项，加载失败也能提交，另有蜜罐和按 IP 限流。现有应用 Worker `hearsay` 只改 `routes`。

**Tech Stack:** Cloudflare Workers（TypeScript）、Workers Static Assets、D1、Email Routing `send_email`、Rate Limiting 绑定、Turnstile；测试沿用仓库做法：esbuild 编译成 ESM，再用 Node `node:assert` 跑。

**Spec:** `docs/superpowers/specs/2026-10-28-public-portal-design.md`

## Global Constraints

- 所有页面文案、错误信息、通知邮件用简体中文。
- 应用在任何时刻都不能出现在不受 Access 保护的地址上（迁移按 Task 5 的顺序，一步一检查）。
- 门户的任何请求都不能唤醒应用容器：门户是独立 Worker，不绑定 `HEARSAY` Durable Object。
- 申请表单只有：邮箱（必填）、想练什么（可选，最多 200 字）；手机 375px 下无横向滚动，按钮和输入框高度 ≥ 44px。
- 页面除 Turnstile（`https://challenges.cloudflare.com/turnstile/v0/api.js`）外不引用任何外部资源（字体、CDN 脚本、图片）。
- 不存 IP；IP 只用作限流键。
- 发件人 `noreply@hearsay.fans`，收件人写死为 `zhanglu.net@gmail.com`。
- 配色 `#0c5c5c`，字体 system-ui，无前端框架。
- 部署全部在本机手动 `npx wrangler deploy`（门户用 `--config portal/wrangler.jsonc`）。
- 提交信息结尾：`Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`。

## Review Focus

- 手机上连点两次「提交」：按钮提交期间禁用；服务端同邮箱也只记一次、只发一封信。→ Task 1 `duplicate email` 测试 + Task 3 手动检查。
- 邮箱前后有空格或大写（`  Foo@Mail.COM `）：视为同一邮箱 `foo@mail.com`。→ Task 1 `normalizeEmail` 测试。
- 「想练什么」含 emoji 或中英混排：按字符（code point）计数，200 个 emoji 也合法，201 个拒绝。→ Task 1 `validateNote` 测试。
- 本地或异常请求没有 `CF-Connecting-IP`、限流绑定不存在：不崩溃，限流键退回 `"unknown"`。→ Task 1 `missing ip` 测试。
- 通知邮件发送抛错：申请仍返回成功、记录已入库。→ Task 1 `notify failure` 测试。

---

## 文件结构

| 文件 | 职责 |
|---|---|
| `portal/wrangler.jsonc` | 门户 Worker 配置：assets、D1、send_email、ratelimits、routes |
| `portal/schema.sql` | D1 建表 |
| `portal/src/apply.ts` | 申请处理：规范化、校验、蜜罐、限流、Turnstile 校验、入库、通知（依赖注入，可在 Node 测） |
| `portal/src/routes.ts` | 纯函数：www 和应用旧路径的跳转目标 |
| `portal/src/mail.ts` | 纯函数：拼 UTF-8 MIME 原文 |
| `portal/src/index.ts` | 入口：组装真实依赖（`cloudflare:email`、fetch、D1、限流），分发请求 |
| `portal/public/index.html`、`style.css`、`app.js`、`favicon.svg` | 门户单页 |
| `portal/test/portal.test.mjs` | Node 测试 |
| `portal/README.md` | 门户部署与查名单的命令 |
| `package.json` | 新增 `test:portal`、`deploy:portal` |
| `wrangler.jsonc` | 应用路由改为 app.hearsay.fans |
| `docs/ops/cloudflare-deploy.md`、`README.md` | 地址与门户说明 |

---

### Task 1: 申请处理逻辑 `apply.ts`

**Files:**
- Create: `portal/src/apply.ts`、`portal/test/portal.test.mjs`、`portal/schema.sql`
- Modify: `package.json`（scripts）

**Interfaces:**
- Produces（`portal/src/apply.ts`）：
  ```ts
  export const NOTE_MAX = 200;
  export interface D1Like { prepare(sql: string): { bind(...v: unknown[]): { run(): Promise<{ meta: { changes: number } }> } } }
  export interface LimiterLike { limit(opts: { key: string }): Promise<{ success: boolean }> }
  export interface ApplyDeps {
    db: D1Like;
    limiter?: LimiterLike;
    verifyTurnstile(token: string, ip: string): Promise<boolean>;
    notify(subject: string, text: string): Promise<void>;
    now(): Date;
  }
  export function normalizeEmail(raw: unknown): string | null;
  export function validateNote(raw: unknown): { ok: true; note: string } | { ok: false; error: string };
  export function verifyTurnstile(secret: string, token: string, ip: string, fetchFn?: typeof fetch): Promise<boolean>;
  export function handleApply(request: Request, deps: ApplyDeps): Promise<Response>;
  ```
- 请求体 JSON：`{ email, note, token, website }`（`website` 是蜜罐）。
- 响应 JSON：成功 `200 {"ok":true}`；校验失败 `400 {"ok":false,"error":"…"}`；限流 `429 {"ok":false,"error":"提交太频繁，请稍后再试"}`；非 POST `405`。

- [ ] **Step 1: 建表 `portal/schema.sql`**

```sql
CREATE TABLE IF NOT EXISTS applications (
  email TEXT PRIMARY KEY,
  note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  country TEXT NOT NULL DEFAULT '',
  verified INTEGER NOT NULL DEFAULT 0
);
```

- [ ] **Step 2: 加脚本到 `package.json`**

```json
"test:portal": "esbuild portal/src/apply.ts --format=esm --platform=neutral --outdir=.wrangler/portal-test --log-level=warning && node portal/test/portal.test.mjs .wrangler/portal-test",
"deploy:portal": "wrangler deploy --config portal/wrangler.jsonc"
```

测试文件按目录参数 `import` 各模块（`${dir}/apply.js`），全部通过时打印 `portal：全部断言通过`。Task 2 再把 `portal/src/routes.ts portal/src/mail.ts` 加进 esbuild 入口。

- [ ] **Step 3: 写失败的测试 `portal/test/portal.test.mjs`（apply 部分）**

测试用假 D1（内存 Map，`INSERT OR IGNORE` 语义：已有返回 `changes: 0`）、假限流（计数，第 4 次起 `success:false`）、记录 `notify` 调用。断言：

```js
// normalizeEmail
assert.equal(normalizeEmail("  Foo@Mail.COM "), "foo@mail.com");
assert.equal(normalizeEmail("not-an-email"), null);
assert.equal(normalizeEmail("a@b"), null);           // 必须有点号后缀
assert.equal(normalizeEmail("x".repeat(250) + "@a.com"), null); // 总长 > 254
// validateNote：按 code point 计数
assert.deepEqual(validateNote(undefined), { ok: true, note: "" });
assert.equal(validateNote("😀".repeat(200)).ok, true);
assert.equal(validateNote("😀".repeat(201)).ok, false);
// new application：入库 1 条、verified=1、notify 1 次，标题不含「[未验证]」，正文含邮箱、note、国家
// duplicate email：同邮箱（大小写不同）再提交 → 200 ok，库里仍 1 条且 note 是第一次的，notify 仍 1 次
// unverified：verifyTurnstile 返回 false → 200 ok，verified=0，标题以「[未验证] 」开头
// honeypot：website 非空 → 200 ok，不入库，不 notify
// rate limit：同 IP 第 4 次 → 429，error === "提交太频繁，请稍后再试"
// missing ip：无 CF-Connecting-IP 且 limiter 为 undefined → 200 ok（不抛错），限流键为 "unknown"（用假 limiter 断言收到的 key）
// bad input：邮箱非法 → 400，error 为中文；note 超长 → 400；body 不是 JSON → 400 "请求格式不对"
// notify failure：notify 抛错 → 200 ok，记录已入库
// method：GET → 405
// verifyTurnstile(secret, "", ip, fakeFetch) → false 且不调用 fetch；fakeFetch 返回 {success:true} → true；fakeFetch 抛错 → false
```

- [ ] **Step 4: 运行，确认失败**

Run: `npm run test:portal`
Expected: FAIL（`apply.ts` 未实现）

- [ ] **Step 5: 实现 `portal/src/apply.ts`**

要点：
- 校验顺序：方法 → JSON 解析 → 蜜罐（非空直接 `200 ok`）→ 限流（键 `CF-Connecting-IP` 或 `"unknown"`；`limiter` 缺省时跳过）→ 邮箱 → note → Turnstile → 入库 → 若 `changes === 1` 才 notify（`try/catch`，失败只 `console.log`）。
- 邮箱正则：`/^[^\s@]+@[^\s@]+\.[^\s@]+$/`，规范化为 `trim().toLowerCase()`，长度 ≤ 254。
- 错误文案：邮箱「请填写正确的邮箱地址」；note「想练什么最多 200 个字」。
- 入库：`INSERT OR IGNORE INTO applications (email, note, created_at, country, verified) VALUES (?1, ?2, ?3, ?4, ?5)`；`country` 取 `(request as any).cf?.country ?? ""`；`created_at` 用 `deps.now().toISOString()`。
- 通知标题：`${verified ? "" : "[未验证] "}Hearsay 新申请：${email}`；正文逐行：邮箱、想练什么（空时写「（未填写）」）、国家、时间、是否通过人机验证。
- `verifyTurnstile`：token 为空直接 `false`；POST `https://challenges.cloudflare.com/turnstile/v0/siteverify`，表单字段 `secret`、`response`、`remoteip`；用 `AbortSignal.timeout(5000)`；任何异常返回 `false`。

- [ ] **Step 6: 运行，确认通过**

Run: `npm run test:portal`
Expected: 输出 `portal：全部断言通过`

- [ ] **Step 7: 提交**

```bash
git add portal/src/apply.ts portal/test/portal.test.mjs portal/schema.sql package.json
git commit -m "门户：申请处理逻辑（校验、蜜罐、限流、Turnstile 降级、去重、通知）"
```

---

### Task 2: 路由、邮件与 Worker 入口

**Files:**
- Create: `portal/src/routes.ts`、`portal/src/mail.ts`、`portal/src/index.ts`、`portal/wrangler.jsonc`
- Modify: `portal/test/portal.test.mjs`（追加）

**Interfaces:**
- Consumes: Task 1 的 `handleApply`、`verifyTurnstile`、`ApplyDeps`。
- Produces:
  ```ts
  // routes.ts
  export const APP_ORIGIN = "https://app.hearsay.fans";
  export const PORTAL_ORIGIN = "https://hearsay.fans";
  export function redirectTarget(url: URL): string | null;
  // mail.ts
  export function buildMime(from: string, to: string, subject: string, text: string, date: Date): string;
  ```
- `index.ts` 的 `Env`：`ASSETS: Fetcher; DB: D1Database; NOTIFY: SendEmail; APPLY_LIMITER: RateLimit; TURNSTILE_SECRET?: string`。

- [ ] **Step 1: 把 `routes.ts`、`mail.ts` 加进 `test:portal` 的 esbuild 入口，并追加失败的测试**

```js
// redirectTarget
assert.equal(redirectTarget(new URL("https://www.hearsay.fans/abc?x=1")), "https://hearsay.fans/abc?x=1");
assert.equal(redirectTarget(new URL("https://hearsay.fans/listen/")), "https://app.hearsay.fans/listen/");
assert.equal(redirectTarget(new URL("https://hearsay.fans/plan/api/plan?minutes=15")), "https://app.hearsay.fans/plan/api/plan?minutes=15");
assert.equal(redirectTarget(new URL("https://hearsay.fans/converse")), "https://app.hearsay.fans/converse");
assert.equal(redirectTarget(new URL("https://hearsay.fans/listening")), null);   // 只匹配整段
assert.equal(redirectTarget(new URL("https://hearsay.fans/")), null);
assert.equal(redirectTarget(new URL("https://hearsay.fans/api/apply")), null);
// buildMime
const mime = buildMime("noreply@hearsay.fans", "zhanglu.net@gmail.com", "[未验证] Hearsay 新申请：a@b.com", "邮箱：a@b.com", new Date("2026-10-28T00:00:00Z"));
assert.match(mime, /^From: noreply@hearsay\.fans\r\n/m);
assert.match(mime, /^Subject: =\?UTF-8\?B\?[A-Za-z0-9+/=]+\?=\r\n/m);   // 中文标题 RFC 2047 编码
assert.match(mime, /Content-Type: text\/plain; charset=UTF-8/);
assert.match(mime, /Content-Transfer-Encoding: base64/);
assert.match(mime, /^Message-ID: <[^>]+@hearsay\.fans>/m);
// 正文 base64 解码后等于原文
```

- [ ] **Step 2: 运行，确认失败**

Run: `npm run test:portal` → FAIL（`redirectTarget` / `buildMime` 未定义）

- [ ] **Step 3: 实现 `routes.ts`、`mail.ts`**

- `redirectTarget`：主机名 `www.hearsay.fans` → `PORTAL_ORIGIN + pathname + search`；路径匹配 `/^\/(listen|shadow|retell|converse|plan)(\/|$)/` → `APP_ORIGIN + pathname + search`；其余 `null`。
- `buildMime`：头部 `From`、`To`、`Subject`（`=?UTF-8?B?…?=`）、`Date`（`toUTCString()`）、`Message-ID`（`<随机 UUID@hearsay.fans>`）、`MIME-Version: 1.0`、`Content-Type: text/plain; charset=UTF-8`、`Content-Transfer-Encoding: base64`；行尾 `\r\n`；正文 UTF-8 → base64，每 76 字符换行。不引入第三方库。

- [ ] **Step 4: 运行，确认通过**

Run: `npm run test:portal` → `portal：全部断言通过`

- [ ] **Step 5: 实现 `portal/src/index.ts`**

`fetch(request, env)`：
1. `redirectTarget(url)` 非空 → `Response.redirect(target, 301)`。
2. `pathname === "/api/apply"` → `handleApply(request, deps)`，`deps.notify` 用 `new EmailMessage("noreply@hearsay.fans", "zhanglu.net@gmail.com", buildMime(...))` 交给 `env.NOTIFY.send`（`import { EmailMessage } from "cloudflare:email"`）；`deps.verifyTurnstile` 用 `env.TURNSTILE_SECRET`（未设置时返回 `false`）。
3. 其余 → `env.ASSETS.fetch(request)`。

- [ ] **Step 6: 写 `portal/wrangler.jsonc`**

```jsonc
{
  "$schema": "../node_modules/wrangler/config-schema.json",
  "name": "hearsay-portal",
  "main": "src/index.ts",
  "compatibility_date": "2026-10-01",
  "observability": { "enabled": true },
  "workers_dev": false,
  "assets": { "directory": "./public", "binding": "ASSETS", "run_worker_first": true },
  "d1_databases": [{ "binding": "DB", "database_name": "hearsay-portal", "database_id": "<Task 4 填>" }],
  "send_email": [{ "name": "NOTIFY", "destination_address": "zhanglu.net@gmail.com" }],
  "ratelimits": [{ "name": "APPLY_LIMITER", "namespace_id": "1001", "simple": { "limit": 3, "period": 60 } }],
  "routes": []   // Task 5 第 4 步才填 hearsay.fans、www.hearsay.fans
}
```

- [ ] **Step 7: 验证编译**

Run: `npx wrangler deploy --config portal/wrangler.jsonc --dry-run --outdir .wrangler/portal-dry-run`
Expected: 无报错，列出 `env.DB`、`env.NOTIFY`、`env.APPLY_LIMITER`、`env.ASSETS` 绑定。（`database_id` 占位时 dry-run 仍可通过；若报错，先做 Task 4 第 1 步再回来。）

- [ ] **Step 8: 提交**

```bash
git add portal/src portal/test portal/wrangler.jsonc
git commit -m "门户：旧地址跳转、通知邮件、Worker 入口与配置"
```

---

### Task 3: 门户页面

**Files:**
- Create: `portal/public/index.html`、`portal/public/style.css`、`portal/public/app.js`、`portal/public/favicon.svg`

**Interfaces:**
- Consumes: `POST /api/apply`，请求/响应格式见 Task 1。
- Turnstile site key 写在 `index.html` 表单容器的 `data-sitekey` 上；开发时用官方测试 key `1x00000000000000000000AA`（总是通过），Task 4 换成正式 key。

- [ ] **Step 1: 写 `index.html`**（结构照设计文档第 3 节布局 B）

1. 顶栏：左「HEARSAY · 听说」，右「登录」链接 → `https://app.hearsay.fans/`。
2. 首屏：`<h1>听得懂，说得出</h1>`；一句定位（与多邻国对比，素材取 README 第一节）；按钮「申请试用 ↓」（`href="#apply"`，CSS `scroll-behavior: smooth`）。
3. 「一条循环」：听 / 跟读 / 复述 / 对话 四张卡片，每张一句说明（素材取 README 第二节第 2 点）。
4. 理念三条：说错的话变成复习并在新对话里再用；进度是「能做什么」不是宝石；针对中文母语者的常见难点。
5. `<section id="apply">` 表单：邮箱（`type="email"`、`autocomplete="email"`、`inputmode="email"`、必填）、「想练什么（可选）」（`maxlength="200"`）、蜜罐 `<input name="website" tabindex="-1" autocomplete="off">` 放在 `aria-hidden` 且移出视口的容器里、Turnstile 容器、提交按钮；下方小字「只用于开放时通知你，不会用于其他用途。」；结果区 `role="status"`。
6. `<head>`：`viewport`、`<title>Hearsay · 听说</title>`、`description` 与 Open Graph（`og:title`、`og:description`）、`favicon.svg`；Turnstile 脚本 `https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit` 用 `async defer`。

- [ ] **Step 2: 写 `style.css`**：配色 `#0c5c5c`、system-ui；`max-width: 720px` 居中；`@media (max-width: 640px)` 下按钮、输入框 `min-height: 44px; font-size: 1rem`（16px，避免 iOS 聚焦时放大）；四张卡片窄屏 2×2。

- [ ] **Step 3: 写 `app.js`**

- 页面加载时若 `window.turnstile` 可用就 `turnstile.render` 到容器；token 存变量。
- 提交：`preventDefault` → 按钮禁用并显示「提交中…」→ 若还没 token，最多等 5000ms（轮询或 Promise.race），超时用空 token → `fetch("/api/apply", {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({email, note, token, website})})`。
- `ok` → 隐藏表单，结果区显示「已登记，开放时会发邮件通知你。」；否则显示服务端 `error`，按钮恢复；网络错误显示「网络不稳定，请稍后再试」。

- [ ] **Step 4: 本地运行并在手机宽度检查**

```bash
npx wrangler d1 execute hearsay-portal --local --config portal/wrangler.jsonc --file portal/schema.sql
npx wrangler dev --config portal/wrangler.jsonc --port 8790
```

用内置浏览器打开 `http://127.0.0.1:8790/`，设视口 375×812，检查并记录：
- `document.documentElement.scrollWidth === 375`（无横向滚动）；首屏可见标语和「申请试用 ↓」。
- 所有可见按钮、输入框 `getBoundingClientRect().height >= 44`。
- 提交新邮箱 → 显示「已登记…」；连点两次提交只发出一次请求。
- 在 DevTools 网络里屏蔽 `challenges.cloudflare.com` 后刷新提交 → 约 5 秒后仍显示「已登记…」。
- `http://127.0.0.1:8790/listen/` 返回 301 到 `https://app.hearsay.fans/listen/`。
- 页面网络请求里除 Turnstile 外没有其他外部域名。

- [ ] **Step 5: 提交**

```bash
git add portal/public
git commit -m "门户：单页介绍与申请表单（手机优先，Turnstile 可降级）"
```

---

### Task 4: Cloudflare 资源与作者手动步骤

**Files:**
- Modify: `portal/wrangler.jsonc`（填 `database_id`）、`portal/public/index.html`（正式 site key）
- Create: `portal/README.md`

- [ ] **Step 1: 建 D1 并建表**

```bash
npx wrangler d1 create hearsay-portal
npx wrangler d1 execute hearsay-portal --remote --config portal/wrangler.jsonc --file portal/schema.sql
```

把返回的 `database_id` 写进 `portal/wrangler.jsonc`。

- [ ] **Step 2: 请作者完成（停下等确认）**
  - Cloudflare 后台 hearsay.fans → Email → Email Routing：开通（自动加 MX/TXT），在 Destination addresses 添加 `zhanglu.net@gmail.com` 并去 Gmail 点确认链接。
  - Turnstile → 新建站点，域名 `hearsay.fans`、`www.hearsay.fans`，模式 Managed；把 site key 告诉 Claude，secret 由作者执行：`npx wrangler secret put TURNSTILE_SECRET --config portal/wrangler.jsonc`。

- [ ] **Step 3: 填正式 site key**，写 `portal/README.md`：部署命令、建表命令、查名单命令 `npx wrangler d1 execute hearsay-portal --remote --config portal/wrangler.jsonc --command "SELECT * FROM applications ORDER BY created_at DESC"`。

- [ ] **Step 4: 首次部署门户（尚无 routes，不对外）**

Run: `npm run deploy:portal`
Expected: 部署成功；因为 `workers_dev: false` 且 `routes` 为空，暂时没有可访问地址。

- [ ] **Step 5: 提交**

```bash
git add portal/wrangler.jsonc portal/public/index.html portal/README.md
git commit -m "门户：D1、Turnstile 正式配置与运维说明"
```

---

### Task 5: 地址迁移与上线验收

**Files:**
- Modify: `wrangler.jsonc`（应用 routes）、`portal/wrangler.jsonc`（门户 routes）、`docs/ops/cloudflare-deploy.md`、`README.md`、`prototype/home/web/index.html`（若有指向 hearsay.fans 的绝对链接）

严格按顺序，每步检查通过才做下一步；任一步失败立即停下报告，不要跳步。

- [ ] **Step 1: Access 应用加 app.hearsay.fans**（Claude in Chrome 操作 Zero Trust，登录由作者处理）：在「hearsay 听说练习」的 Public hostnames 里**新增** `app.hearsay.fans`，不删旧的。

- [ ] **Step 2: 应用路由加 app.hearsay.fans**：`wrangler.jsonc` `routes` 追加 `{ "pattern": "app.hearsay.fans", "custom_domain": true }`，`npx wrangler deploy`。
  检查：`curl -sI https://app.hearsay.fans/ | head -1` 为 302，`location` 指向 `*.cloudflareaccess.com`。

- [ ] **Step 3: 应用路由去掉 hearsay.fans、www.hearsay.fans**：`routes` 只留 `app.hearsay.fans`，`npx wrangler deploy`。
  检查：app.hearsay.fans 仍 302 到 Access；`hearsay.zhanglu-net.workers.dev` 仍 302 到 Access。

- [ ] **Step 4: 门户绑定 hearsay.fans、www.hearsay.fans**：`portal/wrangler.jsonc` `routes` 填 `[{ "pattern": "hearsay.fans", "custom_domain": true }, { "pattern": "www.hearsay.fans", "custom_domain": true }]`，`npm run deploy:portal`。

- [ ] **Step 5: Access 应用去掉 hearsay.fans、www.hearsay.fans**（浏览器操作）。
  检查（不带登录 cookie 的 `curl`）：
  - `curl -sI https://hearsay.fans/` → 200，`content-type: text/html`。
  - `curl -sI https://www.hearsay.fans/x` → 301 到 `https://hearsay.fans/x`。
  - `curl -sI https://hearsay.fans/listen/` → 301 到 `https://app.hearsay.fans/listen/`。
  - `curl -sI https://app.hearsay.fans/` → 302 到 Access。

- [ ] **Step 6: 线上申请验收**（用 Claude in Chrome，作者已登录也不影响门户）
  - 375px 宽度下重复 Task 3 Step 4 的尺寸检查。
  - 用 `zhanglu.net+portal-test@gmail.com` 提交一次 → 页面成功；`wrangler d1 execute … --command "SELECT * FROM applications"` 有这条且 `verified = 1`；请作者确认 Gmail 收到通知。
  - 同邮箱再提交 → 成功提示，表里仍一条，不再收到邮件。
  - 屏蔽 Turnstile 提交另一个测试邮箱 → 记录 `verified = 0`，邮件标题带「[未验证]」。
  - 验收后删除测试记录：`DELETE FROM applications WHERE email LIKE 'zhanglu.net+%'`。
  - 应用容器日志在门户测试期间没有新的启动：`npx wrangler tail hearsay` 期间访问门户无输出。
  - 请作者用手机流量（大陆网络）打开 hearsay.fans 提交一次，30 秒内完成。

- [ ] **Step 7: 更新文档**：`docs/ops/cloudflare-deploy.md` 里应用地址改为 app.hearsay.fans，新增「门户站」一节（指向 `portal/README.md`）；`README.md` 状态行和链接改为：门户 hearsay.fans、应用 app.hearsay.fans。

- [ ] **Step 8: 提交并开 PR**

```bash
git add wrangler.jsonc portal/wrangler.jsonc docs/ops/cloudflare-deploy.md README.md
git commit -m "应用迁到 app.hearsay.fans，hearsay.fans 改为公开门户站"
```

开 PR 后等 CI 通过，**合并前先问作者**。
