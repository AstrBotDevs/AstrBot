// Author: task16_impl (original); elecvoid243 (v1.1 update)
// Date: 2026-07-03 (original); 2026-07-05 (wire format update)
// Spec: docs/superpowers/specs/2026-07-02-blocking-interactive-choice-design.md §5.1
// Plan: docs/superpowers/plans/2026-07-05-interactive-choice-history-roundtrip.md §2.4
//
// TDD: tests for the pure helper that converts a raw SSE
// `interactive_choice` payload (as emitted by the backend's
// `_push_to_webchat_back_queue`) into an `InteractiveChoicePart`
// ready for `useInteractiveChoiceStore().addChoice(...)`.
//
// The actual SSE integration in `useMessages.ts processStreamPayload`
// delegates to this helper, so we keep it pure & exported.
//
// v1.1 wire format (verified in
// astrbot_plugin_ask_user_choice/ask_user_choice_tool.py):
//   {
//     "type": "plain",                       // generic SSE channel
//     "chain_type": "interactive_choice",    // dispatched by chat_service
//     "data": "<JSON string of the v1.0 envelope>",
//     "message_id": "<sse stream id>"
//   }
//
// `useMessages.ts processStreamPayload` parses `data` and rewraps it
// into the v1.0 envelope before calling this helper, so the function
// contract is unchanged:
//
//   {
//     "type": "interactive_choice",
//     "data": {
//       "request_id": "<uuid>",
//       "spec": {
//         "type": "interactive_choice",
//         "prompt": "<text>",
//         "options": [{"id": "<id>", "label": "<label>"}, ...]
//       },
//       "expires_at": <unix ts>
//     }
//   }
//
// Run: cd dashboard && pnpm exec node --test src/composables/parseInteractiveChoice.sse.test.ts
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  interactiveChoicePartFromSsePayload,
} from "./parseInteractiveChoice.ts";

test("converts a valid SSE payload to InteractiveChoicePart", () => {
  const payload = {
    type: "interactive_choice",
    data: {
      request_id: "uuid-abc",
      spec: {
        type: "interactive_choice",
        prompt: "Pick one",
        options: [
          { id: "A", label: "alpha" },
          { id: "B", label: "beta" },
        ],
      },
      expires_at: 1700000000,
    },
  };
  const part = interactiveChoicePartFromSsePayload(payload);
  assert.ok(part, "expected a non-null part");
  assert.equal(part.type, "interactive_choice");
  assert.equal(part.request_id, "uuid-abc");
  assert.equal(part.prompt, "Pick one");
  assert.equal(part.options.length, 2);
  assert.equal(part.options[0].id, "A");
  assert.equal(part.options[1].label, "beta");
  assert.equal(part.expires_at, 1700000000);
});

test("accepts a spec without an expires_at (expires_at optional)", () => {
  const payload = {
    type: "interactive_choice",
    data: {
      request_id: "r1",
      spec: {
        type: "interactive_choice",
        prompt: "Pick",
        options: [
          { id: "A", label: "a" },
          { id: "B", label: "b" },
        ],
      },
    },
  };
  const part = interactiveChoicePartFromSsePayload(payload);
  assert.ok(part);
  assert.equal(part.request_id, "r1");
  assert.equal(part.expires_at, undefined);
});

test("prefers data.request_id over spec.request_id when both exist", () => {
  const payload = {
    type: "interactive_choice",
    data: {
      request_id: "outer-id",
      spec: {
        type: "interactive_choice",
        request_id: "inner-id",
        prompt: "Pick",
        options: [
          { id: "A", label: "a" },
          { id: "B", label: "b" },
        ],
      },
    },
  };
  const part = interactiveChoicePartFromSsePayload(payload);
  assert.ok(part);
  assert.equal(part.request_id, "outer-id");
});

test("falls back to spec.request_id when data.request_id is missing", () => {
  const payload = {
    type: "interactive_choice",
    data: {
      spec: {
        type: "interactive_choice",
        request_id: "spec-only-id",
        prompt: "Pick",
        options: [
          { id: "A", label: "a" },
          { id: "B", label: "b" },
        ],
      },
    },
  };
  const part = interactiveChoicePartFromSsePayload(payload);
  assert.ok(part);
  assert.equal(part.request_id, "spec-only-id");
});

test("rejects payloads with a wrong top-level type", () => {
  const payload = {
    type: "interactive_choice_resolved",
    data: {
      request_id: "r",
      spec: {
        type: "interactive_choice",
        prompt: "x",
        options: [
          { id: "A", label: "a" },
          { id: "B", label: "b" },
        ],
      },
    },
  };
  assert.equal(interactiveChoicePartFromSsePayload(payload), null);
});

test("rejects payloads missing data.spec", () => {
  const payload = {
    type: "interactive_choice",
    data: { request_id: "r" },
  };
  assert.equal(interactiveChoicePartFromSsePayload(payload), null);
});

test("rejects payloads whose spec fails validation (single option)", () => {
  const payload = {
    type: "interactive_choice",
    data: {
      request_id: "r",
      spec: {
        type: "interactive_choice",
        prompt: "x",
        options: [{ id: "A", label: "only" }],
      },
    },
  };
  assert.equal(interactiveChoicePartFromSsePayload(payload), null);
});

test("rejects null/non-object inputs", () => {
  assert.equal(interactiveChoicePartFromSsePayload(null), null);
  assert.equal(interactiveChoicePartFromSsePayload("string"), null);
  assert.equal(interactiveChoicePartFromSsePayload(123), null);
  assert.equal(interactiveChoicePartFromSsePayload(undefined), null);
});

test("truncates an oversized prompt via the existing helper", () => {
  const payload = {
    type: "interactive_choice",
    data: {
      request_id: "r",
      spec: {
        type: "interactive_choice",
        prompt: "x".repeat(500),
        options: [
          { id: "A", label: "a" },
          { id: "B", label: "b" },
        ],
      },
    },
  };
  const part = interactiveChoicePartFromSsePayload(payload);
  assert.ok(part);
  assert.equal(part?.prompt.length, 200);
});