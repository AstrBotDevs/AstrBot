import assert from "node:assert/strict";
import { test } from "node:test";
import builtIns from "./fixtures/sponsorCatalog.mjs";
const defaults = structuredClone(builtIns);
defaults.sponsors[0].website_url = "https://example.com/";
defaults.sponsors[0].help_url = "https://docs.example.com/start#key";
import { SPONSOR_CACHE_TTL } from "../src/utils/sponsorCatalogSchema.mjs";

test("dashboard six-hour cache", async (t) => {
  const now = Date.now();
  let cached = null;
  let fetched = 0;
  t.mock.method(Date, "now", () => now);
  const originalStorage = Object.getOwnPropertyDescriptor(
    globalThis,
    "localStorage",
  );
  t.after(() => {
    if (originalStorage)
      Object.defineProperty(globalThis, "localStorage", originalStorage);
    else delete globalThis.localStorage;
  });
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    writable: true,
    value: {
      getItem: () => cached,
      setItem: (_, value) => {
        cached = value;
      },
    },
  });
  t.mock.method(globalThis, "fetch", async (_, options) => {
    fetched++;
    assert.equal(options.credentials, "omit");
    return Response.json(defaults);
  });
  let sequence = 0;
  const freshModule = () =>
    import(`../src/utils/sponsorCatalog.ts?test=${sequence++}`);

  await t.test(
    "fetches once, deduplicates and persists a valid catalog",
    async () => {
      const module = await freshModule();
      await Promise.all([
        module.loadSponsorCatalog(),
        module.loadSponsorCatalog(),
      ]);
      assert.equal(
        JSON.parse(cached).catalog.sponsors[0].website_url,
        defaults.sponsors[0].website_url,
      );
      assert.equal(
        module.sponsorCatalog.value.sponsors[0].help_url,
        defaults.sponsors[0].help_url,
      );
      assert.equal(fetched, 1);
      assert.equal(JSON.parse(cached).fetchedAt, now);
      assert.equal(module.sponsorCatalog.value.sponsors.length, 3);
      assert.deepEqual(
        JSON.parse(cached).catalog.sponsors[1].i18n,
        defaults.sponsors[1].i18n,
      );
      assert.deepEqual(
        module.sponsorCatalog.value.sponsors[1].i18n,
        defaults.sponsors[1].i18n,
      );
      await module.loadSponsorCatalog();
      assert.equal(fetched, 1);
    },
  );
  await t.test(
    "fresh storage avoids a request until exactly six hours",
    async () => {
      cached = JSON.stringify({
        fetchedAt: now - SPONSOR_CACHE_TTL + 1,
        catalog: defaults,
      });
      await (await freshModule()).loadSponsorCatalog();
      assert.equal(fetched, 1);
      cached = JSON.stringify({
        fetchedAt: now - SPONSOR_CACHE_TTL,
        catalog: defaults,
      });
      await (await freshModule()).loadSponsorCatalog();
      assert.equal(fetched, 2);
    },
  );
  await t.test("corrupt and future-dated caches are replaced", async () => {
    for (const value of [
      "broken-json",
      JSON.stringify({ fetchedAt: now + 1, catalog: defaults }),
    ]) {
      cached = value;
      await (await freshModule()).loadSponsorCatalog();
      assert.equal(JSON.parse(cached).fetchedAt, now);
    }
    assert.equal(fetched, 4);
  });
  await t.test(
    "offline refresh retains stale data and first visit uses built-ins",
    async () => {
      globalThis.fetch = async () => {
        throw new Error("Offline");
      };
      cached = JSON.stringify({
        fetchedAt: now - SPONSOR_CACHE_TTL,
        catalog: defaults,
      });
      const stale = await freshModule();
      await stale.loadSponsorCatalog();
      assert.equal(stale.sponsorCatalog.value.sponsors.length, 3);
      cached = null;
      const empty = await freshModule();
      await empty.loadSponsorCatalog();
      assert.equal(empty.sponsorCatalog.value, null);
    },
  );
  await t.test(
    "invalid remote data never replaces a valid cached catalog",
    async () => {
      cached = JSON.stringify({
        fetchedAt: now - SPONSOR_CACHE_TTL,
        catalog: defaults,
      });
      globalThis.fetch = async () =>
        Response.json({
          ...defaults,
          sponsors: [
            { ...defaults.sponsors[0], api_base: "javascript:alert(1)" },
          ],
        });
      const module = await freshModule();
      await module.loadSponsorCatalog();
      assert.equal(
        module.sponsorCatalog.value.sponsors[0].api_base,
        defaults.sponsors[0].api_base,
      );
    },
  );
  await t.test(
    "storage failures still allow loading and an empty remote list remains authoritative",
    async () => {
      globalThis.localStorage = {
        getItem() {
          throw new Error("Disabled");
        },
        setItem() {
          throw new Error("Full");
        },
      };
      globalThis.fetch = async () =>
        Response.json({ ...defaults, sponsors: [] });
      const module = await freshModule();
      await module.loadSponsorCatalog();
      assert.deepEqual(module.sponsorCatalog.value.sponsors, []);
    },
  );
});
