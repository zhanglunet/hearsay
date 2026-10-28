/**
 * Hearsay 公开门户站（hearsay.fans、www.hearsay.fans）的入口 Worker。
 *
 * 和应用 Worker（../worker/index.ts，app.hearsay.fans，受 Cloudflare Access 保护）完全分开：
 * 这里不绑定应用的 Durable Object，门户流量不会唤醒应用容器。
 *
 *   www 和应用旧路径 → 301 跳转（src/routes.ts）
 *   POST /api/apply   → 申请登记（src/apply.ts），写 D1，邮件通知作者
 *   其余              → public/ 下的静态页面
 */
import { EmailMessage } from "cloudflare:email";
import { handleApply, verifyTurnstile } from "./apply";
import { buildMime } from "./mail";
import { redirectTarget } from "./routes";

const NOTIFY_FROM = "noreply@hearsay.fans";
const NOTIFY_TO = "zhanglu.net@gmail.com"; // 与 wrangler.jsonc 里 send_email 的 destination_address 一致

interface Env {
  ASSETS: Fetcher;
  DB: D1Database;
  NOTIFY: SendEmail;
  APPLY_LIMITER: RateLimit;
  // wrangler secret put TURNSTILE_SECRET（不写进仓库）
  TURNSTILE_SECRET?: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const target = redirectTarget(url);
    if (target) return Response.redirect(target, 301);

    if (url.pathname === "/api/apply") {
      return handleApply(request, {
        db: env.DB,
        limiter: env.APPLY_LIMITER,
        verifyTurnstile: (token, ip) =>
          env.TURNSTILE_SECRET ? verifyTurnstile(env.TURNSTILE_SECRET, token, ip) : Promise.resolve(false),
        notify: (subject, text) =>
          env.NOTIFY.send(new EmailMessage(NOTIFY_FROM, NOTIFY_TO, buildMime(NOTIFY_FROM, NOTIFY_TO, subject, text, new Date()))),
        now: () => new Date(),
      });
    }
    return env.ASSETS.fetch(request);
  },
};
