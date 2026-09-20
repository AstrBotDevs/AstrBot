<script setup lang="ts">
import { computed } from "vue";
import { RouterLink, RouterView, useRoute } from "vue-router";
import { useI18n } from "@/i18n/composables";

const { t } = useI18n();
const route = useRoute();

const tabs = computed(() => [
  {
    value: "installed",
    label: t("core.navigation.extensionTabs.installed"),
    icon: "mdi-puzzle-outline",
    routeName: "Extensions",
  },
  {
    value: "skills",
    label: t("core.navigation.extensionTabs.skills"),
    icon: "mdi-lightning-bolt-outline",
    routeName: "ExtensionSkills",
  },
  {
    value: "mcp",
    label: t("core.navigation.extensionTabs.mcp"),
    icon: "mdi-server-network",
    routeName: "ExtensionMcp",
  },
  {
    value: "components",
    label: t("core.navigation.extensionTabs.components"),
    icon: "mdi-wrench-outline",
    routeName: "ExtensionComponents",
  },
]);

const activeTab = computed(() =>
  String(route.meta.extensionTab || "installed"),
);
</script>

<template>
  <div class="plugin-workspace">
    <div class="plugin-tabs-scroll">
      <nav
        class="plugin-tabs"
        role="tablist"
        :aria-label="t('core.navigation.extension')"
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
            class="plugin-tab"
            :class="{ 'plugin-tab--active': activeTab === tab.value }"
            role="tab"
            :aria-selected="activeTab === tab.value"
            @click="navigate"
          >
            <v-icon :icon="tab.icon" size="16" />
            <span>{{ tab.label }}</span>
          </a>
        </RouterLink>
      </nav>
    </div>

    <RouterView v-slot="{ Component, route: childRoute }">
      <component
        :is="Component"
        :key="String(
          childRoute.meta.pluginView ||
            childRoute.meta.extensionTab ||
            childRoute.name,
        )"
      />
    </RouterView>
  </div>
</template>

<style scoped>
.plugin-workspace {
  min-width: 0;
  width: 100%;
}

.plugin-tabs-scroll {
  overflow-x: auto;
  padding: 4px 12px 8px;
  scrollbar-width: none;
}

.plugin-tabs-scroll::-webkit-scrollbar {
  display: none;
}

.plugin-tabs {
  align-items: center;
  display: inline-flex;
  gap: 2px;
  min-width: max-content;
}

.plugin-tab {
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

.plugin-tab:hover {
  background: rgba(var(--v-theme-on-surface), 0.045);
  color: rgba(var(--v-theme-on-surface), 0.78);
}

.plugin-tab--active {
  background: rgba(var(--v-theme-on-surface), 0.065);
  color: rgba(var(--v-theme-on-surface), 0.86);
}

.plugin-tab--active:hover {
  background: rgba(var(--v-theme-on-surface), 0.09);
  color: rgba(var(--v-theme-on-surface), 0.9);
}

@media (max-width: 600px) {
  .plugin-tabs-scroll {
    padding-inline: 4px;
  }

  .plugin-tab {
    padding-inline: 11px;
  }
}
</style>
