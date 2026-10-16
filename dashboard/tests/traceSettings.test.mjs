import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";
import { computed, ref } from "vue";
import { parse } from "vue/compiler-sfc";

const source = readFileSync(new URL("../src/views/Settings.vue", import.meta.url), "utf8");
const { descriptor } = parse(source);
const ast = ts.createSourceFile("settings.js", descriptor.scriptSetup.content, ts.ScriptTarget.Latest, true);

test("general log settings expose SQLite path, capacity, and retention without legacy JSONL keys", () => {
  const keys = [
    "log_level", "log_file_enable", "log_file_path", "log_file_max_mb",
    "trace_db_path", "trace_db_max_mb", "trace_retention_days",
  ];
  const items = Object.fromEntries(keys.map((key) => [key, { type: key === "trace_db_path" ? "string" : "int" }]));
  const context = vm.createContext({
    computed,
    tm: (key) => key,
    systemConfigMetadata: ref({ system_group: { metadata: { system: { items } } } }),
  });
  const names = new Set(["systemConfigGroups", "generalSystemConfigGroups"]);
  const statements = ast.statements.filter((node) => ts.isVariableStatement(node) &&
    names.has(node.declarationList.declarations[0]?.name.getText(ast)));
  assert.equal(statements.length, names.size);
  vm.runInContext(statements.map((node) => node.getText(ast)).join("\n"), context);
  const groups = vm.runInContext("generalSystemConfigGroups.value", context);
  const logs = groups.find((group) => group.key === "logs");
  assert.deepEqual(Object.keys(logs.metadata.logs.items), keys);
  for (const key of ["trace_log_enable", "trace_log_path", "trace_log_max_mb"]) {
    assert.doesNotMatch(statements[0].getText(ast), new RegExp(key));
  }
});
