import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";

// Python calls in the run details are labelled by the timeline itself, not by
// ToolCallCard, so its status text must know the interrupted phase too.
function statusText() {
  const source = readFileSync(
    new URL(
      "../src/components/chat/message_list_comps/ReasoningTimeline.vue",
      import.meta.url,
    ),
    "utf8",
  )
    .split('<script setup lang="ts">')[1]
    .split("</script>")[0];
  const ast = ts.createSourceFile("t.ts", source, ts.ScriptTarget.Latest, true);
  const fn = ast.statements.find(
    (node) =>
      ts.isFunctionDeclaration(node) &&
      node.name?.text === "toolCallStatusText",
  );
  const context = { tm: (key) => key };
  vm.runInNewContext(ts.transpile(fn.getText(ast)), context);
  return (tool) => context.toolCallStatusText(tool);
}

test("an interrupted Python call in the run details is not shown as running", () => {
  const status = statusText();
  assert.equal(status({}), "toolStatus.running");
  assert.equal(status({ phase: "unknown" }), "toolStatus.interrupted");
  assert.equal(status({ finished_ts: 2 }), "toolStatus.done");
});
