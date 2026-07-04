// Author: elecvoid243
// Date: 2026-07-04
// Spec: docs/superpowers/specs/2026-07-02-blocking-interactive-choice-design.md §5.2
//
// Pinia store for blocking InteractiveChoice parts, **scoped per UMO**.
//
// Why per-UMO scoping (Bug Y1 / Y2 fix):
//
//   The Pinia store is a SPA-wide singleton, but chat history is
//   per-session. A naive flat `Record<request_id, Part>` design
//   pooled *every* session's pending prompts in one bag — switching
//   sessions or hard-refreshing after conversations in three
//   different UMOes injected all five old-session boxes into the
//   newest session's page (a "stack" of stale choices). The
//   `submissionStates` "I already chose option B" ints had the same
//   problem — every session's submission intent was visible in
//   every session.
//
// Fix: double-key by `<umo, request_id>` everywhere, with
// `hydrate(umo)` as the single entry point that owns which session
// is currently live. `hydrate` clears in-memory state for any
// previous umo and only loads the current one from localStorage.
//
// The persistence layout is also nested:
//
//   STORAGE_KEY => Record<umo, Record<request_id, InteractiveChoicePart>>
//   SUBMISSION_STORAGE_KEY => Record<umo, Record<request_id, SubmissionState>>
//   IGNORED_STORAGE_KEY => Record<umo, Record<request_id, true>>
//     (request_ids for which a later user message has "passed over" the
//     choice box; persisted so a hard refresh on a tab whose chat history
//     has already moved on keeps the box collapsed instead of letting the
//     message-sequence re-derive it as still pending.)
//
// Old flat-array persistence (pre-2026-07-04) is dropped on first
// hydrate: any payload that is not a flat object keyed by umo is
// treated as stale and removed from localStorage.
import { defineStore } from "pinia";

import { httpClient } from "../api/http.ts";
import type { ApiEnvelope } from "../api/v1.ts";
import type { InteractiveChoicePart } from "../composables/parseInteractiveChoice.ts";

/** localStorage key for transient persistence of pending choice parts. */
export const STORAGE_KEY = "astrbot-interactive-choice-pending";

/**
 * localStorage key for the user's local submission intent, keyed
 * by umo so per-session "I already chose" state stays in its lane.
 *
 * Kept separate from `STORAGE_KEY` so a clear of one does not
 * silently wipe the other (e.g. clearing pending choices after a
 * tab-close should not also nuke the "I chose option B" UI on a
 * still-visible history box).
 */
export const SUBMISSION_STORAGE_KEY = "astrbot-interactive-choice-submissions";

/**
 * localStorage key for per-UMO "this choice box has been passed over
 * by a later user message" sets. Mirrored into `ignoredStates` on
 * hydrate, written through on `markIgnored`.
 *
 * Kept separate from `SUBMISSION_STORAGE_KEY` so a clean of
 * "I chose X" does not silently un-collapse already-ignored boxes
 * (and vice-versa).
 */
export const IGNORED_STORAGE_KEY = "astrbot-interactive-choice-ignored";

interface SubmitPayload {
  choice_id: string;
  free_text: string;
}

interface PendingResponse {
  pending: InteractiveChoicePart[];
}

/**
 * User's local submission intent for a single InteractiveChoice part.
 * `kind === "option"` carries `optionId`; `kind === "input"` carries
 * `freeText`. `submittedAt` is the wall-clock millis when the user
 * clicked/typed, used only for debugging / ordering in the persisted blob.
 */
export interface SubmissionState {
  kind: "option" | "input";
  optionId?: string;
  freeText?: string;
  submittedAt: number;
}

/** Per-UMO wire shape persisted to localStorage. */
type PersistedChoices = Record<string, Record<string, InteractiveChoicePart>>;

/** Per-UMO wire shape for submissions persisted to localStorage. */
type PersistedSubmissions = Record<string, Record<string, SubmissionState>>;

/** Per-UMO wire shape for ignored-by-user-message request ids. */
type PersistedIgnored = Record<string, Record<string, true>>;

/**
 * Structural shape of a bot message as consumed by
 * `injectOrphans`. Declared locally so the store does not import the
 * concrete `ChatRecord` / `MessagePart` types from `useMessages` —
 * keeping the store unit-testable in plain node (no Vue aliases).
 */
interface InjectableBotMessage {
  content: {
    message: Array<Record<string, unknown> & { type: string }>;
  };
}

