// Author: askuserchoice_f3_impl
// Date: 2026-07-19
//
// Tests for `applyInteractiveChoiceResolved` — the dispatcher that
// translates the backend's `interactive_choice_resolved
// {reason: "cancelled"}` SSE event into a Pinia-store write to the
// `cancelledStates` bucket added in Task F2. Mirrors the "throw on
// missing umo, silent on bad payload" contract of
// `applyInteractiveChoiceSse` (Bug Y1).

import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { createPinia, setActivePinia } from "pinia";

import { useInteractiveChoiceStore } from "../stores/interactiveChoice";
import { applyInteractiveChoiceResolved } from "./dispatchInteractiveChoice";

describe("applyInteractiveChoiceResolved", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    localStorage.clear();
  });
  afterEach(() => {
    localStorage.clear();
  });

  it("writes cancelled state for a valid payload", () => {
    const store = useInteractiveChoiceStore();
    const umo = "webchat:FriendMessage:webchat!alice!sess";
    applyInteractiveChoiceResolved(umo, {
      type: "interactive_choice_resolved",
      data: { request_id: "rid-1", reason: "cancelled" },
    });
    expect(store.isCancelled(umo, "rid-1")).toBe(true);
  });

  it("silently drops payload with wrong type", () => {
    const store = useInteractiveChoiceStore();
    const umo = "webchat:FriendMessage:webchat!alice!sess";
    applyInteractiveChoiceResolved(umo, {
      type: "interactive_choice",
      data: { request_id: "rid-1" },
    });
    expect(store.isCancelled(umo, "rid-1")).toBe(false);
  });

  it("silently drops payload missing data.request_id", () => {
    const store = useInteractiveChoiceStore();
    const umo = "webchat:FriendMessage:webchat!alice!sess";
    applyInteractiveChoiceResolved(umo, {
      type: "interactive_choice_resolved",
      data: { reason: "cancelled" },
    });
    expect(Object.keys(store.cancelledStates[umo] ?? {})).toHaveLength(0);
  });

  it("silently drops payload with empty request_id after trim", () => {
    const store = useInteractiveChoiceStore();
    const umo = "webchat:FriendMessage:webchat!alice!sess";
    applyInteractiveChoiceResolved(umo, {
      type: "interactive_choice_resolved",
      data: { request_id: "   ", reason: "cancelled" },
    });
    expect(Object.keys(store.cancelledStates[umo] ?? {})).toHaveLength(0);
  });

  it("throws when umo is missing (Bug Y1 contract)", () => {
    expect(() =>
      applyInteractiveChoiceResolved("", {
        type: "interactive_choice_resolved",
        data: { request_id: "rid-1", reason: "cancelled" },
      }),
    ).toThrow(/missing required 'umo'/);
  });
});
