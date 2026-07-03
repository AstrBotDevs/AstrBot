// Author: elecvoid243
// Date: 2026-07-03
// Spec: docs/superpowers/specs/2026-07-02-blocking-interactive-choice-design.md §5.2
//
// Pinia store for blocking InteractiveChoice parts.
// Maps request_id -> InteractiveChoicePart, persists to localStorage so a
// hard refresh during a pending choice does not lose the prompt, and
// reconciles against GET /api/chat/interactive-choice/pending on session load.
import { defineStore } from "pinia";

import { httpClient } from "../api/http.ts";
import type { ApiEnvelope } from "../api/v1.ts";
import type { InteractiveChoicePart } from "../composables/parseInteractiveChoice.ts";

/** localStorage key for transient persistence of pending choice parts. */
export const STORAGE_KEY = "astrbot-interactive-choice-pending";

interface SubmitPayload {
  choice_id: string;
  free_text: string;
}

interface PendingResponse {
  pending: InteractiveChoicePart[];
}

interface State {
  activeChoices: Record<string, InteractiveChoicePart>;
}

export const useInteractiveChoiceStore = defineStore("interactiveChoice", {
  state: (): State => ({
    activeChoices: {},
  }),
  getters: {
    hasAny(state): boolean {
      return Object.keys(state.activeChoices).length > 0;
    },
    asList(state): InteractiveChoicePart[] {
      return Object.values(state.activeChoices);
    },
  },
  actions: {
    /**
     * Add or replace a pending choice part keyed by request_id.
     * Persists immediately so a refresh keeps the prompt visible.
     */
    addChoice(part: InteractiveChoicePart): void {
      this.activeChoices[part.request_id] = part;
      this.persist();
    },

    /**
     * Remove a pending choice part by request_id.
     * Persists the new (smaller) list immediately.
     */
    removeChoice(requestId: string): void {
      delete this.activeChoices[requestId];
      this.persist();
    },

    /**
     * Read pending choices from localStorage and populate state.
     * Corrupted payloads are dropped and the key cleared.
     * Safe to call multiple times; later calls overwrite earlier state.
     */
    hydrate(): void {
      let raw: string | null = null;
      try {
        raw = localStorage.getItem(STORAGE_KEY);
      } catch {
        return;
      }
      if (!raw) return;
      try {
        const parsed = JSON.parse(raw) as unknown;
        if (!Array.isArray(parsed)) {
          localStorage.removeItem(STORAGE_KEY);
          return;
        }
        const next: Record<string, InteractiveChoicePart> = {};
        for (const item of parsed) {
          if (
            item &&
            typeof item === "object" &&
            typeof (item as { request_id?: unknown }).request_id === "string"
          ) {
            const part = item as InteractiveChoicePart;
            next[part.request_id] = part;
          }
        }
        this.activeChoices = next;
      } catch {
        try {
          localStorage.removeItem(STORAGE_KEY);
        } catch {
          // ignore
        }
      }
    },

    /**
     * Reconcile state with the backend's view of pending requests for a
     * given session (umo / session_id). Network failures are logged but
     * never thrown — UI must keep working offline.
     */
    async reconcile(umo: string): Promise<void> {
      try {
        const res = await httpClient.get<ApiEnvelope<PendingResponse>>(
          "/api/chat/interactive-choice/pending",
          { params: { session_id: umo } },
        );
        if (res.data?.status === "ok" && res.data.data) {
          const next: Record<string, InteractiveChoicePart> = {};
          for (const part of res.data.data.pending) {
            if (part && typeof part.request_id === "string") {
              next[part.request_id] = part;
            }
          }
          this.activeChoices = next;
          this.persist();
        }
      } catch (e) {
        console.warn("[interactiveChoice] reconcile failed:", e);
      }
    },

    /**
     * Submit a user's selection for the given request_id.
     * On success, optimistically removes the local entry; the caller can
     * roll back by re-adding it if a subsequent event re-injects the part.
     */
    async submitChoice(
      requestId: string,
      payload: SubmitPayload,
    ): Promise<ApiEnvelope<unknown> | undefined> {
      const res = await httpClient.post<ApiEnvelope<unknown>>(
        `/api/chat/interactive-choice/${encodeURIComponent(requestId)}`,
        payload,
      );
      if (res.data?.status === "ok") {
        this.removeChoice(requestId);
      }
      return res.data;
    },

    /**
     * Serialize current state to localStorage. Best-effort: failures are
     * logged but never thrown (e.g. quota exceeded, SSR with no window).
     */
    persist(): void {
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(this.asList));
      } catch (e) {
        console.warn("[interactiveChoice] persist failed:", e);
      }
    },
  },
});