interface State {
  /**
   * UMO whose data is currently loaded in `activeChoices` /
   * `submissionStates` / `ignoredStates`. `null` means "nothing
   * hydrated yet". Every mutator that touches a session-scoped
   * slice requires an explicit `umo` argument; this field is the
   * cross-check the component passes in, not a hidden default.
   */
  currentUmo: string | null;
  /** Per-UMO pending choice prompts awaiting user action. */
  activeChoices: Record<string, Record<string, InteractiveChoicePart>>;
  /** Per-UMO "the user already chose option B" submission intents. */
  submissionStates: Record<string, Record<string, SubmissionState>>;
  /**
   * Per-UMO set of `request_id`s for which a later user message
   * has already "passed over" the choice box. Mirrors the
   * message-sequence derivation that `ChatMessageList.isInteractiveChoiceIgnored`
   * performs on the fly, but persisted so a hard refresh on a tab
   * whose chat history has already moved on doesn't briefly
   * re-show the box as pending while history reloads.
   *
   * The set is "monotone-additive" per session — once a request_id
   * is ignored it stays ignored until the user closes the tab. This
   * is intentional: a user who has moved past a prompt should not
   * have it pop back if the history API happens to reorder or
   * truncate messages on reload.
   */
  ignoredStates: PersistedIgnored;
}

/** Sentinel used when a caller forgets to pass an explicit umo. */
function missingUmo(action: string): never {
  throw new Error(
    `interactiveChoice.${action}: missing required 'umo' argument ` +
      "(Bug Y1/Y2 fix — per-UMO scoping)",
  );
}

/**
 * Read a per-UMO sub-map; returns an empty object if missing. Does
 * not mutate. Lets mutators stay terse without leaking undefineds.
 */
function bucketOf<T>(
  root: Record<string, Record<string, T>>,
  umo: string,
): Record<string, T> {
  return root[umo] ?? {};
}

