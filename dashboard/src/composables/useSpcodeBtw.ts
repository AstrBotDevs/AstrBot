// Author: elecvoid243
// Date: 2026-07-17
// Spec: docs/superpowers/specs/2026-07-17-commit-message-ai-generate-design.md §4.1
// API doc: astrbot_plugin_spcode_toolkit docs/api/v2.20-btw-frontend.md
//
// Vue composable wrapping POST /spcode/btw — a one-shot, side-effect-free
// LLM endpoint ("by the way"). Lifecycle mirrors useSpcodeGitCommit.ts:
// single in-flight call, AbortController, isMounted guard.
//
// Response shape note: the HTTP body is ApiEnvelope whose `data` is the
// plugin envelope (see _make_envelope in the plugin): {reply?,
// has_context?, reason, stderr, elapsed_ms}. Success is indicated by
// `reason === null` plus a non-empty `reply` — NOT by a `success` flag
// (the v2.20 doc's success/data framing is approximate; the plugin code
// is canonical).

import { ref } from "vue";
import { pluginExtensionApi } from "@/api/v1";

export interface BtwParams {
  prompt: string;
  umo?: string | null;
}

export type BtwResult =
  | { ok: true; reply: string; hasContext: boolean }
  | { ok: false; reason: string };

export interface UseSpcodeBtw {
  isGenerating: import("vue").Ref<boolean>;
  ask: (params: BtwParams) => Promise<BtwResult>;
  /** Abort the in-flight request; the composable stays usable afterwards. */
  cancel: () => void;
  /** Unmount hook: abort in-flight and stop all further state writes. */
  dispose: () => void;
}

// Raw shape of the plugin envelope's data field (see _make_envelope).
interface SpcodeBtwRawData {
  reply?: string;
  has_context?: boolean;
  reason: string | null;
  elapsed_ms?: number;
}

// LLM latency varies a lot by model and prompt size (a staged diff can
// be several thousand chars); 30 s proved too tight for slower models.
// 120 s gives even slow providers room while still surfacing genuine
// hangs as a `network` error eventually.
const BTW_TIMEOUT_MS = 120_000;

export function useSpcodeBtw(): UseSpcodeBtw {
  const isGenerating = ref(false);
  let abortController: AbortController | null = null;
  let isMounted = true;

  async function ask(params: BtwParams): Promise<BtwResult> {
    if (!isMounted) return { ok: false, reason: "aborted" };
    abortController?.abort();
    abortController = new AbortController();
    isGenerating.value = true;
    try {
      const resp = await pluginExtensionApi.post<SpcodeBtwRawData>(
        "spcode/btw",
        {
          prompt: params.prompt,
          ...(params.umo ? { umo: params.umo } : {}),
        },
        { signal: abortController.signal, timeout: BTW_TIMEOUT_MS },
      );
      if (!isMounted) return { ok: false, reason: "aborted" };
      const data = resp.data?.data;
      if (!data) return { ok: false, reason: "unknown" };
      const reply = typeof data.reply === "string" ? data.reply.trim() : "";
      if (data.reason === null && reply.length > 0) {
        return { ok: true, reply, hasContext: data.has_context === true };
      }
      // Failure: reason carries the backend ReasonCode. A null reason
      // with an empty reply is folded into empty_response defensively
      // (backend normally reports empty_response itself).
      return { ok: false, reason: data.reason ?? "empty_response" };
    } catch (err) {
      if (!isMounted) return { ok: false, reason: "aborted" };
      if ((err as { name?: string })?.name === "CanceledError") {
        return { ok: false, reason: "aborted" };
      }
      const anyErr = err as { code?: string; message?: string };
      if (
        anyErr.code === "ERR_NETWORK" ||
        anyErr.code === "ECONNABORTED" || // axios timeout
        /network|timeout/i.test(anyErr.message ?? "")
      ) {
        return { ok: false, reason: "network" };
      }
      return { ok: false, reason: "unknown" };
    } finally {
      if (isMounted) isGenerating.value = false;
    }
  }

  function cancel(): void {
    abortController?.abort();
    abortController = null;
  }

  function dispose(): void {
    isMounted = false;
    cancel();
  }

  return { isGenerating, ask, cancel, dispose };
}
