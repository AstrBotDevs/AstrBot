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

  it("ignores reason: 'submitted' (v1.0 success path)", () => {
    const store = useInteractiveChoiceStore();
    const umo = "webchat:FriendMessage:webchat!alice!sess";
    applyInteractiveChoiceResolved(umo, {
      type: "interactive_choice_resolved",
      data: { request_id: "rid-1", reason: "submitted" },
    });
    expect(store.isCancelled(umo, "rid-1")).toBe(false);
  });

  it("throws when umo is missing (Bug Y1 contract)", () => {
    expect(() =>
      applyInteractiveChoiceResolved("", {
        type: "interactive_choice_resolved",
        data: { request_id: "rid-1", reason: "cancelled" },
      }),
    ).toThrow(/missing required 'umo'/);
  });

  it("uses data.umo over the passed umo param (v1.2.1 fix)", () => {
    // Simulate the real bug: the SSE pipeline passes the raw
    // conversation UUID, but the backend includes the full
    // unified_msg_origin in data.umo. The dispatcher must write
    // to the full UMO bucket so InteractiveChoiceBox (which reads
    // with props.currentUmo) can see the cancelled state.
    const store = useInteractiveChoiceStore();
    const rawSessionId = "abc-123";
    const fullUmo = "webchat:FriendMessage:webchat!alice!abc-123";
    applyInteractiveChoiceResolved(rawSessionId, {
      type: "interactive_choice_resolved",
      data: {
        request_id: "rid-1",
        reason: "cancelled",
        umo: fullUmo,
      },
    });
    // The cancelled state must be written under the FULL UMO, not
    // the raw session ID.
    expect(store.isCancelled(fullUmo, "rid-1")).toBe(true);
    expect(store.isCancelled(rawSessionId, "rid-1")).toBe(false);
  });

  it("falls back to umo param when data.umo is absent (backward compat)", () => {
    const store = useInteractiveChoiceStore();
    const umo = "webchat:FriendMessage:webchat!alice!sess";
    applyInteractiveChoiceResolved(umo, {
      type: "interactive_choice_resolved",
      data: { request_id: "rid-1", reason: "cancelled" },
    });
    expect(store.isCancelled(umo, "rid-1")).toBe(true);
  });
});
