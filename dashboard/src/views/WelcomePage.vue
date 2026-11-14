<template>
  <div class="welcome-page">
    <header class="overview-header">
      <div>
        <h1 class="overview-greeting">{{ greetingText }} <span>{{ greetingEmoji }}</span></h1>
      </div>
      <OverviewStatus />
    </header>

    <v-alert v-if="statsFailed" type="warning" variant="tonal" class="mb-4">
      {{ tm('metrics.loadFailed') }}
      <template #append><v-btn variant="text" :loading="statsLoading" @click="loadOverview">{{ tm('health.refresh') }}</v-btn></template>
    </v-alert>
    <section class="metrics-grid" :aria-label="tm('metrics.title')" :aria-busy="statsLoading">
      <article v-for="metric in metrics" :key="metric.key" class="metric-card" :class="`metric-card--${metric.tone}`">
        <div class="metric-icon"><v-icon size="24">{{ metric.icon }}</v-icon></div>
        <div class="metric-content">
          <h2 class="metric-label">{{ tm(`metrics.${metric.key}`) }}</h2>
          <div class="metric-value" :title="metric.exact">{{ metric.value }}</div>
          <div class="metric-comparison">
            <span :class="metric.direction ? 'text-success' : 'text-medium-emphasis'">
              <v-icon v-if="metric.direction" size="18">{{ metric.direction > 0 ? 'mdi-arrow-up' : 'mdi-arrow-down' }}</v-icon>
              {{ metric.change }}
            </span>
            <span class="text-medium-emphasis">{{ tm('metrics.vsYesterday') }}</span>
          </div>
        </div>
      </article>
    </section>

    <OverviewSystemStats :system="overview?.system" :system-unavailable="statsFailed" />

    <div class="overview-panels">
      <section class="overview-panel">
        <div class="panel-header">
          <div class="panel-icon"><v-icon size="22">mdi-rocket-launch-outline</v-icon></div>
          <div class="panel-heading">
            <h2>{{ tm('onboard.title') }}</h2>
            <p>{{ tm('onboard.subtitle') }}</p>
          </div>
        </div>
        <ol class="onboarding-steps">
          <li v-for="(step, index) in onboardingSteps" :key="step.key" class="onboarding-step">
            <div class="step-marker" :class="{ 'step-marker--completed': step.completed }">
              <v-icon v-if="step.completed" size="16">mdi-check</v-icon>
              <span v-else>{{ index + 1 }}</span>
            </div>
            <div class="step-copy">
              <h3>{{ tm(`onboard.${step.key}Title`) }}</h3>
              <p>{{ tm(`onboard.${step.key}Desc`) }}</p>
            </div>
            <v-btn :color="step.completed ? 'success' : 'primary'" variant="tonal" rounded="pill" size="small"
              :prepend-icon="step.completed ? 'mdi-check' : undefined" :append-icon="step.completed ? undefined : 'mdi-arrow-right'"
              :loading="step.key === 'step2' && loadingPlatformDialog" @click="step.action">
              {{ tm(step.completed ? 'onboard.completed' : 'onboard.configure') }}
            </v-btn>
          </li>
        </ol>
      </section>

      <section class="overview-panel resources-panel">
        <div class="panel-header">
          <div class="panel-icon"><v-icon size="22">mdi-book-open-outline</v-icon></div>
          <div class="panel-heading">
            <h2>{{ tm('resources.title') }}</h2>
            <p>{{ tm('resources.subtitle') }}</p>
          </div>
        </div>
        <div class="resources-grid">
          <a v-for="resource in resources" :key="resource.key" :href="resource.href" target="_blank" rel="noopener noreferrer"
            class="resource-card" :class="`resource-card--${resource.key}`">
            <v-icon class="resource-external" size="18">mdi-open-in-new</v-icon>
            <v-icon class="resource-icon" size="26">{{ resource.icon }}</v-icon>
            <h3>{{ resource.key === 'github' ? 'GitHub' : tm(`resources.${resource.key}Title`) }}</h3>
            <p>{{ tm(`resources.${resource.key}Desc`) }}</p>
          </a>
        </div>
      </section>
    </div>

    <section v-if="showAnnouncement" class="overview-panel announcement-panel">
      <h2 class="text-h3 font-weight-bold mb-4">{{ tm('announcement.title') }}</h2>
      <MarkdownRender :content="welcomeAnnouncement" :typewriter="false" class="welcome-announcement-markdown markdown-content" />
    </section>

    <v-dialog v-model="showComputerAccessDialog" max-width="540">
      <v-card>
        <v-card-title class="text-h3 pa-4 pb-0 pl-6">{{ tm('onboard.step3Title') }}</v-card-title>
        <v-card-text class="pa-6">
          <p class="text-body-2 text-medium-emphasis mb-5">{{ tm('onboard.step3Desc') }}</p>
          <v-select v-model="computerAccessRuntime" :items="computerAccessOptions" item-title="title" item-value="value"
            :label="tm('onboard.step3SelectLabel')" :loading="savingComputerAccess" :disabled="savingComputerAccess"
            hide-details density="comfortable" variant="outlined" />
          <v-btn variant="text" color="primary" class="mt-3" @click="showComputerAccessHelpDialog = true">{{ tm('onboard.learnMore') }}</v-btn>
        </v-card-text>
        <v-card-actions class="px-6 pb-4">
          <v-spacer />
          <v-btn variant="tonal" color="primary" @click="showComputerAccessDialog = false">{{ tm('onboard.step3HelpClose') }}</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <AddNewPlatform v-model:show="showAddPlatformDialog" :metadata="platformMetadata" :config_data="platformConfigData"
      @refresh-config="loadPlatformConfigBase" />
    <ProviderConfigDialog v-model="showProviderDialog" />
    <v-dialog v-model="showComputerAccessHelpDialog" max-width="640">
      <v-card>
        <v-card-title class="text-h3 pa-4 pb-0 pl-6">
          {{ tm('onboard.step3HelpTitle') }}
        </v-card-title>
        <v-card-text>
          <ol class="computer-access-help-list">
            <li>{{ tm('onboard.step3HelpItem1') }}</li>
            <li>{{ tm('onboard.step3HelpItem2') }}</li>
            <li>{{ tm('onboard.step3HelpItem3') }}</li>
          </ol>
        </v-card-text>
        <v-card-actions class="px-6 pb-4">
          <v-spacer />
          <v-btn color="primary" variant="text" @click="showComputerAccessHelpDialog = false">
            {{ tm('onboard.step3HelpClose') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch, onMounted, onUnmounted } from 'vue';
import axios from 'axios';
import OverviewStatus from '@/components/overview/OverviewStatus.vue';
import OverviewSystemStats from '@/components/overview/OverviewSystemStats.vue';
import type { StatsDailyUsage, StatsSystemResources as SystemStats } from '@/api/generated/openapi-v1';
import AddNewPlatform from '@/components/platform/AddNewPlatform.vue';
import ProviderConfigDialog from '@/components/chat/ProviderConfigDialog.vue';
import { configProfileApi, providerApi, systemConfigApi, statsApi } from '@/api/v1';
import { useI18n, useModuleI18n } from '@/i18n/composables';
import { useToast } from '@/utils/toast';
import { MarkdownRender } from 'markstream-vue';
import 'markstream-vue/index.css';

type StepState = 'pending' | 'completed' | 'skipped';
type ComputerAccessRuntime = 'local' | 'none';

const { tm } = useModuleI18n('features/welcome');
const { locale } = useI18n();
const { success: showSuccess, error: showError } = useToast();

const showComputerAccessDialog = ref(false);
const overview = ref<{ daily_usage: { today: StatsDailyUsage; yesterday: StatsDailyUsage }; system: SystemStats } | null>(null);
const statsLoading = ref(false);
const statsFailed = ref(false);
let overviewTimer: ReturnType<typeof setInterval>;
const metrics = computed(() => [
  { key: 'tokens' as const, icon: 'mdi-layers-triple-outline', tone: 'primary' },
  { key: 'messages' as const, icon: 'mdi-chat-outline', tone: 'info' },
  { key: 'active_sessions' as const, icon: 'mdi-account-multiple-outline', tone: 'success' },
].map(metric => {
  const current = overview.value?.daily_usage.today[metric.key];
  const previous = overview.value?.daily_usage.yesterday[metric.key];
  const delta = current !== undefined && previous !== undefined ? current - previous : 0;
  const percentage = previous ? delta / previous * 100 : null;
  return {
    ...metric,
    exact: current?.toLocaleString(locale.value),
    value: current === undefined ? '—' : new Intl.NumberFormat(locale.value, {
      notation: metric.key === 'tokens' && current >= 100000 ? 'compact' : 'standard',
      maximumFractionDigits: 2,
    }).format(current),
    direction: delta === 0 ? 0 : Math.sign(delta),
    change: current === undefined ? '—' : percentage !== null
      ? `${percentage > 0 ? '+' : ''}${percentage.toLocaleString(locale.value, { maximumFractionDigits: 1 })}%`
      : delta > 0 ? tm('metrics.newActivity') : '0%',
  };
}));
const resources = [
  { key: 'github', icon: 'mdi-github', href: 'https://github.com/AstrBotDevs/AstrBot/' },
  { key: 'docs', icon: 'mdi-file-document-outline', href: 'https://docs.astrbot.app' },
  { key: 'afdian', icon: 'mdi-heart-outline', href: 'https://afdian.com/a/astrbot_team' },
];
const onboardingSteps = computed(() => [
  { key: 'step1', completed: providerStepState.value === 'completed', action: openProviderDialog },
  { key: 'step2', completed: platformStepState.value === 'completed', action: openPlatformDialog },
  { key: 'step3', completed: computerAccessStepState.value === 'completed', action: () => { showComputerAccessDialog.value = true; } },
]);

async function loadOverview() {
  if (statsLoading.value) return;
  statsLoading.value = true;
  try {
    const response = await statsApi.get(undefined, 'daily_usage,system');
    if (response.data.status !== 'ok') throw new Error(response.data.message || 'Failed to load overview');
    overview.value = response.data.data;
    statsFailed.value = false;
  } catch (error) {
    statsFailed.value = true;
    console.error('Failed to load overview metrics:', error);
  } finally {
    statsLoading.value = false;
  }
}

const showAddPlatformDialog = ref(false);
const showProviderDialog = ref(false);
const showComputerAccessHelpDialog = ref(false);
const loadingPlatformDialog = ref(false);

const platformMetadata = ref<Record<string, any>>({});
const platformConfigData = ref<Record<string, any>>({});
const platformCountBeforeOpen = ref(0);
const providerCountBeforeOpen = ref(0);

const platformStepState = ref<StepState>('pending');
const providerStepState = ref<StepState>('pending');
const computerAccessStepState = ref<StepState>('pending');
const computerAccessRuntime = ref<ComputerAccessRuntime>('none');
const savedComputerAccessRuntime = ref<ComputerAccessRuntime>('none');
const savingComputerAccess = ref(false);
const welcomeAnnouncementRaw = ref<unknown>(null);

function resolveWelcomeAnnouncement(raw: unknown, currentLocale: string) {
  if (typeof raw === 'string') {
    return raw.trim();
  }

  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
    return '';
  }

  const localeMap = raw as Record<string, unknown>;
  const normalized = currentLocale.replace('-', '_');
  const preferredKeys =
    normalized.startsWith('zh')
      ? [normalized, 'zh_CN', 'zh-CN', 'zh', 'en_US', 'en-US', 'en']
      : [normalized, 'en_US', 'en-US', 'en', 'zh_CN', 'zh-CN', 'zh'];

  for (const key of preferredKeys) {
    const value = localeMap[key];
    if (typeof value === 'string' && value.trim().length > 0) {
      return value.trim();
    }
  }

  return '';
}

