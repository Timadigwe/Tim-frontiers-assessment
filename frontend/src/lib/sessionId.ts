/**
 * Session id = RFC 4122 UUID string (must match backend validation).
 * `crypto.randomUUID` is only available in secure contexts (HTTPS) in some browsers;
 * fall back to a v4-style generator.
 */
export function newSessionId(): string {
  const c = globalThis.crypto;
  if (c && typeof c.randomUUID === "function") {
    return c.randomUUID();
  }
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (ch) => {
    const r = (Math.random() * 16) | 0;
    const v = ch === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}
