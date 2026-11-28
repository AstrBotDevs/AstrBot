import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";
import * as vue from "vue";

// Transpile one source module and run it with the given imports.
function load(path, imports = {}) {
  const source = readFileSync(new URL(path, import.meta.url), "utf8");
  const module = { exports: {} };
  vm.runInNewContext(
    ts.transpile(source, {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
    }),
    {
      module,
      exports: module.exports,
      require: (name) => {
        if (!(name in imports)) throw new Error(`unexpected import ${name}`);
        return imports[name];
      },
      localStorage: memoryStorage(),
      Date,
      setTimeout,
      clearTimeout,
    },
  );
  return module.exports;
}

function memoryStorage() {
  const values = new Map([["user", "alice"]]);
  return {
    get length() {
      return values.size;
    },
    key: (index) => [...values.keys()][index],
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: (key) => values.delete(key),
  };
}

// The modules run in their own realm: compare plain copies.
const plain = (value) => JSON.parse(JSON.stringify(value));

test("a conversation's permission mode is stored with it and removed with it", () => {
  const prefs = load("../src/utils/chatSessionPrefs.mjs", {
    "@/utils/chatPreferences": load("../src/utils/chatPreferences.ts"),
  });
  const storage = memoryStorage();
  prefs.writeChatSessionPref("a", "permission_mode", "workspace", storage);
  prefs.writeChatSessionPref("b", "permission_mode", "full", storage);
  assert.deepEqual(plain(prefs.readChatSessionPrefs("a", storage)), {
    permission_mode: "workspace",
  });
  // An empty value falls back to the default instead of being stored.
  prefs.writeChatSessionPref("a", "permission_mode", "", storage);
  assert.deepEqual(plain(prefs.readChatSessionPrefs("a", storage)), {});
  prefs.clearChatSessionPrefs("b", storage);
  assert.deepEqual(plain(prefs.readChatSessionPrefs("b", storage)), {});
  // A new conversation has no ID yet and nothing is written for it.
  prefs.writeChatSessionPref("", "permission_mode", "full", storage);
  assert.deepEqual(plain(prefs.readChatSessionPrefs("", storage)), {});
});

function approvalCard(callback, extra = {}) {
  return {
    type: "actionrow",
    single_use: true,
    title: "Tool astrbot_execute_shell asks to run",
    buttons: [{ action: { type: "callback", callback_data: callback } }],
    ...extra,
  };
}

test("an approval card locks once chosen, answered or expired, and a failed delivery unlocks it", () => {
  const choices = load("../src/composables/useActionRowChoices.ts", { vue });
  const card = approvalCard("approve-1");
  assert.equal(choices.approvalCardState(card).open, true);

  choices.rememberChosenCallback("approve-1");
  assert.deepEqual(plain(choices.approvalCardState(card)), {
    chosen: "approve-1",
    expired: false,
    outcome: "",
    locked: true,
    open: false,
  });
  choices.forgetChosenCallback("approve-1");
  assert.equal(choices.approvalCardState(card).open, true);

  const answered = approvalCard("approve-2", { outcome: "approved" });
  assert.equal(choices.approvalCardState(answered).locked, true);
  const expired = approvalCard("approve-3", { expires_at: Date.now() / 1000 - 1 });
  choices.approvalNow.value = Date.now();
  assert.equal(choices.approvalCardState(expired).expired, true);
  assert.equal(choices.approvalCardState(expired).open, false);
});

test("the newest open approval card is the one docked on the input box", () => {
  const choices = load("../src/composables/useActionRowChoices.ts", { vue });
  const older = approvalCard("old");
  const newer = approvalCard("new");
  const answered = approvalCard("done", { outcome: "rejected" });
  const messages = [
    { content: { message: [older] } },
    { content: { message: [newer, answered, { type: "plain", text: "…" }] } },
  ];
  assert.equal(choices.latestOpenApproval(messages).part, newer);
  newer.outcome = "approved";
  assert.equal(choices.latestOpenApproval(messages).part, older);
});

test("an approval only changes the tool call it names", () => {
  const source = readFileSync(
    new URL("../src/composables/useMessages.ts", import.meta.url),
    "utf8",
  );
  const ast = ts.createSourceFile("messages.ts", source, ts.ScriptTarget.Latest, true);
  const fn = ast.statements.find(
    (node) =>
      ts.isFunctionDeclaration(node) && node.name?.text === "processToolStreamPayload",
  );
  const context = vm.createContext({
    markMessageStarted() {},
    parseJsonSafe: (value) => (typeof value === "string" ? JSON.parse(value) : value),
    normalizeMessageParts: (parts) => parts,
  });
  vm.runInContext(ts.transpile(fn.getText(ast).replace(/^export /, "")), context);
  const process = context.processToolStreamPayload;

  const waiting = { id: "call-1" };
  const other = { id: "call-2" };
  const record = {
    content: { message: [{ type: "plain", tool_calls: [waiting, other] }] },
  };
  process(record, "actionrow", undefined, {
    ...approvalCard("approve-1"),
    tool_call_id: "call-1",
  });
  assert.equal(waiting.phase, "awaiting_approval");
  assert.equal(other.phase, undefined);

  process(
    record,
    "plain",
    "approval_result",
    JSON.stringify({ tool_call_id: "call-1", outcome: "approved" }),
  );
  assert.equal(waiting.phase, undefined);
  assert.equal(record.content.message[1].outcome, "approved");

  // A call still open when the turn ends never returned.
  other.finished_ts = 1;
  process(record, "end", undefined, null);
  assert.equal(waiting.phase, "unknown");
  assert.equal(other.phase, undefined);
});
