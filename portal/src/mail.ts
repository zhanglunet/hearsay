/**
 * 拼通知邮件的 MIME 原文（Email Routing 的 send_email 绑定要求原始邮件）。
 * 中文标题按 RFC 2047 编码，正文 UTF-8 + base64（每行 76 字符）。不引第三方库。
 */
function utf8Base64(text: string): string {
  let binary = "";
  for (const byte of new TextEncoder().encode(text)) binary += String.fromCharCode(byte);
  return btoa(binary);
}

export function buildMime(from: string, to: string, subject: string, text: string, date: Date): string {
  const body = utf8Base64(text).replace(/.{1,76}/g, "$&\r\n").trimEnd();
  return [
    `From: ${from}`,
    `To: ${to}`,
    `Subject: =?UTF-8?B?${utf8Base64(subject)}?=`,
    `Date: ${date.toUTCString()}`,
    `Message-ID: <${crypto.randomUUID()}@hearsay.fans>`,
    "MIME-Version: 1.0",
    "Content-Type: text/plain; charset=UTF-8",
    "Content-Transfer-Encoding: base64",
    "",
    body,
  ].join("\r\n");
}
