import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";

const moduleUrl = new URL("../src/utils/reasoningEffort.ts", import.meta.url);
const source = readFileSync(moduleUrl, "utf8");
const context = vm.createContext({ exports: {}, require: createRequire(moduleUrl) });
vm.runInContext(
  ts.transpile(source, {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2022,
    esModuleInterop: true,
  }),
  context,
);
const resolveReasoningEffort = (...args) =>
  JSON.parse(JSON.stringify(context.exports.resolveReasoningEffort(...args)));

test("shows the selectable levels for each Gemini model", () => {
  const standard = ["low", "medium", "high"];
  const extended = [...standard, "xhigh"];
  for (const [model, levels] of [
    ["gemini-4-carbon", standard],
    ["models/gemini-4-argon-preview", standard],
    ["gemini-4-neon", extended],
    ["gemini-4-hydrogen-001", extended],
    ["gemini-2.5-pro", []],
  ]) {
    const provider = { type: "googlegenai_chat_completion", model };
    assert.deepEqual(resolveReasoningEffort(provider), { levels, effort: null }, model);
  }
});

test("uses advertised levels and leaves the provider default in effect", () => {
  const levels = ["low", "medium", "high", "xhigh", "max"];
  const metadata = { reasoning_efforts: levels };
  for (const provider of [
    { type: "custom_adapter" },
    { type: "anthropic_chat_completion", anth_thinking_config: { effort: "high" } },
  ]) {
    assert.deepEqual(resolveReasoningEffort(provider, metadata), { levels, effort: null });
  }
});

test("a preset or reasoning flag alone does not advertise selectable levels", () => {
  const provider = {
    type: "openai_chat_completion",
    model: "mimo-v2.5",
    custom_extra_body: { reasoning_effort: "high" },
  };
  for (const metadata of [{ reasoning: true }, { reasoning_efforts: [] }]) {
    assert.deepEqual(resolveReasoningEffort(provider, metadata, "high"), {
      levels: [],
      effort: null,
    });
  }
});

test("sends a manual choice only on supporting models until the user clears it", () => {
  const provider = { type: "openai_responses" };
  const modelA = { reasoning_efforts: ["low", "high", "max"] };
  const modelB = { reasoning_efforts: ["none", "low", "high"] };
  assert.equal(resolveReasoningEffort(provider, modelA, "max").effort, "max");
  assert.equal(resolveReasoningEffort(provider, modelB, "max").effort, null);
  assert.equal(resolveReasoningEffort(provider, modelA, "max").effort, "max");
  assert.equal(resolveReasoningEffort(provider, modelB, "none").effort, "none");
  assert.equal(resolveReasoningEffort(provider, modelB, "").effort, null);
});
