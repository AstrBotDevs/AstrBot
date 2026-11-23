<template>
  <button
    v-if="inWorkbench"
    type="button"
    class="workbench-link"
    @click="workbench?.open(part, action)"
  >
    <PanelsTopLeft :size="17" :stroke-width="1.6" />
    <span class="workbench-link-copy">
      <strong>{{ title }}</strong>
      <span>{{ tm("workbench.openView") }}</span>
    </span>
    <ArrowUpRight :size="14" :stroke-width="1.6" />
  </button>
  <PluginViewCard v-else :part="part" :is-dark="isDark" />
</template>

<script setup lang="ts">
import { ArrowUpRight, PanelsTopLeft } from "@lucide/vue";
import { computed, inject, onMounted } from "vue";
import type { MessagePart } from "@/composables/useMessages";
import { useI18n, useModuleI18n } from "@/i18n/composables";
import { viewActionKey, workbenchKey } from "@/utils/chatViews";
import { resolvePluginViewText } from "@/utils/pluginI18n";
import PluginViewCard from "./PluginViewCard.vue";

const props = defineProps<{ part: MessagePart; isDark?: boolean }>();
const workbench = inject(workbenchKey, undefined);
const action = inject(viewActionKey, undefined);
const { tm } = useModuleI18n("features/chat");
const { locale } = useI18n();
const title = computed(
  () =>
    props.part.title ||
    resolvePluginViewText(
      props.part.view_metadata?.i18n,
      locale.value,
      props.part.view_metadata || { name: props.part.name },
      "title",
    ),
);
const inWorkbench = computed(
  () => ["chat_workbench", "chat_workbench_with_launcher"].includes(String(props.part.target)) && workbench,
);
onMounted(() => {
  if (inWorkbench.value) workbench?.open(props.part, action, props.part.workbenchLive === true ? "live" : "history");
});
</script>

<style scoped>
.workbench-link {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  max-width: calc(100% - 8px);
  margin: 8px 0;
  margin-inline-end: 8px;
  padding: 8px 10px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.14);
  border-radius: var(--astrbot-radius-control);
  background: transparent;
  color: inherit;
  text-align: start;
  cursor: pointer;
}
.workbench-link:hover {
  background: rgba(var(--v-theme-on-surface), 0.04);
}
.workbench-link:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 3px;
}
.workbench-link-copy {
  display: grid;
  gap: 1px;
  min-width: 0;
}
.workbench-link-copy strong {
  font-size: 13px;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.workbench-link-copy span {
  font-size: 11px;
  opacity: 0.6;
}
</style>