const welcomeAnnouncement = computed(() =>
  resolveWelcomeAnnouncement(welcomeAnnouncementRaw.value, locale.value)
);
const showAnnouncement = computed(() => welcomeAnnouncement.value.length > 0);

const springFestivalDates: Record<number, string> = {
  2025: '01-29',
  2026: '02-17',
  2027: '02-06',
  2028: '01-26',
  2029: '02-13',
  2030: '02-03'
}

function isSpringFestival() {
  const now = new Date();
  const year = now.getFullYear();
  const dateStr = springFestivalDates[year];

  if (!dateStr) return false;

  const [month, day] = dateStr.split('-').map(Number);
  const festivalDate = new Date(year, month - 1, day);

  const start = new Date(festivalDate);
  start.setDate(festivalDate.getDate() - 5);

  const end = new Date(festivalDate);
  end.setDate(festivalDate.getDate() + 5);

  // start of day for comparison
  const nowTime = now.setHours(0, 0, 0, 0);
  const startTime = start.setHours(0, 0, 0, 0);
  const endTime = end.setHours(0, 0, 0, 0);

  return nowTime >= startTime && nowTime <= endTime;
}

function isExactSpringFestivalDay() {
  const now = new Date();
  const year = now.getFullYear();
  const dateStr = springFestivalDates[year];

  if (!dateStr) return false;

  const [month, day] = dateStr.split('-').map(Number);
  const festivalDate = new Date(year, month - 1, day);

  const nowTime = new Date(now).setHours(0, 0, 0, 0);
  const festivalTime = festivalDate.setHours(0, 0, 0, 0);

  return nowTime === festivalTime;
}

