import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";
import { computed, effectScope, nextTick, reactive, ref, watch } from "vue";
import { parse } from "vue/compiler-sfc";

const source = fs.readFileSync(
  new URL("../src/components/shared/SenderSelector.vue", import.meta.url),
  "utf8",
);
const { descriptor } = parse(source);
const ast = ts.createSourceFile(
  "SenderSelector.js",
  descriptor.scriptSetup.content,
  ts.ScriptTarget.Latest,
  true,
);
const script = ast.statements
  .filter((node) => !ts.isImportDeclaration(node))
  .map((node) => node.getText(ast))
  .join("\n");
const sender = {
  sender_id: "123",
  sender_name: "Alice",
  umo: "qq:GroupMessage:1",
  platform: "qq",
  display_name: "Team",
};
const response = (senders) => ({ data: { status: "ok", data: { senders } } });

function loadSelector({
  ids = [],
  readonly = false,
  lookup = async () => response([]),
} = {}) {
  const props = reactive({ modelValue: ids, readonly });
  const events = [];
  const timers = new Map();
  const delays = [];
  const calls = [];
  const botCalls = [];
  const scope = effectScope();
  const context = vm.createContext({
    ref,
    watch,
    computed,
    defineProps: () => props,
    defineEmits:
      () =>
      (...args) =>
        events.push(args),
    useI18n: () => ({ t: (value) => value }),
    conversationApi: {
      filterOptions: async () => {
        botCalls.push(true);
        return {
          data: {
            status: "ok",
            data: { bots: [{ id: "My bot", type: "lark" }] },
          },
        };
      },
    },
    sessionApi: {
      senders: (params) => {
        calls.push(params);
        return lookup(params);
      },
    },
    setTimeout: (fn, delay) => {
      delays.push(delay);
      const id = Symbol();
      timers.set(id, fn);
      return id;
    },
    clearTimeout: (id) => timers.delete(id),
  });
  const state = scope.run(() =>
    vm.runInContext(
      `${script}\n({ dialog, draft, known, search, suggestions, loading, failed, refreshVersion, botTypes, canAddSearch, openDialog, toggleSender, addSearchId, confirmSelection })`,
      context,
    ),
  );
  return {
    ...state,
    props,
    events,
    timers,
    delays,
    calls,
    botCalls,
    stop: () => scope.stop(),
    async flush() {
      await nextTick();
      const pending = [...timers.values()];
      timers.clear();
      await Promise.all(pending.map((fn) => fn()));
      await nextTick();
    },
  };
}

test("stages known and unmatched user IDs until confirmation and preserves cancellation", async () => {
  const ui = loadSelector({ ids: ["unknown"] });
  try {
    ui.openDialog();
    ui.toggleSender(sender);
    ui.search.value = " new-id ";
    await ui.flush();
    assert.equal(ui.canAddSearch.value, true);
    ui.addSearchId();
    assert.deepEqual(Array.from(ui.draft.value), ["unknown", "123", "new-id"]);
    assert.equal(ui.search.value, "");
    assert.deepEqual(Array.from(ui.props.modelValue), ["unknown"]);
    assert.equal(ui.events.length, 0);
    ui.dialog.value = false;
    ui.openDialog();
    assert.deepEqual(Array.from(ui.draft.value), ["unknown"]);
    ui.toggleSender(sender);
    ui.confirmSelection();
    assert.equal(ui.events[0][0], "update:modelValue");
    assert.deepEqual(Array.from(ui.events[0][1]), ["unknown", "123"]);
    assert.equal(ui.dialog.value, false);
  } finally {
    ui.stop();
  }
});

test("loads instance-to-type metadata once per dialog opening, independent of user searches", async () => {
  const ui = loadSelector();
  try {
    assert.equal(ui.botCalls.length, 0);
    ui.openDialog();
    await ui.flush();
    assert.equal(ui.botTypes.value["My bot"], "lark");
    ui.search.value = "Alice";
    await ui.flush();
    ui.refreshVersion.value++;
    await ui.flush();
    assert.equal(ui.botCalls.length, 1);
    ui.dialog.value = false;
    await ui.flush();
    ui.openDialog();
    await ui.flush();
    assert.equal(ui.botCalls.length, 2);
  } finally {
    ui.stop();
  }
});

test("readonly selectors cannot change selections or emit configuration", async () => {
  const ui = loadSelector({ ids: ["unknown"], readonly: true });
  try {
    ui.openDialog();
    ui.toggleSender(sender);
    ui.search.value = "new-id";
    await ui.flush();
    ui.addSearchId();
    ui.confirmSelection();
    assert.equal(ui.dialog.value, false);
    assert.equal(ui.events.length, 0);
    assert.deepEqual(Array.from(ui.props.modelValue), ["unknown"]);
  } finally {
    ui.stop();
  }
});

