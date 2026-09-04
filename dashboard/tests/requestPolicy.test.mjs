import assert from "node:assert/strict";
import test from "node:test";

import {
  isSameOriginRequest,
  normalizeExternalHttpUrl,
  resolveRequestUrl,
} from "../src/utils/requestPolicy.mjs";

const dashboardOrigin = "https://dashboard.example";

test("resolves same-origin relative and absolute requests", () => {
  assert.equal(
    resolveRequestUrl("/api/v1/chat", dashboardOrigin)?.href,
    "https://dashboard.example/api/v1/chat",
  );
  assert.equal(
    isSameOriginRequest("/api/v1/chat", dashboardOrigin),
    true,
  );
  assert.equal(
    isSameOriginRequest("https://dashboard.example/api/v1/chat", dashboardOrigin),
    true,
  );
});

test("rejects foreign and malformed requests from authenticated clients", () => {
  assert.equal(
    isSameOriginRequest("https://attacker.example/collect", dashboardOrigin),
    false,
  );
  assert.equal(isSameOriginRequest("http://[", dashboardOrigin), false);
});

test("only normalizes absolute HTTP(S) external links", () => {
  assert.equal(
    normalizeExternalHttpUrl("https://example.com/docs?q=1"),
    "https://example.com/docs?q=1",
  );
  assert.equal(normalizeExternalHttpUrl("http://example.com"), "http://example.com/");
  assert.equal(normalizeExternalHttpUrl("/relative"), null);
  assert.equal(normalizeExternalHttpUrl("//example.com"), null);
  assert.equal(normalizeExternalHttpUrl("javascript:alert(1)"), null);
  assert.equal(normalizeExternalHttpUrl("data:text/html,test"), null);
  assert.equal(normalizeExternalHttpUrl("file:///tmp/test"), null);
  assert.equal(normalizeExternalHttpUrl("not a url"), null);
});