const greetingEmoji = computed(() => {
  if (isExactSpringFestivalDay()) {
    return '🧨';
  }
  const hour = new Date().getHours();
  if (hour >= 0 && hour < 5) {
    return '😴';
  }
  return '👋';
});

const greetingText = computed(() => {
  if (isSpringFestival()) {
    return tm('greeting.newYear');
  }
  const hour = new Date().getHours();
  if (hour < 12) return tm('greeting.morning');
  if (hour < 18) return tm('greeting.afternoon');
  return tm('greeting.evening');
});

async function loadPlatformConfigBase() {
  const res = await systemConfigApi.runtime();
  const payload = (res.data.data || {}) as any;
  platformMetadata.value = payload.metadata || {};
  platformConfigData.value = payload.config || {};
}

async function fetchDefaultConfig() {
  const res = await configProfileApi.get('default');
  return (res.data?.data as any)?.config || {};
}

function getChatProvidersFromTemplatePayload(payload: any) {
  const providers = payload?.providers || [];
  const sources = payload?.provider_sources || [];
  const sourceMap = new Map();
  sources.forEach((s: any) => sourceMap.set(s.id, s.provider_type));

  return providers.filter((provider: any) => {
    if (provider.provider_type) {
      return provider.provider_type === 'chat_completion';
    }
    if (provider.provider_source_id) {
      const type = sourceMap.get(provider.provider_source_id);
      if (type === 'chat_completion') return true;
    }
    return String(provider.type || '').includes('chat_completion');
  });
}

