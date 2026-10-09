<script setup lang="ts">
import { computed, watch } from "vue";
import { RouterLink, RouterView, useRoute } from "vue-router";
import { useI18n } from "@/i18n/composables";
import { SIDEBAR_SUB_ITEMS } from "@/utils/sidebarSubItems";
import {
  getSidebarCustomization,
  resolveSubItemOrder,
} from "@/utils/sidebarCustomization";

const { t } = useI18n();
const route = useRoute();

const tabs = computed(() =>
  resolveSubItemOrder(
    "core.navigation.data",
    SIDEBAR_SUB_ITEMS["core.navigation.data"],
    getSidebarCustomization(),
  ).map((tab) => ({
    value: tab.value,
    label: t(tab.labelKey),
    routeName: tab.routeName,
    icon: tab.icon,
  })),
);

const activeTab = computed(() => String(route.meta.dataTab || "statistics"));

// Remember the last opened tab so the sidebar entry can reopen it.
watch(
  activeTab,
  (value) => {
    const tab = tabs.value.find((item) => item.value === value);
    if (tab) localStorage.setItem("data_last_tab", tab.routeName);
  },
  { immediate: true },
);
</script>

<template>
  <div class="data-workspace">
    <div class="data-tabs-scroll">
      <nav
        class="data-tabs"
        role="tablist"
        :aria-label="t('core.navigation.data')"
      >
        <RouterLink
          v-for="tab in tabs"
          :key="tab.value"
          v-slot="{ href, navigate }"
          custom
          :to="{ name: tab.routeName }"
        >
          <a
            :href="href"
            class="data-tab"
            :class="{ 'data-tab--active': activeTab === tab.value }"
            role="tab"
            :aria-selected="activeTab === tab.value"
            @click="navigate"
          >
            <component
              :is="tab.icon"
              :size="16"
              :stroke-width="1.8"
              aria-hidden="true"
            />
            <span>{{ tab.label }}</span>
          </a>
        </RouterLink>
      </nav>
    </div>

    <RouterView />
  </div>
</template>

<style scoped>
.data-workspace {
  min-width: 0;
  width: 100%;
}

.data-tabs-scroll {
  overflow-x: auto;
  padding: 4px 12px 8px;
  scrollbar-width: none;
}

.data-tabs-scroll::-webkit-scrollbar {
  display: none;
}

.data-tabs {
  align-items: center;
  display: inline-flex;
  gap: 2px;
  min-width: max-content;
}

.data-tab {
  align-items: center;
  border-radius: 8px;
  color: rgba(var(--v-theme-on-surface), 0.58);
  display: inline-flex;
  font-size: 0.8125rem;
  font-weight: 500;
  gap: 6px;
  height: 34px;
  padding: 0 12px;
  text-decoration: none;
}

.data-tab:hover {
  background: rgba(var(--v-theme-on-surface), 0.045);
  color: rgba(var(--v-theme-on-surface), 0.78);
}

.data-tab--active {
  background: rgba(var(--v-theme-on-surface), 0.065);
  color: rgba(var(--v-theme-on-surface), 0.86);
}

.data-tab--active:hover {
  background: rgba(var(--v-theme-on-surface), 0.09);
  color: rgba(var(--v-theme-on-surface), 0.9);
}

@media (max-width: 600px) {
  .data-tabs-scroll {
    padding-inline: 4px;
  }

  .data-tab {
    padding-inline: 11px;
  }
}
</style>
