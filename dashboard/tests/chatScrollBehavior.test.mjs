import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";

test("user scrolling disables auto-follow even when the event target is a message", () => {
  const source = readFileSync(
    new URL("../src/components/chat/Chat.vue", import.meta.url),
    "utf8",
  )
    .split('<script setup lang="ts">')[1]
    .split("</script>")[0];
  const ast = ts.createSourceFile(
    "source.ts",
    source,
    ts.ScriptTarget.Latest,
    true,
  );
  const functions = [];
  const names = new Set([
    "handleMessagesInteraction",
    "handleMessagesScroll",
    "scrollToBottom",
  ]);
  const visit = (node) => {
    if (ts.isFunctionDeclaration(node) && names.has(node.name?.text)) {
      functions.push(node.getText(ast));
    }
    ts.forEachChild(node, visit);
  };
  visit(ast);
  assert.equal(functions.length, names.size);

  const container = {
    scrollHeight: 1000,
    clientHeight: 400,
    scrollTop: 600,
  };
  const context = vm.createContext({
    messagesContainer: { value: container },
    activeSessionPagination: { value: undefined },
    maybeLoadEarlierOnScroll: () => {},
    nextTick: (callback) => callback(),
    currSessionId: { value: "session" },
    threadSelection: { visible: false },
    WheelEvent: class {},
    KeyboardEvent: class {},
    isAwayFromBottom: { value: false },
    shouldStickToBottom: { value: true },
    lastMessagesScrollTop: 600,
    scrollIntent: 0,
    LOAD_EARLIER_SCROLL_THRESHOLD: 120,
    suppressAutoScroll: { value: false },
  });
  vm.runInContext(ts.transpile(functions.join("\n")), context);

  context.handleMessagesInteraction({
    type: "pointerdown",
    target: { className: "message-bubble" },
  });
  assert.equal(
    context.shouldStickToBottom.value,
    false,
    "pointer interaction inside a message must cancel auto-follow",
  );

  context.shouldStickToBottom.value = true;
  container.scrollTop = 500;
  context.handleMessagesScroll();
  assert.equal(
    context.shouldStickToBottom.value,
    false,
    "being away from the bottom must cancel auto-follow even without a wheel event",
  );

  context.shouldStickToBottom.value = true;
  container.scrollTop = 500;
  context.scrollToBottom();
  assert.equal(
    container.scrollTop,
    500,
    "a queued auto-scroll must not move a container that is already away from the bottom",
  );
  assert.equal(context.shouldStickToBottom.value, false);
});