test("only offers direct addition after an unmatched search and rejects empty or selected IDs", async () => {
  const ui = loadSelector({
    ids: ["123"],
    lookup: async (params) =>
      response(params.search === "Alice" ? [sender] : []),
  });
  try {
    ui.openDialog();
    await ui.flush();
    assert.equal(ui.canAddSearch.value, false);
    for (const query of ["   ", "123", "Alice"]) {
      ui.search.value = query;
      await nextTick();
      assert.equal(ui.canAddSearch.value, false);
      await ui.flush();
      assert.equal(ui.canAddSearch.value, false);
      ui.addSearchId();
    }
    assert.deepEqual(Array.from(ui.draft.value), ["123"]);
    ui.search.value = "new-id";
    await ui.flush();
    ui.addSearchId();
    ui.addSearchId();
    assert.deepEqual(Array.from(ui.draft.value), ["123", "new-id"]);
  } finally {
    ui.stop();
  }
});

test("debounces search and ignores stale responses after new input or closing", async () => {
  let resolveOld;
  const ui = loadSelector({
    lookup: (params) =>
      params.search === "old"
        ? new Promise((resolve) => {
            resolveOld = resolve;
          })
        : Promise.resolve(response([sender])),
  });
  try {
    assert.equal(ui.calls.length, 0);
    ui.openDialog();
    ui.search.value = "old";
    await nextTick();
    const oldRequest = [...ui.timers.values()][0]();
    ui.timers.clear();
    ui.search.value = "new";
    await ui.flush();
    assert.equal(ui.suggestions.value[0].sender_id, "123");
    resolveOld(response([{ ...sender, sender_id: "stale" }]));
    await oldRequest;
    assert.equal(ui.suggestions.value[0].sender_id, "123");
    ui.search.value = "old";
    await nextTick();
    const closingRequest = [...ui.timers.values()][0]();
    ui.dialog.value = false;
    await nextTick();
    resolveOld(response([{ ...sender, sender_id: "closed" }]));
    await closingRequest;
    assert.equal(ui.suggestions.value.length, 0);
    assert.equal(ui.failed.value, false);
  } finally {
    ui.stop();
  }
});

test("resolves existing IDs in bounded batches independently of candidate search", async () => {
  let finish;
  const lookedUp = new Promise((resolve) => {
    finish = resolve;
  });
  const ui = loadSelector({
    ids: Array.from({ length: 201 }, (_, i) => String(i)),
    lookup: async (params) => {
      if (params.sender_ids.includes("200")) finish();
      return response([sender]);
    },
  });
  try {
    await lookedUp;
    await nextTick();
    assert.deepEqual(
      ui.calls.map((call) => call.sender_ids.length),
      [100, 100, 1],
    );
    assert.equal(ui.known.value["123"].sender_name, "Alice");
  } finally {
    ui.stop();
  }
});

test("search failures allow direct ID addition", async () => {
  const ui = loadSelector({
    lookup: async () => {
      throw new Error("Unavailable");
    },
  });
  try {
    ui.openDialog();
    await ui.flush();
    assert.equal(ui.failed.value, true);
    ui.search.value = "manual-user";
    await ui.flush();
    ui.addSearchId();
    ui.confirmSelection();
    assert.deepEqual(Array.from(ui.events[0][1]), ["manual-user"]);
  } finally {
    ui.stop();
  }
});

test("refresh immediately reloads the current search without changing selections", async () => {
  let attempt = 0;
  const ui = loadSelector({
    lookup: async () => {
      attempt++;
      if (attempt === 1) throw new Error("Unavailable");
      return response([sender]);
    },
  });
  try {
    ui.openDialog();
    ui.toggleSender(sender);
    ui.search.value = "Alice";
    await ui.flush();
    assert.equal(ui.failed.value, true);
    assert.equal(ui.delays.at(-1), 250);
    ui.refreshVersion.value++;
    await nextTick();
    assert.equal(ui.loading.value, true);
    assert.equal(ui.delays.at(-1), 0);
    await ui.flush();
    assert.equal(ui.failed.value, false);
    assert.equal(ui.calls.at(-1).search, "Alice");
    assert.equal(ui.search.value, "Alice");
    assert.deepEqual(Array.from(ui.draft.value), ["123"]);
    assert.equal(ui.suggestions.value[0].sender_id, "123");
    assert.equal(ui.events.length, 0);
  } finally {
    ui.stop();
  }
});
