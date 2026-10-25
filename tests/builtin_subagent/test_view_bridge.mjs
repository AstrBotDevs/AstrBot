import { readFile } from "node:fs/promises";
import vm from "node:vm";
import assert from "node:assert/strict";
import { resolve } from "node:path";
if (!process.argv[2])
  throw new Error(
    "Usage: node tests/test_view_bridge.mjs <AstrBot source root>",
  );
const bridgeSource = await readFile(
  resolve(process.argv[2], "astrbot/dashboard/plugin_page_bridge.js"),
  "utf8",
);
const appSource = await readFile(
  new URL(
    "../../astrbot/builtin_stars/astrbot_plugin_subagent/views/runtime/app.js",
    import.meta.url,
  ),
  "utf8",
);
class Element {
  children = [];
  dataset = {};
  handlers = {};
  textContent = "";
  hidden = false;
  value = "";
  checked = false;
  open = false;
  constructor(tag = "div") {
    this.tagName = tag;
  }
  append(...children) {
    this.children.push(...children);
  }
  replaceChildren(...children) {
    this.children = children;
  }
  setAttribute(name, value) {
    this[name] = value;
  }
  addEventListener(name, fn) {
    this.handlers[name] = fn;
  }
  focus() {}
  showModal() {
    this.open = true;
  }
  close() {
    this.open = false;
  }
  querySelectorAll(selector) {
    return this.children.flatMap((child) => [
      ...(selector === "input:checked" &&
      child.tagName === "input" &&
      child.checked
        ? [child]
        : []),
      ...child.querySelectorAll(selector),
    ]);
  }
}
function findAction(element, name) {
  if (element.dataset.action === name) return element;
  for (const child of element.children) {
    const found = findAction(child, name);
    if (found) return found;
  }
}
for (const { populated, failExpertLoad } of [
  { populated: false },
  { populated: true },
  { populated: false, failExpertLoad: true },
]) {
  const elements = new Map();
  const document = {
    hidden: false,
    documentElement: new Element("html"),
    activeElement: null,
    getElementById(id) {
      if (!elements.has(id)) elements.set(id, new Element());
      return elements.get(id);
    },
    createElement(tag) {
      return new Element(tag);
    },
    addEventListener() {},
    querySelectorAll() {
      return [];
    },
  };
  let listener;
  let experts = [];
  const worker = {
    agent_id: "worker-1",
    name: "researcher",
    provider_id: "research-provider",
    state: "completed",
    turn_id: 1,
    completed_steps: 2,
    session: "test",
    result: "recorded-result",
    messages: [{ role: "assistant", content: "Worker finished" }],
  };
  const window = {
    location: { origin: "http://test.local" },
    addEventListener(name, fn) {
      listener = fn;
    },
  };
  window.parent = {
    postMessage(message) {
      let response;
      if (message.kind === "ready")
        response = {
          channel: "astrbot-plugin-page",
          kind: "context",
          context: { locale: "zh-CN", isDark: false },
        };
      else {
        if (
          (message.action === "api:post" &&
            message.body.agents.some((item) => item.name === "reject")) ||
          (failExpertLoad && message.endpoint === "experts")
        ) {
          response = {
            channel: "astrbot-plugin-page",
            kind: "response",
            requestId: message.requestId,
            ok: false,
            error: "Save rejected",
          };
        } else {
          if (message.action === "api:post")
            experts = JSON.parse(JSON.stringify(message.body.agents));
          const data =
            message.endpoint === "experts"
              ? { agents: experts, providers: [], personas: [], tools: [] }
              : { agents: populated ? [worker] : [] };
          response = {
            channel: "astrbot-plugin-page",
            kind: "response",
            requestId: message.requestId,
            ok: true,
            data,
          };
        }
      }
      queueMicrotask(() =>
        listener({
          source: window.parent,
          origin: "http://test.local",
          data: response,
        }),
      );
    },
  };
  const context = vm.createContext({
    window,
    document,
    navigator: { language: "zh-CN" },
    console,
    setTimeout() {},
    clearTimeout() {},
  });
  vm.runInContext(bridgeSource, context);
  await vm.runInContext(`(async () => { ${appSource}\n })()`, context);
  if (failExpertLoad) {
    assert.equal(elements.get("error").hidden, false);
    assert.equal(elements.get("create").disabled, true);
    await elements.get("create").handlers.click();
    assert.equal(elements.get("editor").open, false);
    continue;
  }
  assert.equal(elements.get("error").hidden, true);
  if (populated) {
    await elements.get("workers").children[0].handlers.click();
    const texts = JSON.stringify(elements.get("detail"), (key, value) =>
      key === "handlers" ? undefined : value,
    );
    assert.match(texts, /recorded-result/);
    assert.match(texts, /research-provider/);
    assert.match(
      JSON.stringify(elements.get("workers"), (key, value) =>
        key === "handlers" ? undefined : value,
      ),
      /research-provider/,
    );
  } else
    assert.match(
      elements.get("workers").children[0].textContent,
      /还没有委派任务/,
    );

  await elements.get("create").handlers.click();
  assert.equal(elements.get("editor").open, true);
  elements.get("expert-name").value = "INVALID";
  await elements.get("expert-form").handlers.submit({ preventDefault() {} });
  assert.equal(elements.get("form-error").hidden, false);
  assert.equal(experts.length, 0);
  elements.get("expert-name").value = "writer";
  elements.get("expert-prompt").value = "Draft a document";
  await elements.get("expert-form").handlers.submit({ preventDefault() {} });
  assert.equal(experts[0].name, "writer");
  assert.equal(experts[0].system_prompt, "Draft a document");
  assert.equal(elements.get("editor").open, false);

  await findAction(elements.get("experts"), "edit").handlers.click();
  assert.equal(elements.get("expert-name").value, "writer");
  elements.get("expert-name").value = "editor";
  await elements.get("expert-form").handlers.submit({ preventDefault() {} });
  assert.equal(experts[0].name, "editor");
  await findAction(elements.get("experts"), "toggle").handlers.click();
  assert.equal(experts[0].enabled, false);
  await findAction(elements.get("experts"), "delete").handlers.click();
  await elements.get("confirm-delete").handlers.click();
  assert.equal(experts.length, 0);

  await elements.get("create").handlers.click();
  elements.get("expert-name").value = "reject";
  await elements.get("expert-form").handlers.submit({ preventDefault() {} });
  assert.equal(elements.get("form-error").hidden, false);
  assert.equal(elements.get("editor").open, true);
  assert.equal(experts.length, 0);
  listener({
    source: window.parent,
    origin: "http://test.local",
    data: {
      channel: "astrbot-plugin-page",
      kind: "context",
      context: { locale: "en-US", isDark: true },
    },
  });
  assert.equal(document.documentElement.dataset.theme, "dark");
  assert.equal(document.documentElement.lang, "en");
  assert.equal(elements.get("expert-name").value, "reject");
}
console.log(
  "PASS: real bridge renders progress and supports expert create/edit/toggle/delete, save errors, and live theme changes.",
);
