export const SECRET_UNCHANGED_SENTINEL = '__ASTRBOT_SECRET_UNCHANGED__'

/**
 * Return whether a response value represents an already configured secret.
 *
 * @param {unknown} value A configuration value returned by the dashboard API.
 * @returns {boolean} Whether the value is the write-only secret sentinel.
 */
export function isSecretSentinel(value) {
  return value === SECRET_UNCHANGED_SENTINEL
}

/**
 * Convert a write-only secret sentinel to an empty editable field.
 *
 * @param {unknown} value A configuration value returned by the dashboard API.
 * @returns {unknown} Empty text for sentinels, otherwise the original value.
 */
export function secretDisplayValue(value) {
  return isSecretSentinel(value) ? '' : value
}
