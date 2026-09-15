/**
 * Mask a provider credential for display.
 *
 * Only a short prefix and suffix survive so a user can recognise which key is
 * configured without the full value ever reaching the DOM, a screenshot, or a
 * log line.
 *
 * @param {string} value Raw secret.
 * @returns {string} Masked form safe to render.
 */
export function redactSecret(value) {
  const text = typeof value === 'string' ? value.trim() : ''
  if (!text) return ''
  if (text.length <= 8) return '****'
  return `${text.slice(0, 8)}…${text.slice(-4)}`
}
