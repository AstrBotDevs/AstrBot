import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";

const levelsJson = JSON.parse(
  readFileSync(
    new URL("../src/utils/geminiThinkingLevels.json", import.meta.url),
    "utf8",
  ),
);
const source = readFileSync(
  new URL("../src/utils/reasoningEffort.ts", import.meta.url),
  "utf8",
);
const context = vm.createContext({
  exports: {},
  require: (specifier) => {
    if (specifier === "./geminiThinkingLevels.json") return levelsJson;
    throw new Error(`Unexpected import: ${specifier}`);
  },
});
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

test("adapts levels for Gemini 4 models and hides selector for non-Gemini-4 models", () => {
  assert.deepEqual(
    resolveReasoningEffort({
      type: "googlegenai_chat_completion",
      model: "gemini-4-carbon",
    }),
    { levels: ["low", "medium", "high"], effort: null },
  );
  assert.deepEqual(
    resolveReasoningEffort({
      type: "googlegenai_chat_completion",
      model: "models/gemini-4-argon-preview",
    }),
    { levels: ["low", "medium", "high"], effort: null },
  );
  assert.deepEqual(
    resolveReasoningEffort({
      type: "googlegenai_chat_completion",
      model: "gemini-4-neon",
    }),
    { levels: ["low", "medium", "high", "xhigh"], effort: null },
  );
  assert.deepEqual(
    resolveReasoningEffort({
      type: "googlegenai_chat_completion",
      model: "gemini-4-hydrogen-001",
    }),
    { levels: ["low", "medium", "high", "xhigh"], effort: null },
  );
  assert.deepEqual(
    resolveReasoningEffort({
      type: "googlegenai_chat_completion",
      model: "gemini-2.5-pro",
    }),
    { levels: [], effort: null },
  );
});

test("uses provider-specific levels and hides models without selectable effort", () => {
  // DeepSeek exposes its native levels and keeps its default until a manual selection.
  assert.deepEqual(
    resolveReasoningEffort(
      { type: "openai_chat_completion", model: "deepseek-v4-flash" },
      { reasoning: true, reasoning_efforts: ["none", "low", "high", "max"] },
    ),
    { levels: ["none", "low", "high", "max"], effort: null },
  );

  // Xiaomi MiMo: toggle-only (reasoning: true, reasoning_efforts: []) -> selector hidden.
  assert.deepEqual(
    resolveReasoningEffort(
      { type: "xiaomi_chat_completion", model: "mimo-v2.5" },
      { reasoning: true, reasoning_efforts: [] },
    ),
    { levels: [], effort: null },
  );

  // OpenAI Responses & OpenAI Subscribe plugin models with 5/6 levels.
  assert.deepEqual(
    resolveReasoningEffort(
      { type: "openai_responses", model: "gpt-6.1-sol" },
      {
        reasoning: true,
        reasoning_efforts: ["low", "medium", "high", "xhigh", "max"],
      },
    ),
    { levels: ["low", "medium", "high", "xhigh", "max"], effort: null },
  );
  assert.deepEqual(
    resolveReasoningEffort(
      { type: "OpenAI Subscribe", model: "gpt-6-luna" },
      {
        reasoning: true,
        reasoning_efforts: ["none", "low", "medium", "high", "xhigh", "max"],
      },
    ),
    {
      levels: ["none", "low", "medium", "high", "xhigh", "max"],
      effort: null,
    },
  );

  // Non-reasoning model stays hidden; Anthropic & Kimi Code follow models.dev reasoning_efforts.
  assert.deepEqual(
    resolveReasoningEffort(
      { type: "openai_chat_completion", model: "gpt-4o" },
      { reasoning: false, reasoning_efforts: [] },
    ),
    { levels: [], effort: null },
  );
  assert.deepEqual(
    resolveReasoningEffort(
      {
        type: "anthropic_chat_completion",
        model: "claude-opus-4-8",
        anth_thinking_config: { type: "adaptive", effort: "high" },
      },
      {
        reasoning: true,
        reasoning_efforts: ["low", "medium", "high", "xhigh", "max"],
      },
    ),
    { levels: ["low", "medium", "high", "xhigh", "max"], effort: null },
  );
  assert.deepEqual(
    resolveReasoningEffort(
      { type: "kimi_code_chat_completion", model: "kimi-for-coding" },
      {
        reasoning: true,
        reasoning_efforts: ["none", "low", "high", "max"],
      },
    ),
    { levels: ["none", "low", "high", "max"], effort: null },
  );
  assert.deepEqual(
    resolveReasoningEffort(
      { type: "kimi_code_chat_completion", model: "kimi-for-coding-highspeed" },
      { reasoning: true, reasoning_efforts: [] },
    ),
    { levels: [], effort: null },
  );
  assert.deepEqual(
    resolveReasoningEffort(
      { type: "anthropic_chat_completion", model: "claude-3-7-sonnet" },
      { reasoning: true },
    ),
    { levels: [], effort: null },
  );
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
