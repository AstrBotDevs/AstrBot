// src/composables/useSpcodePlanModeLoad.ts
//
// Unified visibility gate for the spcode plan/build chip
// (:class:`SpcodePlanModeChip`).
//
// Mirrors the structure of :mod:`useSpcodeProjectLoad`: a single
// composable that returns one boolean the chip gates on, so the
// visibility can never disagree between surfaces.
//
// The gate is the AND of two conditions:
//
//   1. The spcode plugin is enabled (``activated === true`` from
//      :func:`useSpcodePluginEnabled`). Same rationale as
//      :mod:`useSpcodeProjectLoad` — a disabled plugin can leave
//      stale commands in the registry, so an explicit activation
//      check is required.
//
//   2. BOTH the ``/plan`` and ``/build`` commands are registered.
//      The chip drives a toggle, so showing it when only one of the
//      two exists would be misleading (clicking plan with no
//      `/build` registered would put the user in a state with no
//      in-app way out besides the chat prompt).
//
// Author: elecvoid243
// Last-Modified: 2026-06-19

import { computed, type ComputedRef, type Ref } from "vue";
import type { CommandItem } from "@/components/extension/componentPanel/types";
import { SPCODE_PLUGIN, useSpcodePluginEnabled } from "./useSpcodePluginEnabled";

/** Names of the top-level spcode commands that drive the chip. */
const PLAN_COMMANDS = new Set(["plan", "build"]);

/**
 * Recursively walk a command list (including nested ``sub_commands``)
 * and report whether the given spcode top-level command is present
 * and enabled.
 *
 * Args:
 *   commands: Flat or tree-shaped command list, as returned by
 *     the backend's command list API.
 *   name: The effective_command to look for (e.g. ``"plan"``).
 *
 * Returns:
 *   ``true`` if the spcode plugin owns an enabled command whose
 *   ``effective_command`` equals ``name``.
 */
function hasSpcodeTopLevelCommand(
  commands: CommandItem[],
  name: string,
): boolean {
  for (const cmd of commands) {
    if (
      cmd.enabled &&
      cmd.plugin === SPCODE_PLUGIN &&
      cmd.effective_command === name
    ) {
      return true;
    }
    if (
      cmd.sub_commands &&
      cmd.sub_commands.length > 0 &&
      hasSpcodeTopLevelCommand(cmd.sub_commands, name)
    ) {
      return true;
    }
  }
  return false;
}

/**
 * Unified visibility composable for the spcode plan/build chip.
 *
 * Returns ``true`` ONLY when:
 *   1. The spcode plugin is known to be activated
 *      (``activated === true``), AND
 *   2. BOTH ``/plan`` and ``/build`` top-level commands are
 *      registered in the provided command list.
 *
 * Args:
 *   commands: Ref to the current command list (typically ChatInput's
 *     ``allCommands``).
 *
 * Returns:
 *   - ``isPlanModeChipAvailable``: computed boolean the UI should
 *     gate on (``v-if="isPlanModeChipAvailable"``).
 *   - ``refreshPluginState``: trigger a re-fetch of the plugin list
 *     (call after the user toggles the plugin on the extension
 *     page).
 */
export function useSpcodePlanModeLoad(commands: Ref<CommandItem[]>): {
  isPlanModeChipAvailable: ComputedRef<boolean>;
  refreshPluginState: () => Promise<void>;
} {
  const { activated, refresh } = useSpcodePluginEnabled();

  const isPlanModeChipAvailable = computed<boolean>(() => {
    // Guard 1 — plugin enabled state. We require an explicit `true`;
    // `null` (loading) and `false` (disabled) both fail closed.
    if (activated.value !== true) return false;
    // Guard 2 — both /plan and /build must be present. The chip is a
    // toggle, so showing it without one half would trap the user.
    for (const name of PLAN_COMMANDS) {
      if (!hasSpcodeTopLevelCommand(commands.value, name)) return false;
    }
    return true;
  });

  return {
    isPlanModeChipAvailable,
    refreshPluginState: refresh,
  };
}