export const useInteractiveChoiceStore = defineStore("interactiveChoice", {
  state: (): State => ({
    currentUmo: null,
    activeChoices: {},
    submissionStates: {},
    ignoredStates: {},
  }),
  getters: {
    hasAny(state): boolean {
      if (!state.currentUmo) return false;
      return (
        Object.keys(state.activeChoices[state.currentUmo] ?? {}).length > 0
      );
    },
    asList(state): InteractiveChoicePart[] {
      if (!state.currentUmo) return [];
      return Object.values(state.activeChoices[state.currentUmo] ?? {});
    },
  },
  actions: {
    /**
     * Add or replace a pending choice part for a given UMO.
     * Persists immediately so a refresh keeps the prompt visible.
     */
    addChoice(umo: string, part: InteractiveChoicePart): void {
      if (!umo) missingUmo("addChoice");
      const bucket = (this.activeChoices[umo] ??= {});
      bucket[part.request_id] = part;
      this.persist();
    },

    /**
     * Remove a pending choice part by request_id for a given UMO.
     * Persists the new (smaller) bucket immediately.
     */
    removeChoice(umo: string, requestId: string): void {
      if (!umo) missingUmo("removeChoice");
      const bucket = this.activeChoices[umo];
      if (!bucket) return;
      if (requestId in bucket) {
        delete bucket[requestId];
        if (Object.keys(bucket).length === 0) delete this.activeChoices[umo];
        this.persist();
      }
    },

    /**
     * Record the user's local "I already chose X" intent for a
     * given `request_id` under a specific UMO. Replaces any previous
     * submission for the same id.
     *
     * Why this lives in the store (not in the component) — see Bug 1:
     * the parent v-for can re-mount the `<InteractiveChoiceBox>` when
     * a new bot message arrives, destroying the component's local
     * refs. Reading from the store on every render lets the box
     * restore its "已选择" / "已输入" UI from a single source of truth.
     *
     * NOTE: deliberately NOT coupled to `removeChoice` /
     * `submitChoice`. The user expects to keep seeing "已选择"
     * after the backend acknowledges and the entry leaves
     * `activeChoices[umo]`.
     */
    markSubmitted(
      umo: string,
      requestId: string,
      kind: SubmissionState["kind"],
      payload: { optionId?: string; freeText?: string } = {},
    ): void {
      if (!umo) missingUmo("markSubmitted");
      const bucket = (this.submissionStates[umo] ??= {});
      bucket[requestId] = {
        kind,
        optionId: payload.optionId,
        freeText: payload.freeText,
        submittedAt: Date.now(),
      };
      this.persistSubmissions();
    },

    /**
     * Drop the local submission intent for one `request_id` under a
     * given UMO. Used when the user explicitly undoes their choice
     * (future-proofing) or when the history record is deleted.
     * Safe to call when no entry exists.
     */
    clearSubmissionState(umo: string, requestId: string): void {
      if (!umo) missingUmo("clearSubmissionState");
      const bucket = this.submissionStates[umo];
      if (!bucket || !(requestId in bucket)) return;
      delete bucket[requestId];
      if (Object.keys(bucket).length === 0) delete this.submissionStates[umo];
      this.persistSubmissions();
    },

    /**
     * Read-only access to a single submission state, scoped to the
     * supplied UMO. Kept as a regular method (rather than a Pinia
     * getter) so it can take both the UMO and request id as
     * parameters — Pinia getters cannot.
     */
    getSubmissionState(
      umo: string,
      requestId: string,
    ): SubmissionState | undefined {
      if (!umo) missingUmo("getSubmissionState");
      return bucketOf(this.submissionStates, umo)[requestId];
    },

    /**
     * Mark a batch of `request_id`s under one UMO as "passed over"
     * by a later user message. Idempotent — already-ignored ids are
     * ignored (re-marked is a no-op so the recomputed-derived
     * caller's second pass won't redundant-write).
     */
    markIgnored(umo: string, requestIds: string[]): void {
      if (!umo) missingUmo("markIgnored");
      if (requestIds.length === 0) return;
      const bucket = (this.ignoredStates[umo] ??= {});
      let changed = false;
      for (const id of requestIds) {
        if (typeof id !== "string" || !id) continue;
        if (bucket[id]) continue;
        bucket[id] = true;
        changed = true;
      }
      if (changed) this.persistIgnored();
    },

    /**
     * Read-only check: has this request_id been marked ignored in
     * this UMO's persisted set? Used by
     * `ChatMessageList.isInteractiveChoiceIgnored` as the
     * "persisted wins" branch before falling back to the
     * message-sequence derivation.
     */
    isIgnored(umo: string, requestId: string): boolean {
      if (!umo) return false;
      return Boolean(this.ignoredStates[umo]?.[requestId]);
    },

    /**
     * Read pending choices + submission states for a given UMO from
     * localStorage and populate state. Switching to a different UMO
     * clears the in-memory state for the previous UMO first, so a
     * single SPA can carry one live session at a time.
     *
     * Safe to call multiple times with the same UMO. Best-effort on
     * corruption: malformed payloads are dropped and the key
     * cleared.
     *
     * Migration: legacy flat-array payloads (pre-2026-07-04) are
     * recognised and discarded — they pre-date per-UMO scoping and
     * cannot be safely auto-merged.
     */
    hydrate(umo: string): void {
      if (!umo) missingUmo("hydrate");
      // Clear in-memory state if we're switching sessions; same UMO
      // is a no-op so duplicate mounts don't blow away pending parts.
      if (this.currentUmo !== umo) {
        this.activeChoices = {};
        this.submissionStates = {};
        this.ignoredStates = {};
      }
      this.currentUmo = umo;

      this.hydrateActiveChoices(umo);
      this.hydrateSubmissions(umo);
      this.hydrateIgnored(umo);
    },

    hydrateActiveChoices(umo: string): void {
      const parsed = this.readPerUmo<InteractiveChoicePart>(STORAGE_KEY);
      const perUmo = parsed[umo];
      if (!perUmo) return;
      const next: Record<string, InteractiveChoicePart> = {};
      for (const [requestId, part] of Object.entries(perUmo)) {
        if (
          part &&
          typeof part === "object" &&
          typeof (part as { type?: unknown }).type === "string"
        ) {
          next[requestId] = part as InteractiveChoicePart;
        }
      }
      // Even if the bucket was empty after filtering, retain the key
      // so a hydrate round-trip is a true no-op.
      if (Object.keys(next).length > 0) {
        this.activeChoices[umo] = next;
      }
    },

    hydrateSubmissions(umo: string): void {
      const parsed = this.readPerUmo<SubmissionState>(SUBMISSION_STORAGE_KEY);
      const perUmo = parsed[umo];
      if (!perUmo) return;
      const next: Record<string, SubmissionState> = {};
      for (const [requestId, s] of Object.entries(perUmo)) {
        if (
          s &&
          typeof s === "object" &&
          ((s as { kind?: unknown }).kind === "option" ||
            (s as { kind?: unknown }).kind === "input")
        ) {
          next[requestId] = {
            kind: (s as { kind: "option" | "input" }).kind,
            optionId: (s as { optionId?: string }).optionId,
            freeText: (s as { freeText?: string }).freeText,
            submittedAt:
              typeof (s as { submittedAt?: unknown }).submittedAt === "number"
                ? (s as { submittedAt: number }).submittedAt
                : Date.now(),
          };
        }
      }
      if (Object.keys(next).length > 0) {
        this.submissionStates[umo] = next;
      }
    },

    /**
     * Hydrate `ignoredStates` for a given UMO from localStorage.
     * Same defensive contract as `hydrateSubmissions`: only
     * well-shaped entries survive (we accept any non-empty string
     * id since the payload is just `Record<id, true>`). Called
     * once per `hydrate(umo)`; safe to re-call.
     */
    hydrateIgnored(umo: string): void {
      const parsed = this.readPerUmo<true>(IGNORED_STORAGE_KEY);
      const perUmo = parsed[umo];
      if (!perUmo) return;
      const next: Record<string, true> = {};
      for (const [requestId, _flag] of Object.entries(perUmo)) {
        if (typeof requestId === "string" && requestId) {
          next[requestId] = true;
        }
      }
      if (Object.keys(next).length > 0) {
        this.ignoredStates[umo] = next;
      }
    },

    /**
     * Common read-path for the per-UMO localStorage payloads.
     * Returns an empty object if anything is malformed so callers
     * can keep going. Triggers a one-time migration: legacy
     * flat-array payloads are cleared, never read.
     */
    readPerUmo<T>(key: string): Record<string, Record<string, T>> {
      let raw: string | null = null;
      try {
        raw = localStorage.getItem(key);
      } catch {
        return {};
      }
      if (!raw) return {};
      try {
        const parsed: unknown = JSON.parse(raw);
        // Legacy flat-array shape: drop & migrate.
        if (Array.isArray(parsed)) {
          try {
            localStorage.removeItem(key);
          } catch {
            // ignore — privacy-mode browsers etc.
          }
          return {};
        }
        if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
          try {
            localStorage.removeItem(key);
          } catch {
            // ignore
          }
          return {};
        }
        // We accept any object map; per-UMO integrity is enforced at
        // the call site (each `perUmo` value must itself be an
        // object map).
        return parsed as Record<string, Record<string, T>>;
      } catch {
        try {
          localStorage.removeItem(key);
        } catch {
          // ignore
        }
        return {};
      }
    },

    /**
     * Reconcile state with the backend's view of pending requests
     * for a given session (umo / session_id). Backend-supplied parts
     * for `umo` overwrite local-only entries; parts from other UMOs
     * in `activeChoices` are preserved untouched.
     *
     * Network failures are logged but never thrown — UI must keep
     * working offline.
     */
    async reconcile(umo: string): Promise<void> {
      try {
        // POST (not GET) — the dashboard's static-files catch-all
        // route (`/{static_path:path}`) wins on GET and would shadow
        // every /api/* GET with a 404. The pending endpoint has no
        // side effects, but it lives under /api/... and so must use
        // a method the catch-all ignores. See Bug X1 / X2 fix notes.
        const res = await httpClient.post<ApiEnvelope<PendingResponse>>(
          "/api/chat/interactive-choice/pending",
          { session_id: umo },
        );
        if (res.data?.status === "ok" && res.data.data) {
          const next: Record<string, InteractiveChoicePart> = {};
          for (const part of res.data.data.pending) {
            if (
              part &&
              typeof part === "object" &&
              typeof (part as { request_id?: unknown }).request_id === "string"
            ) {
              const p = part as InteractiveChoicePart;
              next[p.request_id] = p;
            }
          }
          // Overwrite *only* this UMO's bucket; leave sibling UMOs
          // alone so a tab-switch back to a previous session still
          // shows its pending box (Bug Y1).
          this.activeChoices[umo] = next;
          this.persist();
        }
      } catch (e) {
        console.warn("[interactiveChoice] reconcile failed:", e);
      }
    },

    /**
     * Submit a user's selection for the given request_id under a
     * specific UMO. On success, optimistically removes the local
     * entry; the caller can roll back by re-adding it if a
     * subsequent event re-injects the part.
     */
    async submitChoice(
      umo: string,
      requestId: string,
      payload: SubmitPayload,
    ): Promise<ApiEnvelope<unknown> | undefined> {
      if (!umo) missingUmo("submitChoice");
      try {
        const res = await httpClient.post<ApiEnvelope<unknown>>(
          `/api/chat/interactive-choice/${encodeURIComponent(requestId)}`,
          payload,
        );
        if (res.data?.status === "ok") {
          this.removeChoice(umo, requestId);
        }
        return res.data;
      } catch (e) {
        console.error("[interactiveChoice] submitChoice FAILED", {
          umo,
          requestId,
          payload,
          error: e,
        });
        throw e;
      }
    },

    /**
     * Re-attach orphan store parts (those restored by `hydrate()`
     * for the supplied UMO but not present in any in-memory message)
     * to the nearest preceding bot message's `content.message` array.
     *
     * Why: `interactive_choice` parts arrive via SSE and are appended
     * to the in-memory `botRecord.content.message` only — they are
     * not persisted as part of chat history. After a hard refresh,
     * history reload loses them, but `hydrate(umo)` brings them
     * back to the store under the matching UMO bucket. Without this
     * re-attach step, `ChatMessageList.vue`'s template (which only
     * iterates `messageParts(message)`) has no source to render
     * `<InteractiveChoiceBox>` from, so the box disappears — which
     * Bug X1 ("刷新后候选框消失") and Bug X2 ("刷新后退化为
     * tool") are.
     *
     * Idempotent: parts already present in any message (matched by
     * `request_id`) are not re-injected. If no bot message exists in
     * the supplied list, orphan parts are left in the store
     * untouched — they will be re-injected on the next call once a
     * bot message becomes available (e.g. after a tab switch lands
     * on a session whose history is loaded asynchronously).
     *
     * Args:
     *   messages: The current message list as seen by `ChatMessageList`.
     *     Declared structurally so the store stays decoupled from
     *     the concrete `ChatRecord` / `MessagePart` union types.
     *   umo: Required. Restricts the scan to this UMO's bucket so
     *     sibling sessions cannot leak their orphan parts onto this
     *     page (Bug Y1).
     *
     * Returns:
     *   Number of orphan parts newly attached.
     */
    injectOrphans(umo: string, messages: Array<InjectableBotMessage>): number {
      if (!umo) missingUmo("injectOrphans");
      const bucket = this.activeChoices[umo];
      if (!bucket) return 0;
      let count = 0;
      for (const part of Object.values(bucket)) {
        let alreadyAttached = false;
        let lastBotMessage: InjectableBotMessage | null = null;
        for (const m of messages) {
          const msgArr = m?.content?.message;
          if (!Array.isArray(msgArr)) continue;
          // Skip if this bot message already has the part (any
          // part whose `request_id` matches). Once we find a hit we
          // stop scanning; the orphan is no longer an orphan.
          for (const p of msgArr) {
            if (
              p &&
              typeof p === "object" &&
              (p as { request_id?: unknown }).request_id === part.request_id
            ) {
              alreadyAttached = true;
              break;
            }
          }
          if (alreadyAttached) break;
          // Track as candidate injection target. User messages have
          // no `content.message` array (they have plain text) and
          // are skipped by the `Array.isArray` guard above, so
          // `lastBotMessage` only ever points at a bot record.
          lastBotMessage = m;
        }
        if (alreadyAttached || !lastBotMessage) continue;
        lastBotMessage.content.message.push(
          part as unknown as Record<string, unknown> & { type: string },
        );
        count += 1;
      }
      return count;
    },

    /**
     * Serialize the per-UMO `activeChoices` map to localStorage.
     * Best-effort: failures are logged but never thrown (e.g.
     * quota exceeded, SSR with no window).
     */
    persist(): void {
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(this.activeChoices));
      } catch (e) {
        console.warn("[interactiveChoice] persist failed:", e);
      }
    },

    /**
     * Serialize per-UMO `submissionStates` to localStorage. Same
     * best-effort policy as `persist()`. Kept in its own
     * localStorage key (see `SUBMISSION_STORAGE_KEY` rationale).
     */
    persistSubmissions(): void {
      try {
        localStorage.setItem(
          SUBMISSION_STORAGE_KEY,
          JSON.stringify(this.submissionStates),
        );
      } catch (e) {
        console.warn("[interactiveChoice] persistSubmissions failed:", e);
      }
    },

    /**
     * Serialize per-UMO `ignoredStates` to localStorage. Same
     * best-effort policy as `persistSubmissions`.
     */
    persistIgnored(): void {
      try {
        localStorage.setItem(
          IGNORED_STORAGE_KEY,
          JSON.stringify(this.ignoredStates),
        );
      } catch (e) {
        console.warn("[interactiveChoice] persistIgnored failed:", e);
      }
    },
  },
});
