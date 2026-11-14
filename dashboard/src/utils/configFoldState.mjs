/**
 * In-memory fold state for configuration groups.
 *
 * Folding is a view preference for the current page instance only. Keeping it in
 * a module-level map means it survives component unmounts (reopening a dialog,
 * switching providers, SPA navigation) but is dropped on reload, so the schema
 * declaration always wins when the page is opened again.
 */

const foldState = new Map();

/**
 * Prefix shared by every fold-state key, composed by the config renderers.
 */
export const FOLD_STATE_PREFIX = "astrbot.config.collapsed:";

/**
 * Read the fold state remembered for a group in this page instance.
 *
 * @param {string} key Group identity, usually the full configuration path.
 * @returns {boolean | null} The remembered state, or null when never toggled.
 */
export function readFoldState(key) {
  return foldState.has(key) ? foldState.get(key) : null;
}

/**
 * Remember the fold state of a group for this page instance.
 *
 * @param {string} key Group identity, usually the full configuration path.
 * @param {boolean} folded Whether the group is currently folded.
 * @returns {void}
 */
export function writeFoldState(key, folded) {
  foldState.set(key, Boolean(folded));
}
