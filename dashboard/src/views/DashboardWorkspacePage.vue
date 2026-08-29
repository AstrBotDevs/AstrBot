<script setup lang="ts">
import { computed } from 'vue';
import { RouterLink, RouterView, useRoute } from 'vue-router';
import { useI18n } from '@/i18n/composables';

const { t } = useI18n();
const route = useRoute();

const tabs = computed(() => [
  {
    value: 'statistics',
    label: t('core.navigation.dataTabs.statistics'),
    routeName: 'Stats',
    icon: 'mdi-chart-line',
  },
  {
    value: 'conversations',
    label: t('core.navigation.dataTabs.conversations'),
    routeName: 'Conversation',
    icon: 'mdi-message-text-outline',
  },
  {
    value: 'logs',
    label: t('core.navigation.dataTabs.logs'),
    routeName: 'Logs',
    icon: 'mdi-console',
  },
  {
    value: 'trace',
    label: t('core.navigation.dataTabs.trace'),
    routeName: 'Trace',
    icon: 'mdi-timeline-text-outline',
  },
]);

const activeTab = computed(() => String(route.meta.dataTab || 'statistics'));
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
            <v-icon size="16" aria-hidden="true">{{ tab.icon }}</v-icon>
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
