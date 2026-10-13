import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";
import { nextTick, reactive, ref, watch } from "vue";
import { compileStyle, compileTemplate, parse } from "vue/compiler-sfc";

const source = readFileSync(new URL("../src/components/shared/TraceMessagePreview.vue", import.meta.url), "utf8");
const { descriptor } = parse(source);
const ast = ts.createSourceFile("preview.js", descriptor.scriptSetup.content, ts.ScriptTarget.Latest, true);

function setup(t, text, height, lines = 4) {
  const props = reactive({ text, lines, tag: "div" });
  const mounted = [];
  const unmounted = [];
  const stops = [];
  const observers = [];
  const context = vm.createContext({
    ref, nextTick,
    watch: (...args) => { stops.push(watch(...args)); },
    defineProps: () => props,
    useModuleI18n: () => ({ tm: (key) => key }),
    onMounted: (callback) => mounted.push(callback),
    onBeforeUnmount: (callback) => unmounted.push(callback),
    getComputedStyle: () => ({ lineHeight: "20px" }),
    ResizeObserver: class {
      constructor(callback) { this.callback = callback; observers.push(this); }
      observe(element) { this.element = element; }
      disconnect() { this.disconnected = true; }
    },
  });
  vm.runInContext(ast.statements.filter((node) => !ts.isImportDeclaration(node)).map((node) => node.getText(ast)).join("\n"), context);
  const state = vm.runInContext("({ props, content, expanded, overflowing, measure })", context);
  state.content.value = { scrollHeight: height };
  mounted.forEach((callback) => callback());
  t.after(() => { stops.forEach((stop) => stop()); unmounted.forEach((callback) => callback()); });
  return { ...state, observers, unmounted };
}

test("short messages have no expansion button; rendered overflow uses the configured line count", (t) => {
  const short = setup(t, "Short reply", 40);
  assert.equal(short.overflowing.value, false);
  assert.equal(short.expanded.value, false);
  const heading = setup(t, "Three-line title", 60, 2);
  assert.equal(heading.overflowing.value, true);
  assert.equal(heading.observers[0].element, heading.content.value);
});

test("expansion and resizing preserve complete Unicode and unbroken text", (t) => {
  const text = "A".repeat(8192) + "\n长消息🙂".repeat(40);
  const state = setup(t, text, 5000);
  assert.equal(state.overflowing.value, true);
  state.expanded.value = true;
  state.observers[0].callback();
  assert.equal(state.expanded.value, true);
  assert.equal(state.props.text, text);
  state.expanded.value = false;
  state.content.value.scrollHeight = 40;
  state.observers[0].callback();
  assert.equal(state.overflowing.value, false);
  state.content.value.scrollHeight = 120;
  state.observers[0].callback();
  assert.equal(state.overflowing.value, true);
  assert.equal(state.expanded.value, false);
  state.unmounted.forEach((callback) => callback());
  assert.equal(state.observers[0].disconnected, true);
});

test("incoming text is remeasured and preserves expansion unless it becomes short", async (t) => {
  const state = setup(t, "Long text", 120);
  state.expanded.value = true;
  state.props.text = "Updated long text";
  await nextTick();
  await nextTick();
  assert.equal(state.expanded.value, true);
  state.content.value.scrollHeight = 20;
  state.props.text = "Short";
  await nextTick();
  await nextTick();
  assert.equal(state.overflowing.value, false);
  assert.equal(state.expanded.value, false);
});

test("title, receipt, and response share accessible untruncated message previews", () => {
  assert.deepEqual(compileTemplate({ source: descriptor.template.content, filename: "TraceMessagePreview.vue", id: "message-preview" }).errors, []);
  assert.deepEqual(compileStyle({ source: descriptor.styles[0].content, filename: "TraceMessagePreview.vue", id: "message-preview", scoped: true }).errors, []);
  assert.match(descriptor.template.content, /v-if="overflowing"/);
  assert.match(descriptor.template.content, /:aria-expanded="expanded"/);
  assert.match(descriptor.template.content, /\{\{ text \}\}/);
  assert.doesNotMatch(source, /\.slice\(|\.substring\(/);
  const trace = readFileSync(new URL("../src/components/shared/TraceDisplayer.vue", import.meta.url), "utf8");
  assert.equal((trace.match(/<TraceMessagePreview\b/g) || []).length, 3);
  assert.match(trace, /:key="selectedEvent.span_id"[^>]*tag="h2" :lines="2"/);
  for (const locale of ["zh-CN", "en-US", "ja-JP", "ru-RU"]) {
    const translations = JSON.parse(readFileSync(new URL(`../src/i18n/locales/${locale}/features/trace.json`, import.meta.url), "utf8").replace(/^\uFEFF/, ""));
    assert.equal(typeof translations.messagePreview.expand, "string");
    assert.equal(typeof translations.messagePreview.collapse, "string");
  }
});
