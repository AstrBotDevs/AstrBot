<script setup lang="ts">
import { ArrowUpRight, PanelsTopLeft } from "@lucide/vue";
import { onMounted, ref } from "vue";
import { fetchWithAuth } from "@/api/http";
import { useI18n, useModuleI18n } from "@/i18n/composables";
import type { WorkbenchView } from "@/utils/chatViews";
import { resolvePluginViewText } from "@/utils/pluginI18n";

defineEmits<{ open: [view: WorkbenchView] }>();
const { locale } = useI18n();
const { tm } = useModuleI18n("features/chat");
const views = ref<WorkbenchView[]>([]);
const loading = ref(true);
const failed = ref(false);
async function load() {
  loading.value = true;
  failed.value = false;
  try {
    const response = await fetchWithAuth("/api/v1/chat/workbench/views");
    if (!response.ok) throw new Error("Workbench catalog unavailable");
    views.value = (await response.json()).data;
  } catch {
    failed.value = true;
  } finally {
    loading.value = false;
  }
}
onMounted(load);
</script>

<template>
  <section class="workbench-launcher-page">
    <h1>{{ tm("workbench.newTab") }}</h1>
    <p>{{ tm("workbench.chooseView") }}</p>
    <v-progress-linear v-if="loading" indeterminate color="primary" />
    <div v-else-if="failed" role="status">
      <p>{{ tm("workbench.loadError") }}</p>
      <v-btn variant="text" @click="load">{{ tm("workbench.retry") }}</v-btn>
    </div>
    <p v-else-if="!views.length">{{ tm("workbench.empty") }}</p>
    <button
      v-for="view in views"
      :key="`${view.plugin_name}/${view.name}`"
      type="button"
      class="view-choice"
      @click="$emit('open', view)"
    >
      <PanelsTopLeft :size="20" :stroke-width="1.5" />
      <span class="view-copy">
        <strong>{{ resolvePluginViewText(view.i18n, locale, view, "title") }}</strong>
        <span v-if="resolvePluginViewText(view.i18n, locale, view, 'description')">{{ resolvePluginViewText(view.i18n, locale, view, "description") }}</span>
        <small>{{ view.display_name }}</small>
      </span>
      <ArrowUpRight :size="16" />
    </button>
  </section>
</template>

<style scoped>
.workbench-launcher-page {
  height: 100%;
  overflow: auto;
  padding: 32px 24px;
}
h1 {
  font-size: 22px;
  font-weight: 600;
  letter-spacing: -0.03em;
}
p {
  color: rgba(var(--v-theme-on-surface), 0.55);
  font-size: 13px;
  margin: 8px 0 28px;
}
.view-choice {
  width: 100%;
  display: flex;
  align-items: flex-start;
  gap: 14px;
  padding: 18px 12px;
  text-align: start;
  border-radius: var(--astrbot-radius-control);
  color: inherit;
}
.view-choice:hover {
  background: rgba(var(--v-theme-on-surface), 0.05);
}
.view-choice:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
}
.view-copy {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.view-copy strong {
  font-size: 14px;
  font-weight: 500;
}
.view-copy span,
.view-copy small {
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.55);
}
</style>
