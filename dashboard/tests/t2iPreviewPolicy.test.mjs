import assert from "node:assert/strict";
import test from "node:test";

import {
  buildT2iPreviewDocument,
  escapePreviewHtml,
} from "../src/utils/t2iPreviewPolicy.mjs";

test("places a restrictive CSP before any active template content", () => {
  const preview = buildT2iPreviewDocument(
    '<!doctype html><html><head><script src="https://attacker.invalid/x.js"></script></head><body>x</body></html>',
  );

  assert.match(preview, /Content-Security-Policy/);
  assert.match(preview, /default-src 'none'/);
  assert.match(preview, /connect-src 'none'/);
  assert.match(preview, /script-src 'none'/);
  assert.match(preview, /navigate-to 'none'/);
  assert.match(preview, /img-src data: blob:/);
  assert.doesNotMatch(preview, /img-src[^;]*https:/);
  assert.match(preview, /form-action 'none'/);
  assert.ok(preview.indexOf("Content-Security-Policy") < preview.indexOf("<script"));
});

test("prepends the CSP when a template does not contain a head", () => {
  const preview = buildT2iPreviewDocument("<div>preview</div>");
  assert.match(preview, /^<meta http-equiv="Content-Security-Policy"/);
});

test("escapes data interpolated into the preview template", () => {
  assert.equal(
    escapePreviewHtml("<script>alert('x')</script>&"),
    "&lt;script&gt;alert(&#39;x&#39;)&lt;/script&gt;&amp;",
  );
});