async function fetchChatProviders() {
  const response = await providerApi.schema();
  if (response.data.status !== 'ok') {
    throw new Error(response.data.message || tm('onboard.providerLoadFailed'));
  }
  return getChatProvidersFromTemplatePayload(response.data.data);
}

function pickDefaultProviderId(providers: any[]) {
  if (!providers.length) return '';
  const enabledProvider = providers.find((provider) => provider.enable !== false);
  return (enabledProvider || providers[0]).id || '';
}

async function syncDefaultConfigProviderIfNeeded() {
  const providers = await fetchChatProviders();
  if (!providers.length) return;

  const targetProviderId = pickDefaultProviderId(providers);
  if (!targetProviderId) return;

  const configData = await fetchDefaultConfig();
  if (configData?.agent?.runtime !== 'astrbot') {
    return;
  }
  const modelConfig = configData.agent.config?.model;
  if (!modelConfig) return;

  if (modelConfig.provider_id === targetProviderId) return;

  modelConfig.provider_id = targetProviderId;

  const updateRes = await configProfileApi.update('default', configData);
  if (updateRes.data.status !== 'ok') {
    throw new Error(updateRes.data.message || tm('onboard.providerUpdateFailed'));
  }

  showSuccess(tm('onboard.providerDefaultUpdated', { id: targetProviderId }));
}

