import assert from "node:assert/strict";
import { flushPromises } from "@vue/test-utils";
import { onTestFinished, test, vi } from "vitest";
import PluginViewCard from "../src/components/chat/message_list_comps/PluginViewCard.vue";
import { setApiBaseUrl } from "../src/utils/request.ts";
import { mountDashboard } from "./helpers/components.mjs";

for (const authorized of [true, false]) {
  test(`card loads the shared SDK through host authentication: ${authorized}`, async () => {
    const sdk = "window.__sdkFixture = true;";
    localStorage.setItem("token", "test-dashboard-token");
    const requests = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url, init) => {
        requests.push({ url, headers: init?.headers });
        if (!authorized || init?.headers?.get("Authorization") !== "Bearer test-dashboard-token") {
          return new Response("Unauthorized", { status: 401 });
        }
        return url.endsWith("bridge-sdk.js")
          ? new Response(sdk)
          : Response.json({
              data: {
                html: '<html><head><base href="https://untrusted.example/"></head><body>Reading list</body></html>',
                base_url: "/scoped-view-assets/",
                data: { books: [{ title: "Example" }] },
                revision: 1,
              },
            });
      }),
    );
    const { wrapper, vm } = await mountDashboard(PluginViewCard, {
      props: { part: { id: "test-view", name: "reading" } },
    });
    await flushPromises();
    assert.deepEqual(
      requests.map(({ url }) => url),
      ["/api/v1/chat/views/test-view", "/api/plugin/page/bridge-sdk.js"],
    );
    for (const request of requests) assert.equal(request.headers.get("Authorization"), "Bearer test-dashboard-token");
    assert.equal(vm.error, !authorized);
    if (authorized) {
      const iframe = wrapper.get("iframe");
      assert.equal(iframe.attributes("sandbox"), "allow-scripts");
      const document = new DOMParser().parseFromString(iframe.attributes("srcdoc"), "text/html");
      assert.equal(document.querySelectorAll("base").length, 1);
      assert.equal(document.querySelector("base").href, "http://localhost:3000/scoped-view-assets/");
      assert.equal(document.querySelector("script").textContent, sdk);
      assert.equal(document.querySelector("script").hasAttribute("src"), false);
      assert.equal(vm.srcdoc.includes("test-dashboard-token"), false);
    } else {
      assert.equal(vm.srcdoc, "");
      assert.equal(wrapper.find("iframe").exists(), false);
      assert.equal(wrapper.find('[role="status"]').exists(), true);
    }
  });
}

test("a card fetched from a configured backend resolves scoped assets against that same backend", async () => {
  setApiBaseUrl("https://backend.example/prefix/api");
  onTestFinished(() => setApiBaseUrl(""));
  localStorage.setItem("token", "test-dashboard-token");
  const requests = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url, init) => {
      requests.push({ url, headers: init.headers });
      return url.endsWith("bridge-sdk.js")
        ? new Response("window.__sdkFixture = true;")
        : Response.json({
            data: {
              html: "<html><head></head><body>View</body></html>",
              base_url: "/api/v1/chat/views/remote/assets/",
              data: {},
              revision: 1,
            },
          });
    }),
  );
  const { wrapper } = await mountDashboard(PluginViewCard, { props: { part: { id: "remote", name: "remote" } } });
  await flushPromises();
  assert.deepEqual(
    requests.map((request) => request.url),
    [
      "https://backend.example/prefix/api/v1/chat/views/remote",
      "https://backend.example/prefix/api/plugin/page/bridge-sdk.js",
    ],
  );
  for (const request of requests) assert.equal(request.headers.get("Authorization"), "Bearer test-dashboard-token");
  const document = new DOMParser().parseFromString(wrapper.get("iframe").attributes("srcdoc"), "text/html");
  assert.equal(document.querySelector("base").href, "https://backend.example/prefix/api/v1/chat/views/remote/assets/");
});
