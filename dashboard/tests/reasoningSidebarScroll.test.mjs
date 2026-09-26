import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";

test("reasoning activity follows the bottom without overriding upward scrolling", () => {
  const source = readFileSync(
    new URL("../src/components/chat/ReasoningSidebar.vue", import.meta.url),
    "utf8",
  )
    .split('<script setup lang="ts">')[1]
    .split("</script>")[0];
  const names = new Set([
    "scrollToLatestActivity",
    "handleSidebarInteraction",
    "handleSidebarScroll",
  ]);
  const functions = [];
  const ast = ts.createSourceFile(
    "source.ts",
    source,
    ts.ScriptTarget.Latest,
    true,
  );
  const visit = (node) => {
    if (ts.isFunctionDeclaration(node) && names.has(node.name?.text)) {
      functions.push(node.getText(ast));
    }
    ts.forEachChild(node, visit);
  };
  visit(ast);
  assert.equal(functions.length, names.size);

  let scrollTop = 600;
  const body = {
    scrollHeight: 1000,
    clientHeight: 400,
    get scrollTop() {
      return scrollTop;
    },
    set scrollTop(value) {
      scrollTop = Math.min(value, this.scrollHeight - this.clientHeight);
    },
  };
  class WheelEvent {
    constructor(deltaY) {
      this.deltaY = deltaY;
      this.ctrlKey = false;
    }
  }
  class KeyboardEvent {}
  const context = vm.createContext({
    props: { modelValue: true },
    sidebarBody: { value: body },
    shouldStickToBottom: { value: true },
    lastSidebarScrollTop: 600,
    touchScrollY: 0,
    scrollIntent: 0,
    nextTick: (callback) => callback(),
    WheelEvent,
    KeyboardEvent,
    Math,
  });
  vm.runInContext(ts.transpile(functions.join("\n")), context);

  context.handleSidebarInteraction(new WheelEvent(-10));
  assert.equal(context.shouldStickToBottom.value, false);
  body.scrollTop = 400;
  context.handleSidebarScroll();
  body.scrollHeight = 1200;
  context.scrollToLatestActivity();
  assert.equal(
    body.scrollTop,
    400,
    "stream updates must preserve the user's upward scroll position",
  );

  context.handleSidebarInteraction(new WheelEvent(10));
  body.scrollTop = 800;
  context.handleSidebarScroll();
  assert.equal(context.shouldStickToBottom.value, true);
  body.scrollHeight = 1300;
  context.scrollToLatestActivity();
  assert.equal(
    body.scrollTop,
    900,
    "stream updates must resume following after the user reaches the bottom",
  );
});