function normalizeComputerAccessRuntime(runtime: unknown): ComputerAccessRuntime {
  return runtime === 'local' || runtime === 'sandbox' ? 'local' : 'none';
}

function syncComputerAccessRuntime(configData: any) {
  const providerSettings = configData?.provider_settings || {};
  const currentRuntime = providerSettings?.computer_use_runtime;
  const normalizedRuntime = normalizeComputerAccessRuntime(currentRuntime);

  computerAccessRuntime.value = normalizedRuntime;
  savedComputerAccessRuntime.value = normalizedRuntime;
  computerAccessStepState.value =
    currentRuntime === 'local' || currentRuntime === 'none' || currentRuntime === 'sandbox'
      ? 'completed'
      : 'pending';
}

const computerAccessOptions = computed(() => [
  { title: tm('onboard.step3Allow'), value: 'local' },
  { title: tm('onboard.step3Deny'), value: 'none' }
]);

async function saveComputerAccessRuntime() {
  savingComputerAccess.value = true;
  try {
    const configData = await fetchDefaultConfig();
    if (!configData.provider_settings) {
      configData.provider_settings = {};
    }

    configData.provider_settings.computer_use_runtime = computerAccessRuntime.value;

    const updateRes = await configProfileApi.update('default', configData);
    if (updateRes.data.status !== 'ok') {
      throw new Error(updateRes.data.message || tm('onboard.computerAccessUpdateFailed'));
    }

    savedComputerAccessRuntime.value = computerAccessRuntime.value;
    computerAccessStepState.value = 'completed';
    showSuccess(
      tm(
        computerAccessRuntime.value === 'local'
          ? 'onboard.computerAccessAllowed'
          : 'onboard.computerAccessDenied'
      )
    );
  } catch (err: any) {
    computerAccessRuntime.value = savedComputerAccessRuntime.value;
    showError(err?.response?.data?.message || err?.message || tm('onboard.computerAccessUpdateFailed'));
  } finally {
    savingComputerAccess.value = false;
  }
}

async function loadWelcomeAnnouncement() {
  try {
    const res = await axios.get('https://cloud.astrbot.app/api/v1/announcement');
    welcomeAnnouncementRaw.value = res?.data?.data?.notice?.welcome_page ?? null;
  } catch (e) {
    welcomeAnnouncementRaw.value = null;
    console.error(e);
  }
}

onMounted(async () => {
  void loadWelcomeAnnouncement();
  void loadOverview();
  overviewTimer = setInterval(() => { if (!document.hidden) void loadOverview(); }, 30000);

  try {
    await loadPlatformConfigBase();
    if ((platformConfigData.value.platform || []).length > 0) {
      platformStepState.value = 'completed';
    }
  } catch (e) {
    console.error(e);
  }

  try {
    const providers = await fetchChatProviders();
    if (providers.length > 0) {
      providerStepState.value = 'completed';
    }
  } catch (e) {
    console.error(e);
  }

  try {
    const defaultConfig = await fetchDefaultConfig();
    syncComputerAccessRuntime(defaultConfig);
  } catch (e) {
    console.error(e);
  }
});

onUnmounted(() => clearInterval(overviewTimer));

