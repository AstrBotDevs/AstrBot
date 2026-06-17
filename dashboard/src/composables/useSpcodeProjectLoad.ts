// src/composables/useSpcodeProjectLoad.ts
//
// Unified visibility gate for the spcode project-load entry points:
//
//   - the "加载项目" chip in :class:`ChatInput` (rendered as
//     :class:`SpcodeProjectIndicator`),
//   - the "+" popover menu's "加载项目目录" item (:class:`ProjectLoadMenuItem`).
//
// Both surfaces share the *same* gate so the two can never disagree
// (previously the chip used a loose "any spcode command" check while
// the menu used a strict "project load sub_command" check, which made
// the chip visible in cases where the menu was correctly hidden).
//
// The new gate is the AND of two conditions:
//
//   1. The spcode plugin is enabled (``activated === true`` from
//      :func:`useSpcodePluginEnabled`).  We can't rely on the
//      registered command list alone because a disabled plugin can
//      still leave its commands registered (the bot keeps the
//      metadata around) — so an explicit activation check is needed.
//
//   2. At least one registered command is part of the ``/project*``
//      tree: the ``project`` group itself or any of its subcommands
//      (e.g. ``project load``, ``project unload``, ``project status``).
//
// Author: elecvoid243
// Last-Modified: 2026-06-17

import { computed, type ComputedRef, type Ref } from "vue";
import type { CommandItem } from "@/components/extension/componentPanel/types";
import { SPCODE_PLUGIN, useSpcodePluginEnabled } from "./useSpcodePluginEnabled";

/**
 * Match a single ``CommandItem`` against the spcode ``/project*`` tree.
 *
 * Accepts:
 *   - The ``project`` group itself (``effective_command === "project"``),
 *   - Any subcommand whose ``effective_command`` starts with
 *     ``"project "`` (e.g. ``"project load"``, ``"project unload"``,
 *     ``"project status"``).
 *
 * The plugin must own the command and the command must be enabled. We
 * do NOT require ``type === "sub_command"`` because the group itself
 * is what the user types at the prompt.
 *
 * Args:
 *   cmd: The command to test.
 *
 * Returns:
 *   ``true`` if this command is part of the spcode ``/project*`` tree.
 */
export function isProjectTreeCommand(cmd: CommandItem): boolean {
  if (!cmd.enabled) return false;
  if (cmd.plugin !== SPCODE_PLUGIN) return false;
  return (
    cmd.effective_command === "project" ||
    cmd.effective_command.startsWith("project ")
  );
}

/**
 * Recursively walk a command list (including nested ``sub_commands``)
 * and report whether any command matches :func:`isProjectTreeCommand`.
 *
 * The backend nests subcommands under their parent group's
 * ``sub_commands`` array, so a single recursive walk is sufficient.
 *
 * Args:
 *   commands: Flat or tree-shaped command list, as returned by
 *     the backend's command list API.
 *
 * Returns:
 *   ``true`` if at least one spcode ``/project*`` command exists.
 */
export function hasProjectTreeCommand(commands: CommandItem[]): boolean {
  for (const cmd of commands) {
    if (isProjectTreeCommand(cmd)) return true;
    if (
      cmd.sub_commands &&
      cmd.sub_commands.length > 0 &&
      hasProjectTreeCommand(cmd.sub_commands)
    ) {
      return true;
    }
  }
  return false;
}

/**
 * Unified visibility composable for the spcode project-load entry points.
 *
 * Combines the singleton spcode enabled state from
 * :func:`useSpcodePluginEnabled` with the caller's command list ref
 * to produce a single computed boolean the chip and the menu both
 * consume.
 *
 * Returns ``true`` ONLY when:
 *   1. The spcode plugin is known to be activated
 *      (``activated === true``), AND
 *   2. At least one ``/project*`` command is registered in the
 *      provided command list.
 *
 * Args:
 *   commands: Ref to the current command list (typically ChatInput's
 *     ``allCommands``).
 *
 * Returns:
 *   - ``isProjectLoadAvailable``: computed boolean the UI should gate
 *     on (``v-if="isProjectLoadAvailable"``).
 *   - ``refreshPluginState``: trigger a re-fetch of the plugin list
 *     (call after the user toggles the plugin on the extension page).
 */
export function useSpcodeProjectLoad(commands: Ref<CommandItem[]>): {
  isProjectLoadAvailable: ComputedRef<boolean>;
  refreshPluginState: () => Promise<void>;
} {
  const { activated, refresh } = useSpcodePluginEnabled();

  const isProjectLoadAvailable = computed<boolean>(() => {
    // Guard 1 — plugin enabled state. We require an explicit `true`;
    // `null` (loading) and `false` (disabled) both fail closed.
    if (activated.value !== true) return false;
    // Guard 2 — at least one /project* command registered. The user
    // can re-enable the plugin and the chip should not pop in until
    // the corresponding command list has been re-fetched, but the
    // commands ref here is already a live computed so we just trust
    // its current value.
    return hasProjectTreeCommand(commands.value);
  });

  return {
    isProjectLoadAvailable,
    refreshPluginState: refresh,
  };
}
