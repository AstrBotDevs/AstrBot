import assert from "node:assert/strict";
import test from "node:test";
import { messagesHarness } from "./helpers/messagesHarness.mjs";
import { loadSource, mountSetup } from "./helpers/vueHarness.mjs";

// Values from the loaded module live in another realm: compare plain copies.
const same = (actual, expected) =>
  assert.deepEqual(JSON.parse(JSON.stringify(actual)), expected);

function approval(id, extra = {}) {
  return {
    type: "actionrow",
    single_use: true,
    title: `Tool ${id} wants to run`,
    tool_call_id: id,
    buttons: [
      {
        id: "ok",
        label: "Allow",
        action: { type: "callback", callback_data: `cb-${id}` },
      },
    ],
    ...extra,
  };
}

// How the reply is split into folded run details and the visible reply.
function splitByMessageWork(blocks) {
  const component = loadSource(
    new URL(
      "../src/components/chat/message_list_comps/MessageWork.vue",
      import.meta.url,
    ),
    {
      "@/components/chat/ThinkingIndicator.vue": {},
      "@/i18n/composables": { useModuleI18n: () => ({ tm: (key) => key }) },
      "@/components/chat/message_list_comps/processCollapse.css": {},
    },
  ).default;
  const h = mountSetup(component, {
    blocks,
    isUser: false,
    isStreaming: false,
  });
  const split = {
    folded: h.state.processBlocks.map((block) => block.kind),
    visible: h.state.finalBlocks.map((block) => block.kind),
  };
  h.stop();
  return split;
}

test("answered approvals of background sub-agents fold into the run details", () => {
  const h = messagesHarness();
  try {
    // Five cards asked while the turn waited, then the final reply text.
    const blocks = h.api.messageBlocks({
      message: [
        { type: "tool_call", tool_calls: [{ id: "wait", name: "wait_agent" }] },
        ...["a", "b", "c", "d", "e"].map((id) =>
          approval(id, { outcome: "approved" }),
        ),
        { type: "plain", text: "All three sub-agents finished." },
      ],
    });
    same(
      blocks.map((block) => [block.kind, block.parts.length]),
      [
        ["thinking", 1],
        ["approval", 5],
        ["content", 1],
      ],
    );
    same(splitByMessageWork(blocks), {
      folded: ["thinking", "approval"],
      visible: ["content"],
    });
  } finally {
    h.stop();
  }
});

test("a reply ending with an answered or expired approval keeps it folded", () => {
  const h = messagesHarness();
  try {
    for (const card of [
      approval("x", { outcome: "rejected" }),
      approval("y", { expires_at: 1 }),
    ]) {
      const blocks = h.api.messageBlocks({ message: [card] });
      same(splitByMessageWork(blocks), {
        folded: ["approval"],
        visible: [],
      });
    }
  } finally {
    h.stop();
  }
});

test("the open approval stays visible until it is answered", () => {
  const h = messagesHarness();
  try {
    const content = {
      message: [
        { type: "plain", text: "Checking the sites." },
        approval("open", { expires_at: Date.now() / 1000 + 120 }),
      ],
    };
    const open = h.api.messageBlocks(content);
    // Its own block, never merged with the text before it.
    same(
      open.map((block) => [block.kind, block.parts.length]),
      [
        ["content", 1],
        ["content", 1],
      ],
    );
    same(splitByMessageWork(open).visible, ["content"]);

    // A click locks the card at once, before the backend outcome arrives.
    h.choices.rememberChosenCallback("cb-open");
    const answered = h.api.messageBlocks(content);
    same(
      answered.map((block) => block.kind),
      ["content", "approval"],
    );
    same(splitByMessageWork(answered), {
      folded: ["content", "approval"],
      visible: [],
    });
  } finally {
    h.stop();
  }
});

test("plain button rows are still part of the reply", () => {
  const h = messagesHarness();
  try {
    const blocks = h.api.messageBlocks({
      message: [
        { type: "plain", text: "Pick one:" },
        { type: "actionrow", buttons: [] },
      ],
    });
    same(
      blocks.map((block) => [block.kind, block.parts.length]),
      [["content", 2]],
    );
  } finally {
    h.stop();
  }
});
