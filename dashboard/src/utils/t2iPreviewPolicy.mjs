const PREVIEW_CSP = [
  "default-src 'none'",
  "script-src 'none'",
  "style-src 'unsafe-inline'",
  "img-src data: blob:",
  "font-src data:",
  "connect-src 'none'",
  "frame-src 'none'",
  "child-src 'none'",
  "object-src 'none'",
  "base-uri 'none'",
  "form-action 'none'",
  "navigate-to 'none'",
].join("; ");

/**
 * Put a template preview in an opaque document with no network or parent access.
 *
 * @param {string} content Rendered template preview.
 * @returns {string} Preview document with a restrictive content-security policy.
 */
export function buildT2iPreviewDocument(content) {
  const csp = `<meta http-equiv="Content-Security-Policy" content="${PREVIEW_CSP}">`;
  const doctype = content.match(/^\s*<!doctype\s+html[^>]*>/i);
  if (doctype) {
    return `${doctype[0]}${csp}${content.slice(doctype[0].length)}`;
  }
  return `${csp}${content}`;
}

/**
 * Escape preview data before it is interpolated into an HTML template.
 *
 * @param {unknown} value Preview value.
 * @returns {string} HTML-safe text.
 */
export function escapePreviewHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
