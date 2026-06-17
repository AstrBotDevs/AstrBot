<script setup lang="ts">
// Trigger for the "加载项目目录" entry inside the `+` popover menu.
//
// The actual project-load dialog lives in :class:`ProjectLoadDialog`,
// mounted at the :class:`ChatInput` level so it survives the menu's
// popover lifetime. This component is just the menu entry that emits
// an `open` event so the parent can call the dialog's opener through
// the shared template ref.
//
// Visibility gate is shared with the "加载项目" chip — both surfaces
// read from the same :func:`useSpcodeProjectLoad` composable so the
// chip and this menu item can never disagree (one visible while the
// other is hidden). The gate is: spcode plugin enabled AND at least
// one `/project*` command registered.

import { toRef } from "vue";
import { useModuleI18n } from "@/i18n/composables";
import type { CommandItem } from "@/components/extension/componentPanel/types";
import { useSpcodeProjectLoad } from "@/composables/useSpcodeProjectLoad";

// ── Props / Emits ───────────────────────────────────────────────────────
interface Props {
  commands: CommandItem[];
}

const props = withDefaults(defineProps<Props>(), {
  commands: () => [],
});

const emit = defineEmits<{
  open: [];
}>();

// ── i18n ────────────────────────────────────────────────────────────────
const { tm } = useModuleI18n("features/chat");

// ── Reactive state ──────────────────────────────────────────────────────
// Single source of truth for visibility: the chip and this menu item
// both read from the same composable.
const { isProjectLoadAvailable } = useSpcodeProjectLoad(
  toRef(props, "commands"),
);
const showMenuItem = isProjectLoadAvailable;

// ── Handlers ────────────────────────────────────────────────────────────
function onClick(): void {
  emit("open");
}
</script>

<template>
  <v-list-item
    v-if="showMenuItem"
    class="styled-menu-item"
    rounded="md"
    @click="onClick"
  >
    <template #prepend>
      <v-icon icon="mdi-folder-open-outline" size="small" />
    </template>
    <v-list-item-title>
      {{ tm("spcodeProjectLoad.menuItem") }}
    </v-list-item-title>
  </v-list-item>
</template>
