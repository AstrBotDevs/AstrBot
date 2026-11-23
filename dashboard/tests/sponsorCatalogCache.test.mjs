import assert from "node:assert/strict";
import { beforeEach, test, vi } from "vitest";
import { SPONSOR_CACHE_TTL } from "../src/utils/sponsorCatalogSchema.mjs";
import builtIns from "./fixtures/sponsorCatalog.mjs";

const defaults = structuredClone(builtIns);
defaults.sponsors[0].website_url = "https://example.com/";
defaults.sponsors[0].help_url = "https://docs.example.com/start#key";
const cacheKey = "astrbot:sponsor-catalog:v2";
let now, fetch;
beforeEach(() => {
  now = Date.now();
  vi.spyOn(Date, "now").mockReturnValue(now);
  fetch = vi.fn(async (_url, options) => {
    assert.equal(options.credentials, "omit");
    return Response.json(defaults);
  });
  vi.stubGlobal("fetch", fetch);
});
const freshModule = async () => {
  vi.resetModules();
  return import("../src/utils/sponsorCatalog.ts");
};
const cache = () => JSON.parse(localStorage.getItem(cacheKey));
const seed = (value) => localStorage.setItem(cacheKey, typeof value === "string" ? value : JSON.stringify(value));

test("fetches once, deduplicates and persists a valid catalog", async () => {
  const module = await freshModule();
  await Promise.all([module.loadSponsorCatalog(), module.loadSponsorCatalog()]);
  assert.equal(cache().catalog.sponsors[0].website_url, defaults.sponsors[0].website_url);
  assert.equal(module.sponsorCatalog.value.sponsors[0].help_url, defaults.sponsors[0].help_url);
  assert.equal(fetch.mock.calls.length, 1);
  assert.equal(cache().fetchedAt, now);
  assert.equal(module.sponsorCatalog.value.sponsors.length, 3);
  assert.deepEqual(cache().catalog.sponsors[1].i18n, defaults.sponsors[1].i18n);
  assert.deepEqual(module.sponsorCatalog.value.sponsors[1].i18n, defaults.sponsors[1].i18n);
  await module.loadSponsorCatalog();
  assert.equal(fetch.mock.calls.length, 1);
});

test("fresh storage avoids a request until exactly six hours", async () => {
  seed({ fetchedAt: now - SPONSOR_CACHE_TTL + 1, catalog: defaults });
  await (await freshModule()).loadSponsorCatalog();
  assert.equal(fetch.mock.calls.length, 0);
  seed({ fetchedAt: now - SPONSOR_CACHE_TTL, catalog: defaults });
  await (await freshModule()).loadSponsorCatalog();
  assert.equal(fetch.mock.calls.length, 1);
});

test("corrupt and future-dated caches are replaced", async () => {
  for (const value of ["broken-json", JSON.stringify({ fetchedAt: now + 1, catalog: defaults })]) {
    seed(value);
    await (await freshModule()).loadSponsorCatalog();
    assert.equal(cache().fetchedAt, now);
  }
  assert.equal(fetch.mock.calls.length, 2);
});

test("offline refresh retains stale data and a first visit exposes no remote catalog", async () => {
  fetch.mockRejectedValue(new Error("Offline"));
  seed({ fetchedAt: now - SPONSOR_CACHE_TTL, catalog: defaults });
  const stale = await freshModule();
  await stale.loadSponsorCatalog();
  assert.equal(stale.sponsorCatalog.value.sponsors.length, 3);
  localStorage.removeItem(cacheKey);
  const empty = await freshModule();
  await empty.loadSponsorCatalog();
  assert.equal(empty.sponsorCatalog.value, null);
});

test("invalid remote URLs never replace a valid cached catalog", async () => {
  seed({ fetchedAt: now - SPONSOR_CACHE_TTL, catalog: defaults });
  fetch.mockImplementation(async () =>
    Response.json({
      ...defaults,
      sponsors: [{ ...defaults.sponsors[0], api_base: "javascript:alert(1)" }],
    }),
  );
  const module = await freshModule();
  await module.loadSponsorCatalog();
  assert.equal(module.sponsorCatalog.value.sponsors[0].api_base, defaults.sponsors[0].api_base);
});

test("storage failures still allow loading and an empty remote list remains authoritative", async () => {
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
    throw new Error("Disabled");
  });
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
    throw new Error("Full");
  });
  fetch.mockImplementation(async () => Response.json({ ...defaults, sponsors: [] }));
  const module = await freshModule();
  await module.loadSponsorCatalog();
  assert.deepEqual(module.sponsorCatalog.value.sponsors, []);
});
