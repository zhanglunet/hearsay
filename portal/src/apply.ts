/**
 * 门户站「申请试用」：POST /api/apply，只登记意向，不开通任何东西。
 *
 * 请求体 {email, note, token, website}：
 *   email   必填；note「想练什么」可选，最多 NOTE_MAX 个字
 *   token   Turnstile token。申请人主要在大陆，Turnstile 脚本可能加载不出来，
 *           所以拿不到或校验失败也照样登记，只记 verified = 0、通知邮件标「[未验证]」
 *   website 蜜罐：页面上看不见，被填了就假装成功、不登记不发信
 *
 * 另按来访 IP 限流（IP 只作限流键，不入库）。同一邮箱只记一次、只通知一次。
 * 依赖都从参数传入，便于在 Node 里测试（portal/test/portal.test.mjs）。
 */

export const NOTE_MAX = 200;
const EMAIL_MAX = 254;
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify";

export interface D1Like {
  prepare(sql: string): { bind(...v: unknown[]): { run(): Promise<{ meta: { changes: number } }> } };
}
export interface LimiterLike {
  limit(opts: { key: string }): Promise<{ success: boolean }>;
}
export interface ApplyDeps {
  db: D1Like;
  limiter?: LimiterLike;
  verifyTurnstile(token: string, ip: string): Promise<boolean>;
  notify(subject: string, text: string): Promise<void>;
  now(): Date;
}

function reply(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" },
  });
}
const fail = (status: number, error: string) => reply(status, { ok: false, error });

export function normalizeEmail(raw: unknown): string | null {
  if (typeof raw !== "string") return null;
  const email = raw.trim().toLowerCase();
  return email.length <= EMAIL_MAX && EMAIL_RE.test(email) ? email : null;
}

export function validateNote(raw: unknown): { ok: true; note: string } | { ok: false; error: string } {
  const note = typeof raw === "string" ? raw.trim() : "";
  // 按字符（code point）数，emoji 算一个字
  return [...note].length <= NOTE_MAX ? { ok: true, note } : { ok: false, error: `想练什么最多 ${NOTE_MAX} 个字` };
}

export async function verifyTurnstile(
  secret: string, token: string, ip: string, fetchFn: typeof fetch = fetch,
): Promise<boolean> {
  if (!token) return false;
  try {
    const body = new FormData();
    body.append("secret", secret);
    body.append("response", token);
    body.append("remoteip", ip);
    const r = await fetchFn(TURNSTILE_VERIFY_URL, { method: "POST", body, signal: AbortSignal.timeout(5000) });
    const result = (await r.json()) as { success?: boolean };
    return result.success === true;
  } catch {
    return false;
  }
}

export async function handleApply(request: Request, deps: ApplyDeps): Promise<Response> {
  if (request.method !== "POST") return fail(405, "只支持 POST");
  let body: Record<string, unknown>;
  try {
    body = await request.json();
    if (!body || typeof body !== "object") throw new Error("not an object");
  } catch {
    return fail(400, "请求格式不对");
  }
  if (typeof body.website === "string" && body.website.trim()) return reply(200, { ok: true });

  const ip = request.headers.get("cf-connecting-ip") || "unknown";
  if (deps.limiter && !(await deps.limiter.limit({ key: ip })).success) {
    return fail(429, "提交太频繁，请稍后再试");
  }

  const email = normalizeEmail(body.email);
  if (!email) return fail(400, "请填写正确的邮箱地址");
  const noteCheck = validateNote(body.note);
  if (!noteCheck.ok) return fail(400, noteCheck.error);
  const note = noteCheck.note;

  const verified = await deps.verifyTurnstile(typeof body.token === "string" ? body.token : "", ip);
  const country = String((request as { cf?: { country?: string } }).cf?.country ?? "");
  const createdAt = deps.now().toISOString();
  const result = await deps.db
    .prepare("INSERT OR IGNORE INTO applications (email, note, created_at, country, verified) VALUES (?1, ?2, ?3, ?4, ?5)")
    .bind(email, note, createdAt, country, verified ? 1 : 0)
    .run();

  if (result.meta.changes === 1) {
    const subject = `${verified ? "" : "[未验证] "}Hearsay 新申请：${email}`;
    const text = [
      `邮箱：${email}`,
      `想练什么：${note || "（未填写）"}`,
      `国家：${country || "未知"}`,
      `时间：${createdAt}`,
      `人机验证：${verified ? "通过" : "未通过或没加载出来"}`,
    ].join("\n");
    try {
      await deps.notify(subject, text);
    } catch (err) {
      console.log(`apply notify failed: ${err instanceof Error ? err.message : String(err)}`);
    }
  }
  return reply(200, { ok: true });
}
