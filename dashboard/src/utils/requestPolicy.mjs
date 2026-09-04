/**
 * Resolve a browser request target without accepting a browser-global default.
 *
 * @param {RequestInfo | URL} input Request target.
 * @param {string} baseOrigin Origin used for relative targets.
 * @returns {URL | null} The resolved URL, or null for invalid input.
 */
export function resolveRequestUrl(input, baseOrigin) {
  try {
    if (input instanceof URL) return new URL(input.href);
    if (typeof Request !== "undefined" && input instanceof Request) {
      return new URL(input.url, baseOrigin);
    }
    return new URL(String(input), baseOrigin);
  } catch {
    return null;
  }
}

/**
 * Check whether a request remains on the Dashboard origin.
 *
 * @param {RequestInfo | URL} input Request target.
 * @param {string} baseOrigin Dashboard origin.
 * @returns {boolean} Whether the target is same-origin.
 */
export function isSameOriginRequest(input, baseOrigin) {
  const target = resolveRequestUrl(input, baseOrigin);
  if (!target) return false;
  try {
    return target.origin === new URL(baseOrigin).origin;
  } catch {
    return false;
  }
}

/**
 * Normalize an untrusted link for opening in a new browser context.
 *
 * Relative links and all schemes other than HTTP(S) are intentionally rejected.
 *
 * @param {unknown} value Untrusted URL value.
 * @returns {string | null} A safe absolute HTTP(S) URL, or null.
 */
export function normalizeExternalHttpUrl(value) {
  if (typeof value !== "string" || !value.trim()) return null;
  const target = resolveRequestUrl(value.trim(), "https://invalid.example");
  if (!target || !["http:", "https:"].includes(target.protocol)) return null;
  if (!/^[a-z][a-z\d+.-]*:\/\//i.test(value.trim())) return null;
  return target.href;
}
