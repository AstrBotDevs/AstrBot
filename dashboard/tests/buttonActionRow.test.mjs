import assert from "node:assert/strict";
import test from "node:test";
import { nextTick, ref } from "vue";
import { loadSource, mountTemplate } from "./helpers/vueHarness.mjs";

const approvalPart = (overrides = {}) => ({
  type: "actionrow",
  title: "Approve",
  single_use: true,
  buttons: [
    {
      id: "astrbot_tool_approval",
      label: "Reject",
      style: "danger",
      action: { type: "callback", callback_data: "reject" },
    },
    {
      id: "astrbot_tool_approval_conversation",
      label: "Allow conversation",
      style: "primary",
      action: { type: "callback", callback_data: "allow-conversation" },
    },
    {
      id: "astrbot_tool_approval",
      label: "Allow",
      style: "success",
      action: { type: "callback", callback_data: "allow" },
    },
  ],
  ...overrides,
});

function loadChoices(globals = {}) {
  return loadSource(
    new URL("../src/composables/useActionRowChoices.ts", import.meta.url),
    {},
    { localStorage: { getItem: () => "[]", setItem() {} }, ...globals },
  );
}

function mount({ part = approvalPart(), provides = {}, docked, choices }) {
  const callbacks = [];
  const shared = choices || loadChoices();
  const component = loadSource(
    new URL("../src/components/chat/ButtonActionRow.vue", import.meta.url),
    {
      "@/composables/useActionRowChoices": shared,
      "@/i18n/composables": {
        useModuleI18n: () => ({
          tm: (key, params) => (params?.label ? `${key}:${params.label}` : key),
        }),
      },
    },
    { URL },
    true,
  ).default;
  const h = mountTemplate(
    component,
    { part, docked, onCallback: (data) => callbacks.push(data) },
    provides,
  );
  const buttons = () =>
    h.findAll((node) => node.type === "button" && node.props.onClick);
  const text = () =>
    h
      .findAll((node) => node.text)
      .map((node) => node.text)
      .join(" ");
  return { ...h, buttons, text, callbacks, choices: shared };
}

test("approval card orders the decision last and folds the detail away", async () => {
  const h = mount({ part: approvalPart({ detail: '{"path": "a.txt"}' }) });
  try {
    const labels = h.buttons().map((button) =>
      button.children
        .map((child) => child.text)
        .join("")
        .trim(),
    );
    assert.deepEqual(labels, [
      "actionCard.showDetails",
      "Reject",
      "Allow conversation",
      "Allow",
    ]);
    assert.doesNotMatch(h.text(), /a\.txt/);
    h.buttons()[0].props.onClick();
    await nextTick();
    assert.match(h.text(), /a\.txt/);
  } finally {
    h.stop();
  }
});

test("don't ask again never widens a workspace conversation", async () => {
  for (const [before, after] of [
    ["workspace", "workspace_no_ask"],
    ["workspace_no_ask", "workspace_no_ask"],
    ["ask", "full"],
  ]) {
    const mode = ref(before);
    const h = mount({ provides: { approvalPermissionMode: mode } });
    try {
      h.buttons()
        .find((b) => b.children.some((c) => c.text.includes("conversation")))
        .props.onClick();
      await nextTick();
      assert.equal(mode.value, after, before);
    } finally {
      h.stop();
    }
  }
});

test("allow for this conversation switches only the provided permission scope", async () => {
  const parentMode = ref("ask");
  const threadMode = ref("ask");
  const h = mount({ provides: { approvalPermissionMode: threadMode } });
  try {
    h.buttons()
      .find((b) => b.children.some((c) => c.text.includes("conversation")))
      .props.onClick();
    await nextTick();
    assert.deepEqual(h.callbacks, ["allow-conversation"]);
    assert.equal(threadMode.value, "full");
    assert.equal(parentMode.value, "ask");
    assert.equal(h.buttons().length, 0);
    assert.match(h.text(), /actionCard\.chosen:Allow conversation/);
  } finally {
    h.stop();
  }
});

