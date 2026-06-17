// src/composables/useSpcodePluginEnabled.ts
//
// Singleton state for the spcode plugin's enabled status, fetched
// from the backend's GET /api/v1/plugins endpoint.
//
// Author: elecvoid243
// Last-Modified: 2026-06-17

import { computed, ref, type ComputedRef } from "vue";
import { pluginApi } from "@/api/v1";

/** Plugin name constant — single source of truth for the spcode plugin id. */
export const SPCODE_PLUGIN = "astrbot_plugin_spcode_toolkit";

/** Minimal shape of a plugin entry returned by ``GET /api/v1/plugins``. */
interface PluginEntry {
  name: string;
  activated: boolean;
}

// ── Module-level shared state ────────────────────────────────────────────
//
// `activated === null`  : not yet known — either the fetch is in flight,
//                         the plugin list response did not include spcode,
//                         or a previous fetch failed.
// `activated === false` : known to be disabled.
// `activated === true`  : known to be enabled.
//
// Consumers should treat `null` as "not enabled" until proven otherwise so
// the UI does not flash the chip on for a plugin that turns out to be
// missing or disabled.
const pluginState = ref<{
  activated: boolean | null;
  fetchedAt: number;
}>({
  activated: null,
  fetchedAt: 0,
});

// De-dupe concurrent fetches so a chat-input mount and a menu mount
// arriving in the same tick do not both issue a /plugins request.
let inflightFetch: Promise<void> | null = null;

/**
 * Fetch the plugin list and resolve the spcode entry's `activated` flag.
 *
 * The fetch is intentionally a singleton: if a request is already in
 * flight, callers share the same promise. On error the previous state
 * is preserved (we do not flip to `null` on transient network errors).
 */
async function fetchSpcodePluginState(): Promise<void> {
  if (inflightFetch) return inflightFetch;
  inflightFetch = (async () => {
    try {
      const res = await pluginApi.list();
      const list = (res.data?.data ?? []) as PluginEntry[];
      const spcode = list.find((p) => p.name === SPCODE_PLUGIN) ?? null;
      pluginState.value = {
        activated: spcode ? spcode.activated : null,
        fetchedAt: Date.now(),
      };
    } catch (err) {
      // Soft-fail: keep the last known state. We don't want a transient
      // network blip to flip the chip off for an enabled plugin.
      console.warn("[useSpcodePluginEnabled] fetch failed:", err);
    } finally {
      inflightFetch = null;
    }
  })();
  return inflightFetch;
}

/**
 * Composable returning the spcode plugin's current enabled state.
 *
 * The state is shared across the dashboard (module-level singleton),
 * so multiple consumers — the chip, the + menu item, the chat-stream
 * parser — observe the same value without coordinating fetches.
 *
 * Returns:
 *   - ``activated``: ``ComputedRef<boolean | null>`` — three-valued.
 *       Callers should treat ``null`` as "not enabled".
 *   - ``refresh``: trigger an explicit re-fetch (e.g. after the user
 *       enables/disables the plugin on the extension page).
 */
export function useSpcodePluginEnabled(): {
  activated: ComputedRef<boolean | null>;
  refresh: () => Promise<void>;
} {
  return {
    activated: computed(() => pluginState.value.activated),
    refresh: fetchSpcodePluginState,
  };
}
