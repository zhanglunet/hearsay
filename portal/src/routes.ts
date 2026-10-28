/**
 * 门户站的跳转规则：
 *   www.hearsay.fans/*        → hearsay.fans/*（同路径）
 *   hearsay.fans/<应用路径>/* → app.hearsay.fans/<应用路径>/*（应用搬家前的旧书签不失效）
 */
export const APP_ORIGIN = "https://app.hearsay.fans";
export const PORTAL_ORIGIN = "https://hearsay.fans";

const APP_PATH_RE = /^\/(listen|shadow|retell|converse|plan)(\/|$)/;

export function redirectTarget(url: URL): string | null {
  if (url.hostname === "www.hearsay.fans") return PORTAL_ORIGIN + url.pathname + url.search;
  if (APP_PATH_RE.test(url.pathname)) return APP_ORIGIN + url.pathname + url.search;
  return null;
}