test("a single-use card locks after a choice and a failed delivery unlocks it", async () => {
  const h = mount({});
  try {
    h.buttons().at(-1).props.onClick();
    h.buttons().at(-1)?.props.onClick();
    await nextTick();
    assert.deepEqual(h.callbacks, ["allow"]);
    assert.equal(h.buttons().length, 0);
    h.choices.forgetChosenCallback("allow");
    await nextTick();
    assert.equal(h.buttons().length, 3);
    h.buttons().at(-1).props.onClick();
    await nextTick();
    assert.equal(h.buttons().length, 0);
    assert.deepEqual(h.callbacks, ["allow", "allow"]);
  } finally {
    h.stop();
  }
});

for (const [outcome, label] of [
  ["approved", "actionCard.approved"],
  ["rejected", "actionCard.rejected"],
  ["expired", "actionCard.expired"],
]) {
  test(`the backend outcome ${outcome} locks the card and is shown`, () => {
    const h = mount({ part: approvalPart({ outcome }) });
    try {
      assert.equal(h.buttons().length, 0);
      assert.match(h.text(), new RegExp(label.replace(".", "\\.")));
      assert.ok(
        h.findAll((n) => String(n.props.class).includes("is-trace")).length,
      );
    } finally {
      h.stop();
    }
  });
}

test("the docked card is announced by a polite live region", () => {
  const docked = mount({ docked: true });
  const listed = mount({});
  try {
    assert.equal(
      docked.findAll((n) => n.props["aria-live"] === "polite").length,
      1,
    );
    assert.equal(
      listed.findAll((n) => n.props["aria-live"] === "polite").length,
      0,
    );
  } finally {
    docked.stop();
    listed.stop();
  }
});

test("plain rows keep their buttons and links and are not locked unless single-use", async () => {
  const part = {
    type: "actionrow",
    buttons: [
      {
        id: "a",
        label: "Again",
        action: { type: "callback", callback_data: "again" },
      },
      {
        id: "l",
        label: "Docs",
        action: { type: "url", url: "https://example.com/" },
      },
      {
        id: "x",
        label: "Bad",
        action: { type: "url", url: "javascript:alert(1)" },
      },
    ],
  };
  const h = mount({ part });
  try {
    assert.equal(h.findAll((n) => n.type === "a").length, 1);
    h.buttons()[0].props.onClick();
    h.buttons()[0].props.onClick();
    await nextTick();
    assert.deepEqual(h.callbacks, ["again", "again"]);
    assert.equal(h.buttons()[0].props.disabled, false);
  } finally {
    h.stop();
  }
});

test("dock and message-list copies share choice state and one expiry clock", async () => {
  let now = 1000;
  const timers = new Map();
  const choices = loadChoices({
    Date: { now: () => now },
    setTimeout: (fn, delay) => {
      timers.set(fn, delay);
      return fn;
    },
    clearTimeout: (fn) => timers.delete(fn),
  });
  choices.approvalNow.value = now;
  const part = approvalPart({ expires_at: 2 });
  const dock = mount({ part, docked: true, choices });
  const list = mount({
    part,
    choices,
    provides: { approvalDockKey: ref("reject") },
  });
  try {
    // The list hides the card the input box docks.
    assert.equal(list.buttons().length, 0);
    assert.equal(list.findAll((n) => n.type === "div").length, 0);
    assert.equal(dock.buttons().length, 3);
    // One clock for both copies, woken at the deadline.
    assert.deepEqual([...timers.values()], [1050]);
    dock.buttons().at(-1).props.onClick();
    await nextTick();
    assert.equal(dock.buttons().length, 0);
    assert.ok(
      list.findAll((n) => String(n.props.class).includes("is-trace")).length,
    );
    choices.forgetChosenCallback("allow");
    await nextTick();
    assert.equal(dock.buttons().length, 3);
    now = 2050;
    for (const fn of [...timers.keys()]) {
      timers.delete(fn);
      fn();
    }
    await nextTick();
    assert.equal(dock.buttons().length, 0);
    assert.match(list.text(), /actionCard\.expired/);
    assert.equal(timers.size, 0);
  } finally {
    dock.stop();
    list.stop();
  }
});
