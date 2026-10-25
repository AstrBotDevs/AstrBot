import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";
import { computed, effectScope, nextTick, reactive, ref, watch } from "vue";
import { parse } from "vue/compiler-sfc";

const source = fs.readFileSync(
  new URL("../src/components/shared/UmoSelector.vue", import.meta.url),
  "utf8",
);
const { descriptor } = parse(source);
const ast = ts.createSourceFile(
  "UmoSelector.js",
  descriptor.scriptSetup.content,
  ts.ScriptTarget.Latest,
  true,
);
const script = ast.statements
  .filter((node) => !ts.isImportDeclaration(node))
  .map((node) => node.getText(ast))
  .join("\n");
const first = "qq:GroupMessage:1";
const second = "qq-2:FriendMessage:2";
const response = {
  data: {
    status: "ok",
    data: {
      umos: [first, second],
      umo_infos: [
        { umo: first, auto_name: "Engineering", user_alias: "Team" },
        { umo: second, auto_name: "Alice" },
      ],
    },
  },
};

function loadSelector(overrides = {}, lookup = async () => response) {
  const props = reactive({
    modelValue: "",
    multiple: false,
    platformId: "",
    excludedUmos: [],
    items: null,
    allowManual: true,
    disabled: false,
    readonly: false,
    ...overrides,
  });
  const calls = [];
  const changes = [];
  const botCalls = [];
  const cleanup = [];
  const scope = effectScope();
  const context = vm.createContext({
    ref,
    watch,
    computed,
    onBeforeUnmount: (fn) => cleanup.push(fn),
    defineProps: () => props,
    defineEmits: () => (name, value) => {
      if (name === "update:modelValue") changes.push(value);
    },
    defineExpose: () => {},
    useI18n: () => ({ t: (value) => value }),
    conversationApi: {
      filterOptions: async () => {
        botCalls.push(true);
        return {
          data: {
            status: "ok",
            data: { bots: [{ id: "My bot", type: "discord" }] },
          },
        };
      },
    },
    sessionApi: {
      activeUmos: (params) => {
        calls.push(params);
        return lookup(params);
      },
    },
  });
  const state = scope.run(() =>
    vm.runInContext(
      `${script};\n({ dialog, draft, umos, infos, botTypes, search, manual, manualError, filteredUmos, selectionText, openDialog, toggleUmo, addManual, confirmSelection, loadUmos })`,
      context,
    ),
  );
  return {
    ...state,
    props,
    calls,
    botCalls,
    changes,
    stop() {
      cleanup.forEach((fn) => fn());
      scope.stop();
    },
  };
}

test("single selection is staged, cancel preserves the saved UMO, and confirm emits a string", async () => {
  const ui = loadSelector({ modelValue: "unknown:GroupMessage:old" });
  try {
    await ui.loadUmos();
    ui.openDialog();
    ui.toggleUmo(first);
    assert.equal(ui.props.modelValue, "unknown:GroupMessage:old");
    assert.equal(ui.changes.length, 0);
    ui.dialog.value = false;
    ui.openDialog();
    assert.deepEqual(Array.from(ui.draft.value), ["unknown:GroupMessage:old"]);
    ui.toggleUmo(first);
    ui.confirmSelection();
    assert.equal(ui.changes[0], first);
    assert.equal(ui.dialog.value, false);
  } finally {
    ui.stop();
  }
});

test("resolves custom platform instance IDs once per opening rather than per candidate", async () => {
  const ui = loadSelector();
  try {
    assert.equal(ui.botCalls.length, 0);
    ui.openDialog();
    await new Promise((resolve) => setImmediate(resolve));
    assert.equal(ui.botTypes.value["My bot"], "discord");
    ui.search.value = "Team";
    await nextTick();
    assert.equal(ui.botCalls.length, 1);
  } finally {
    ui.stop();
  }
});

test("filters platform instances exactly in the request, options and response metadata", async () => {
  const ui = loadSelector({ platformId: "qq" });
  try {
    await ui.loadUmos();
    assert.equal(ui.calls[0].platform_id, "qq");
    assert.deepEqual(Array.from(ui.filteredUmos.value), [first]);
    assert.equal(ui.infos.value[second], undefined);
    ui.openDialog();
    ui.toggleUmo(second);
    assert.equal(ui.draft.value.length, 0);
    ui.toggleUmo(first);
    ui.confirmSelection();
    assert.equal(ui.changes[0], first);
  } finally {
    ui.stop();
  }
});

test("shared search matches aliases and respects caller-supplied candidates and exclusions", async () => {
  const ui = loadSelector({
    items: [first, second, "missing:GroupMessage:3"],
    excludedUmos: [second],
  });
  try {
    await ui.loadUmos();
    ui.search.value = "team";
    assert.deepEqual(Array.from(ui.filteredUmos.value), [first]);
    ui.search.value = "Alice";
    assert.equal(ui.filteredUmos.value.length, 0);
    ui.search.value = "";
    assert.equal(ui.filteredUmos.value.length, 2);
    ui.props.items = [second];
    assert.equal(ui.filteredUmos.value.length, 0);
  } finally {
    ui.stop();
  }
});

test("multi-select preserves legacy values and deduplicates manually entered UMOs", () => {
  const ui = loadSelector({ modelValue: ["12345"], multiple: true });
  try {
    ui.openDialog();
    ui.manual.value = ` ${first}\n${first}\n\n12345\nunknown:GroupMessage:3 `;
    ui.addManual();
    ui.confirmSelection();
    assert.deepEqual(Array.from(ui.changes[0]), [
      "12345",
      first,
      "unknown:GroupMessage:3",
    ]);
  } finally {
    ui.stop();
  }
});

test("manual selection rejects wrong platforms, excluded sessions and multiple single values", () => {
  const ui = loadSelector({ platformId: "qq", excludedUmos: [first] });
  try {
    ui.openDialog();
    for (const value of [
      first,
      second,
      "qq:GroupMessage:3\nqq:GroupMessage:4",
    ]) {
      ui.manual.value = value;
      ui.addManual();
      assert.equal(ui.draft.value.length, 0);
      assert.ok(ui.manualError.value);
    }
  } finally {
    ui.stop();
  }
});

test("changing platform or unmounting invalidates pending responses and closes the dialog", async () => {
  const pending = [];
  const ui = loadSelector(
    { platformId: "qq" },
    () => new Promise((resolve) => pending.push(resolve)),
  );
  try {
    ui.dialog.value = true;
    ui.props.platformId = "qq-2";
    await nextTick();
    assert.equal(ui.dialog.value, false);
    pending[1](response);
    await nextTick();
    pending[0](response);
    await nextTick();
    assert.deepEqual(Array.from(ui.umos.value), [second]);
    const request = ui.loadUmos();
    ui.stop();
    pending[2]({
      data: { status: "ok", data: { umos: ["stale"], umo_infos: [] } },
    });
    await request;
    assert.deepEqual(Array.from(ui.umos.value), [second]);
  } finally {
    ui.stop();
  }
});

test("disabled and readonly selectors never emit configuration changes", () => {
  for (const flag of ["disabled", "readonly"]) {
    const ui = loadSelector({ [flag]: true, modelValue: first });
    try {
      ui.openDialog();
      ui.manual.value = second;
      ui.addManual();
      ui.toggleUmo(second);
      ui.confirmSelection();
      assert.equal(ui.dialog.value, false);
      assert.equal(ui.changes.length, 0);
    } finally {
      ui.stop();
    }
  }
});
