<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useModuleI18n } from "@/i18n/composables";
import type { CommandItem } from "@/components/extension/componentPanel/types";

// ── Inline helpers (private, no exports) ────────────────────────────────
const HISTORY_KEY = "chatui.spcode.projectPathHistory";
const HISTORY_CAP = 10;
const RECENT_DROPDOWN_COUNT = 5;
const SPCODE_PLUGIN = "astrbot_plugin_spcode_toolkit";

/**
 * Determine whether the spcode "project load" sub-command is currently
 * registered and enabled in the runtime command list.
 *
 * Encapsulated so the parent (`ChatInput`) does not need to import any
 * helper — the menu item's root has `v-if="showMenuItem"` and the parent
 * can simply render `<ProjectLoadMenuItem />` unconditionally.
 *
 * Args:
 *   commands: The current command list from the backend.
 *
 * Returns:
 *   `true` if the menu entry should be visible.
 */
function isProjectLoadAvailable(commands: CommandItem[]): boolean {
  for (const cmd of commands) {
    if (
      cmd.enabled &&
      cmd.plugin === SPCODE_PLUGIN &&
      cmd.effective_command === "project load" &&
      cmd.type === "sub_command"
    ) {
      return true;
    }
    // Recurse into nested sub_commands: backend nests them under their parent
    // group, so `project load` lives under `project`'s sub_commands array.
    if (cmd.sub_commands && isProjectLoadAvailable(cmd.sub_commands)) {
      return true;
    }
  }
  return false;
}

/**
 * Read the recent-project-path history from `localStorage`.
 *
 * Defensive against malformed entries (non-strings, non-arrays, JSON
 * parse errors) — returns an empty list on any failure rather than
 * throwing into the menu render path.
 *
 * Returns:
 *   Up to 10 most-recent paths, newest first.
 */