async function openPlatformDialog() {
  loadingPlatformDialog.value = true;
  try {
    await loadPlatformConfigBase();
    platformCountBeforeOpen.value = (platformConfigData.value.platform || []).length;
    showAddPlatformDialog.value = true;
  } catch (err: any) {
    showError(err?.response?.data?.message || err?.message || tm('onboard.platformLoadFailed'));
  } finally {
    loadingPlatformDialog.value = false;
  }
}

async function openProviderDialog() {
  try {
    const providers = await fetchChatProviders();
    providerCountBeforeOpen.value = providers.length;
    showProviderDialog.value = true;
  } catch (err: any) {
    showError(err?.response?.data?.message || err?.message || tm('onboard.providerLoadFailed'));
  }
}

watch(showAddPlatformDialog, async (visible, wasVisible) => {
  if (!wasVisible || visible) return;
  try {
    await loadPlatformConfigBase();
    const newCount = (platformConfigData.value.platform || []).length;
    if (newCount > platformCountBeforeOpen.value) {
      platformStepState.value = 'completed';
    }
  } catch (err: any) {
    showError(err?.response?.data?.message || err?.message || tm('onboard.platformLoadFailed'));
  }
});

watch(showProviderDialog, async (visible, wasVisible) => {
  if (!wasVisible || visible) return;
  try {
    const providers = await fetchChatProviders();
    if (providers.length > providerCountBeforeOpen.value) {
      providerStepState.value = 'completed';
      await syncDefaultConfigProviderIfNeeded();
    }
  } catch (err: any) {
    showError(err?.response?.data?.message || err?.message || tm('onboard.providerUpdateFailed'));
  }
});

watch(computerAccessRuntime, async (value, oldValue) => {
  if (value === oldValue) return;
  if (value === savedComputerAccessRuntime.value) return;
  if (savingComputerAccess.value) return;

  try {
    await saveComputerAccessRuntime();
  } catch {
    computerAccessRuntime.value = savedComputerAccessRuntime.value;
  }
});
</script>

