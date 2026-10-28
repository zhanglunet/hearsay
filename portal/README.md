# 公开门户站（hearsay.fans）

任何人都能打开的介绍页 + 「申请试用」登记。和应用（app.hearsay.fans，受 Cloudflare Access 保护）是两个独立的 Worker，门户流量不会唤醒应用容器。设计见 [docs/superpowers/specs/2026-10-28-public-portal-design.md](../docs/superpowers/specs/2026-10-28-public-portal-design.md)。

| 路径 | 行为 |
|---|---|
| `/` | 门户单页（`public/`） |
| `POST /api/apply` | 登记申请：写 D1 `applications` 表，用 Email Routing 发通知给 zhanglu.net@gmail.com |
| `/listen/` `/shadow/` `/retell/` `/converse/` `/plan/` | 301 跳到 app.hearsay.fans 同一路径（旧书签） |
| `www.hearsay.fans/*` | 301 跳到 hearsay.fans 同一路径 |

申请人主要在中国大陆，Turnstile 可能加载不出来，所以它不挡提交：没拿到或没通过的申请照样登记，`verified = 0`，通知邮件标题带「[未验证]」。另有蜜罐字段和按 IP 限流（每 60 秒 3 次）。

## 命令（在仓库根目录运行）

```bash
# 测试（esbuild 编译后用 Node 跑，不发真实请求）
npm run test:portal

# 本地运行：先建本地表，再起服务（send_email 在本地只写 .eml 文件）
npx wrangler d1 execute hearsay-portal --local --config portal/wrangler.jsonc --file portal/schema.sql
npx wrangler dev --config portal/wrangler.jsonc --port 8790

# 部署
npm run deploy:portal

# 查申请名单
npx wrangler d1 execute hearsay-portal --remote --config portal/wrangler.jsonc \
  --command "SELECT * FROM applications ORDER BY created_at DESC"
```

## 一次性配置

- D1 数据库 `hearsay-portal`（id 写在 `wrangler.jsonc`），表结构见 `schema.sql`。
- hearsay.fans 开通 Email Routing，并在 Destination addresses 里验证 zhanglu.net@gmail.com；否则 `send_email` 发不出去（申请仍会登记）。
- Turnstile 站点（hearsay.fans、www.hearsay.fans，Managed）：site key 写在 `public/index.html` 的 `data-sitekey`；secret 用 `npx wrangler secret put TURNSTILE_SECRET --config portal/wrangler.jsonc` 设置。没设 secret 时所有申请都记为未验证。