function getPathHistory(): string[] {
  try {
    const raw = localStorage.getItem(HISTORY_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((p): p is string => typeof p === "string");
  } catch {
    return [];
  }
}

/**
 * Push `path` to the front of the history, deduping by exact match and
 * capping total length at `HISTORY_CAP`. Updates both the reactive ref
 * (in-memory source of truth) and the localStorage mirror.
 *
 * Args:
 *   path: Absolute project path the user just confirmed.
 */
function addToPathHistory(path: string): void {
  const trimmed = path.trim();
  if (!trimmed) return;
  const deduped = [trimmed, ...pathHistory.value.filter((p) => p !== trimmed)].slice(
    0,
    HISTORY_CAP,
  );
  pathHistory.value = deduped;
  try {
    localStorage.setItem(HISTORY_KEY, JSON.stringify(deduped));
  } catch {
    // localStorage write failure (quota, private mode, etc.); silent.
  }
}

/**
 * Remove `path` from the history. Updates both the reactive ref and
 * the localStorage mirror. No-op if `path` is not currently in history.
 *
 * Args:
 *   path: The history entry to remove.
 */
function removeFromPathHistory(path: string): void {
  const filtered = pathHistory.value.filter((p) => p !== path);
  if (filtered.length === pathHistory.value.length) return; // no-op
  pathHistory.value = filtered;
  try {
    localStorage.setItem(HISTORY_KEY, JSON.stringify(filtered));
  } catch {
    // localStorage write failure; silent.
  }
}

/**
 * Compose the final chat input text for the project-load command.
 *
 * Args:
 *   wakePrefix: The leading wake prefix (e.g. `"/"`); falls back to `"/"` defensively so an empty `wakePrefixes` does not produce `"undefinedproject load ..."`.
 *   path: The user-supplied project path.
 *
 * Returns:
 *   A string ready to be submitted to the chat input.
 */
function buildLoadCommand(wakePrefix: string, path: string): string {
  // Defensive fallback: if wakePrefixes is ever empty, use "/" instead of producing "undefinedproject load ...".
  const prefix = wakePrefix || "/";
  return `${prefix}project load ${path.trim()}`;
}

// ── Props / Emits ───────────────────────────────────────────────────────
interface Props {
  commands: CommandItem[];
  wakePrefixes: string[];
}

const props = withDefaults(defineProps<Props>(), {
  commands: () => [],
  wakePrefixes: () => ["/"],
});

const emit = defineEmits<{
  submit: [text: string];
}>();

// ── i18n ────────────────────────────────────────────────────────────────
const { tm } = useModuleI18n("features/chat");

// ── Reactive state ──────────────────────────────────────────────────────
const dialogOpen = ref(false);
const path = ref("");

// In-memory reactive source of truth for history; mirrors localStorage.
// Reassigned on add/remove so `recentPaths` recomputes and the list re-renders.
const pathHistory = ref<string[]>(getPathHistory());

const recentPaths = computed<string[]>(() =>
  pathHistory.value.slice(0, RECENT_DROPDOWN_COUNT),
);
const canSubmit = computed(() => path.value.trim().length > 0);
const showMenuItem = computed(() => isProjectLoadAvailable(props.commands));

// Reset `path` when the dialog opens (clear last input, preserve history dropdown).
watch(dialogOpen, (open) => {
  if (open) {
    path.value = "";
  }
});

// ── Handlers ────────────────────────────────────────────────────────────
function openDialog(): void {
  dialogOpen.value = true;
}

function onConfirm(): void {
  const trimmed = path.value.trim();
  if (!trimmed) return;
  addToPathHistory(trimmed);
  const text = buildLoadCommand(props.wakePrefixes[0] || "/", trimmed);
  emit("submit", text);
  dialogOpen.value = false;
}

/**
 * Emit the `/project unload` command text and close the dialog.
 *
 * No confirmation prompt by design — spcode's unload is idempotent and the
 * user can simply re-load. Mirrors the no-confirm behavior of the load
 * action above.
 */
function onUnload(): void {
  const prefix = props.wakePrefixes[0] || "/";
  emit("submit", `${prefix}project unload`);
  dialogOpen.value = false;
}
</script>

<template>
  <v-list-item
    v-if="showMenuItem"
    class="styled-menu-item"
    rounded="md"
    @click="openDialog"
  >
    <template #prepend>
      <v-icon icon="mdi-folder-open-outline" size="small" />
    </template>
    <v-list-item-title>
      {{ tm("spcodeProjectLoad.menuItem") }}
    </v-list-item-title>
  </v-list-item>

  <v-dialog v-model="dialogOpen" max-width="540">
    <v-card>
      <v-card-title class="text-h6">
        {{ tm("spcodeProjectLoad.dialog.title") }}
      </v-card-title>
      <v-card-text>
        <!-- Unload current project (separate from the load form, above a divider) -->
        <v-btn
          block
          variant="outlined"
          prepend-icon="mdi-folder-remove-outline"
          class="mb-2"
          @click="onUnload"
        >
          {{ tm("spcodeProjectLoad.dialog.unloadButton") }}
        </v-btn>
        <v-divider class="my-4" />
        <v-form @submit.prevent="onConfirm">
          <v-text-field
            v-model="path"
            :label="tm('spcodeProjectLoad.dialog.pathLabel')"
            :placeholder="tm('spcodeProjectLoad.dialog.pathPlaceholder')"
            :hint="tm('spcodeProjectLoad.dialog.pathHint')"
            persistent-hint
            variant="outlined"
            autofocus
            clearable
            @keydown.esc="dialogOpen = false"
          />
          <div v-if="recentPaths.length" class="mt-2">
            <div class="text-caption text-medium-emphasis mb-1">
              {{ tm("spcodeProjectLoad.dialog.historyLabel") }}
            </div>
            <v-list density="compact" class="history-list pa-0">
              <v-list-item
                v-for="item in recentPaths"
                :key="item"
                class="history-item"
                rounded="md"
                @click="path = item"
              >
                <template #prepend>
                  <v-icon icon="mdi-history" size="x-small" />
                </template>
                <v-list-item-title class="text-body-2">
                  {{ item }}
                </v-list-item-title>
                <template #append>
                  <!--
                    `@click.stop` prevents the parent v-list-item click
                    (`path = item`) from firing when the user intends to
                    remove the entry.
                  -->
                  <v-btn
                    icon="mdi-close"
                    variant="text"
                    size="x-small"
                    density="compact"
                    :aria-label="tm('spcodeProjectLoad.dialog.removeFromHistory')"
                    @click.stop="removeFromPathHistory(item)"
                  />
                </template>
              </v-list-item>
            </v-list>
          </div>
          <div v-else class="mt-2 text-caption text-medium-emphasis">
            {{ tm("spcodeProjectLoad.dialog.historyEmpty") }}
          </div>
        </v-form>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="dialogOpen = false">
          {{ tm("spcodeProjectLoad.dialog.cancel") }}
        </v-btn>
        <v-btn
          color="primary"
          variant="elevated"
          :disabled="!canSubmit"
          @click="onConfirm"
        >
          {{ tm("spcodeProjectLoad.dialog.submit") }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<style scoped>
.history-list {
  max-height: 160px;
  overflow-y: auto;
  background: transparent;
}

.history-item :deep(.v-list-item-title) {
  font-family: "Fira Code", "Consolas", monospace;
  font-size: 12px;
  word-break: break-all;
  white-space: normal;
}
</style>