<style scoped>
.welcome-page { max-width: 1560px; margin: 0 auto; padding: 24px 20px; }
.overview-header { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 24px; }
.overview-greeting { font-size: clamp(22px, 2vw, 26px); line-height: 1.3; font-weight: 700; letter-spacing: -.4px; overflow-wrap: anywhere; }
.overview-greeting span { display: inline-block; margin-inline-start: 8px; }
.metrics-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; margin-bottom: 20px; }
.metric-card { --metric-color: var(--v-theme-primary); display: flex; align-items: flex-start; gap: 16px; padding: 20px; border-radius: 18px; background: rgba(var(--metric-color), .07); }
.metric-card--info { --metric-color: var(--v-theme-info); }
.metric-card--success { --metric-color: var(--v-theme-success); }
.metric-icon, .panel-icon { display: grid; place-items: center; flex-shrink: 0; width: 44px; height: 44px; border-radius: 50%; background: rgba(var(--metric-color, var(--v-theme-primary)), .09); color: rgb(var(--metric-color, var(--v-theme-primary))); }
.metric-content { min-width: 0; }
.metric-label { font-size: 14px; font-weight: 600; line-height: 1.5; }
.metric-value { font-size: clamp(26px, 2.4vw, 30px); line-height: 1.25; font-weight: 700; margin: 6px 0; letter-spacing: -1px; font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }
.metric-comparison { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; font-size: 13px; }
.overview-panels { display: grid; grid-template-columns: 1.08fr 1fr; gap: 20px; }
.overview-panel { min-width: 0; padding: 20px; border: 1px solid rgba(var(--v-theme-primary), .08); border-radius: 18px; background: rgb(var(--v-theme-surface)); box-shadow: 0 3px 16px rgba(var(--v-theme-primary), .025); }
.panel-header { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.panel-heading { flex: 1; min-width: 0; }
.panel-heading h2 { font-size: 18px; line-height: 1.4; font-weight: 700; }
.panel-heading p, .step-copy p, .resource-card p { color: rgba(var(--v-theme-on-surface), .62); font-size: 13px; line-height: 1.6; margin: 4px 0 0; }
.panel-icon { width: 40px; height: 40px; }
.onboarding-steps { list-style: none; padding: 0; margin: 0; }
.onboarding-step { position: relative; display: flex; align-items: center; gap: 12px; padding: 10px 0; min-height: 66px; }
.onboarding-step:not(:last-child)::after { position: absolute; content: ''; top: calc(50% + 13px); bottom: calc(-50% + 13px); left: 13px; width: 2px; background: rgba(var(--v-theme-primary), .13); }
.step-marker { display: grid; place-items: center; flex-shrink: 0; width: 28px; height: 28px; border-radius: 50%; color: rgb(var(--v-theme-on-primary)); background: rgb(var(--v-theme-primary)); font-size: 13px; z-index: 1; }
.step-marker--completed { background: rgb(var(--v-theme-success)); color: #fff; }
.step-copy { flex: 1; min-width: 0; }
.step-copy h3 { font-size: 14px; line-height: 1.5; font-weight: 600; }
.onboarding-step .v-btn { flex-shrink: 0; font-size: 12px; letter-spacing: 0; }
.resources-panel { display: flex; flex-direction: column; }
.resources-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin: auto 0; }
.resource-card { position: relative; display: flex; flex-direction: column; align-items: flex-start; padding: 18px 14px; border-radius: 16px; background: rgba(var(--v-theme-primary), .06); color: rgb(var(--v-theme-on-surface)); text-decoration: none; transition: background .2s; }
.resource-card:hover, .resource-card:focus-visible { background: rgba(var(--v-theme-primary), .13); }
.resource-card:focus-visible { outline: 2px solid rgb(var(--v-theme-primary)); outline-offset: 3px; }
.resource-card--github { background: rgba(var(--v-theme-info), .06); }
.resource-card--afdian { background: rgba(var(--v-theme-error), .05); }
.resource-external { position: absolute; top: 12px; right: 12px; opacity: .65; }
.resource-icon { margin: 6px 0 14px; color: rgb(var(--v-theme-primary)); }
.resource-card--github .resource-icon { color: rgb(var(--v-theme-on-surface)); }
.resource-card--afdian .resource-icon { color: rgb(var(--v-theme-error)); }
.resource-card h3 { font-size: 15px; font-weight: 600; }
.announcement-panel { margin-top: 24px; }
.welcome-announcement-markdown { line-height: 1.7; }
.computer-access-help-list { margin: 0; padding-left: 1.25rem; }
@media (max-width: 1200px) {
  .welcome-page { padding: 24px 16px; }
  .metric-card { padding: 18px; gap: 12px; }
  .metric-icon { width: 40px; height: 40px; }
  .overview-panels { grid-template-columns: 1fr; }
  .resources-grid { margin: 0; }
}
@media (max-width: 700px) {
  .welcome-page { padding: 20px 4px; }
  .overview-header { flex-direction: column; align-items: flex-start; gap: 16px; margin-bottom: 20px; }
  .metrics-grid { grid-template-columns: 1fr; gap: 12px; margin-bottom: 20px; }
  .metric-card { padding: 16px; border-radius: 16px; }
  .metric-value { margin: 6px 0; }
  .overview-panel { padding: 16px; border-radius: 16px; }
  .panel-header { flex-wrap: wrap; gap: 12px; margin-bottom: 20px; }
  .panel-heading h2 { font-size: 18px; }
  .onboarding-step { display: grid; grid-template-columns: 28px minmax(0, 1fr); gap: 8px 12px; padding-block: 12px; }
  .onboarding-step .v-btn { grid-column: 2; justify-self: start; }
  .onboarding-step:not(:last-child)::after { top: 40px; bottom: -12px; }
  .resources-grid { grid-template-columns: 1fr; }
  .resource-card { padding: 16px; }
  .resource-icon { margin: 0 0 12px; }
}
</style>
