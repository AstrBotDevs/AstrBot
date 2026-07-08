// Author: elecvoid243
// Date: 2026-07-08
// Spec: docs/superpowers/specs/2026-07-07-extra-content-field-amendment.md
//
// v1.1 regression tests: extra_content must survive the full parse path
//   SSE payload → interactiveChoicePartFromSsePayload → truncateInteractiveChoice
// (the two helpers used by `applyInteractiveChoiceSse` and `store.addChoice`).
//
// Why this test file exists separately from `parseInteractiveChoice.sse.test.ts`:
//   The pre-existing v1.0 SSE tests exercise `request_id`, `prompt`,
//   `options`, `expires_at` round-trip but never assert that a v1.1
//   `extra_content` field on `spec` survives the spread+validate+truncate
//   pipeline. A naïve refactor that switched the spread source from
//   `spec` to a hand-picked allow-list would silently drop the field
//   and the dashboard would render the candidate box without its
//   prose section — the user-visible bug is "extra_content 部分没有
//   正常显示" (the Markdown prose area between prompt and options is
//   missing).

import assert from "node:assert/strict";
import { test } from "node:test";

import {
  interactiveChoicePartFromSsePayload,
  truncateInteractiveChoice,
  type InteractiveChoicePart,
} from "./parseInteractiveChoice.ts";

const sampleExtra = `## 推荐选项分析

**我建议选 A**,理由如下:

| 选项 | 优点 | 缺点 |
|------|------|------|
| A    | ✅ 简单直接 | ⚠️ 略单调 |
| B    | ✅ 灵活    | ❌ 略复杂 |

### 注意事项

1. 注意第一条
2. 注意第二条

\`\`\`javascript
const test = () => {
  return "extra_content 端到端测试";
};
\`\`\`

> 这是一个引用块`;

test("extra_content survives SSE payload parsing", () => {
  const payload = {
    type: "interactive_choice",
    data: {
      request_id: "uuid-test-1",
      spec: {
        type: "interactive_choice",
        request_id: "inner-id",
        prompt: "Pick a render mode",
        title: "渲染测试",
        options: [
          { id: "A", label: "A 简单直接" },
          { id: "B", label: "B 灵活" },
          { id: "C", label: "C 折中" },
        ],
        extra_content: sampleExtra,
      },
      expires_at: 1700000000,
    },
  };

  const part = interactiveChoicePartFromSsePayload(payload);
  assert.ok(part, "expected a non-null part");
  assert.equal(
    part?.extra_content,
    sampleExtra,
    "extra_content must be preserved verbatim through SSE payload parsing",
  );
  assert.ok(
    part?.extra_content?.includes("推荐选项分析"),
    "extra_content must contain the H2 heading",
  );
  assert.ok(
    part?.extra_content?.includes("```javascript"),
    "extra_content must contain the fenced code block",
  );
  assert.ok(
    part?.extra_content?.includes("| 选项 | 优点 | 缺点 |"),
    "extra_content must contain the markdown table",
  );
});

test("extra_content survives truncateInteractiveChoice round-trip", () => {
  const part: InteractiveChoicePart = {
    type: "interactive_choice",
    request_id: "uuid-test-2",
    prompt: "p",
    options: [
      { id: "A", label: "a" },
      { id: "B", label: "b" },
    ],
    extra_content: sampleExtra,
  };
  const out = truncateInteractiveChoice(part);
  assert.equal(out.extra_content, sampleExtra);
  assert.equal(out.request_id, "uuid-test-2");
});

test("extra_content is preserved when SSE payload is missing data.request_id", () => {
  const payload = {
    type: "interactive_choice",
    data: {
      spec: {
        type: "interactive_choice",
        request_id: "spec-only",
        prompt: "p",
        options: [
          { id: "A", label: "a" },
          { id: "B", label: "b" },
        ],
        extra_content: sampleExtra,
      },
    },
  };
  const part = interactiveChoicePartFromSsePayload(payload);
  assert.equal(part?.extra_content, sampleExtra);
  assert.equal(part?.request_id, "spec-only");
});
