<template>
  <section class="system-status-bar" :aria-label="tm('system.title')">
    <span class="system-title">{{ tm('system.title') }}</span>
    <div v-for="item in systemItems" :key="item.key" class="system-metric" :class="`system-metric--${item.key}`" :title="systemUnavailable ? tm('system.unavailable') : tm('system.scope')">
      <component :is="item.icon" :size="18" aria-hidden="true" />
      <span>{{ tm(`system.${item.key}`) }}</span>
      <strong>{{ systemUnavailable ? '—' : item.value }}</strong>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { Server, Cpu, MemoryStick, HardDrive } from '@lucide/vue';
import type { StatsSystemResources } from '@/api/generated/openapi-v1';
import { useI18n, useModuleI18n } from '@/i18n/composables';

const props = defineProps<{ system?: StatsSystemResources; systemUnavailable?: boolean }>();
const { tm } = useModuleI18n('features/welcome');
const { locale } = useI18n();
const systemItems = computed(() => {
  const system = props.system;
  const seconds = system?.uptime_seconds ?? 0;
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor(seconds % 86400 / 3600);
  const minutes = Math.floor(seconds % 3600 / 60);
  const items = [
    { key: 'uptime', icon: Server, value: !system ? '—' : days > 0
      ? tm('system.daysHours', { days, hours })
      : tm('system.hoursMinutes', { hours, minutes }) },
    { key: 'cpu', icon: Cpu, value: system ? `${system.cpu_percent.toLocaleString(locale.value, { maximumFractionDigits: 1 })}%` : '—' },
  ];
  for (const [key, icon] of [['memory', MemoryStick], ['disk', HardDrive]] as const) {
    const usage = system?.[key];
    const format = new Intl.NumberFormat(locale.value, { maximumFractionDigits: 1 });
    items.push({ key, icon, value: usage
      ? `${format.format(usage.used / 1024 ** 3)} / ${format.format(usage.total / 1024 ** 3)} GiB (${format.format(usage.percent)}%)`
      : '—' });
  }
  return items;
});

</script>

<style scoped>
.system-status-bar { display: flex; flex-wrap: wrap; align-items: center; gap: 16px; padding: 12px 16px; margin-bottom: 20px; border: 1px solid rgba(var(--v-theme-primary), .08); border-radius: 18px; background: rgb(var(--v-theme-surface)); font-size: 12px; }
.system-title { font-size: 13px; font-weight: 600; white-space: nowrap; }
.system-metric { display: flex; align-items: center; gap: 6px; white-space: nowrap; border-inline-start: 1px solid rgba(var(--v-theme-on-surface), .08); padding-inline-start: 16px; flex: 1 0 auto; }
.system-metric svg { color: rgba(var(--v-theme-on-surface), .55); flex-shrink: 0; }
.system-metric strong { font-weight: 600; font-variant-numeric: tabular-nums; }
.system-metric--cpu { flex: 0.6 0 auto; }
@media (max-width: 700px) {
  .system-status-bar { gap: 12px 20px; }
  .system-title { flex-basis: 100%; }
  .system-metric { border: 0; padding-inline-start: 0; }
}
</style>
