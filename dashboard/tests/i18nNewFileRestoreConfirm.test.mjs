// Author: 2026-07-15 restore-edge-cases
//
// Smoke test: every locale's chat.json must expose
// ``spcodeProjectLoad.diffSidebar.restore.confirmMessageNewFile`` so the
// single-file restore dialog can switch wording when the target is a
// brand-new (untracked) file. Without this key the dialog would silently
// fall back to the generic "discard changes" message and the user would
// not know the restore action will *delete* the file.
//
// Spec: see file_restore.py handler (tools/webapi/) — untracked files
// are restored by ``Path.unlink``, which is irreversible; the dialog
// must warn the user before that runs.

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const __dirname = dirname(fileURLToPath(import.meta.url));
const LOCALES = ["zh-CN", "en-US", "ru-RU"];
const I18N_KEY =
  "spcodeProjectLoad.diffSidebar.restore.confirmMessageNewFile";

function loadChat(locale) {
  const path = resolve(
    __dirname,
    `../src/i18n/locales/${locale}/features/chat.json`,
  );
  return JSON.parse(readFileSync(path, "utf-8"));
}

for (const locale of LOCALES) {
  test(`chat.json [${locale}] exposes ${I18N_KEY}`, () => {
    const data = loadChat(locale);
    const msg = data?.spcodeProjectLoad?.diffSidebar?.restore
      ?.confirmMessageNewFile;
    assert.ok(
      typeof msg === "string" && msg.length > 0,
      `expected non-empty string at ${I18N_KEY} in ${locale}; got ${JSON.stringify(msg)}`,
    );
  });
}

test("the dialog wording mentions file deletion in every locale", () => {
  // Crude but effective — guarantees the user sees a delete-style warning
  // in their language, not a generic "discard changes" line. Keywords
  // below are intentionally a mix of explicit verbs; tweak if a locale
  // uses a more idiomatic phrasing.
  const expectations = {
    "zh-CN": /删除/,
    "en-US": /delete/i,
    "ru-RU": /удал/i, // удалит, удалить, удалён
  };
  for (const locale of LOCALES) {
    const msg = loadChat(locale)?.spcodeProjectLoad?.diffSidebar?.restore
      ?.confirmMessageNewFile;
    assert.match(msg, expectations[locale], `${locale} should warn about deletion`);
  }
});
