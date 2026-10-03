<template>
  <section class="onboarding-setup">
    <div ref="scrollContainer" class="guide-scroll" :class="{ 'guide-scroll--complete': completed }">
    <OnboardingWelcome v-if="completed" />
    <div v-else-if="applying" class="guide-content" :aria-busy="busy">
      <div class="guide-heading">
        <h2>{{ tm('guide.applyTitle') }}</h2>
        <p class="text-body-2 text-medium-emphasis mt-3">{{ tm('guide.applyHint') }}</p>
      </div>
      <p class="text-body-2 mb-3" role="status">{{ tm('guide.applyProgress', { done: applyTasks.filter(task => ['done', 'skipped'].includes(task.status)).length, total: applyTasks.length }) }}</p>
      <v-progress-linear :model-value="applyTasks.filter(task => ['done', 'skipped'].includes(task.status)).length / applyTasks.length * 100" color="primary" :aria-label="tm('guide.applyTitle')" />
      <v-list class="bg-transparent" lines="two">
        <v-list-item v-for="task in applyTasks" :key="task.id" class="guide-apply-task px-0 py-4 border-b">
          <template #prepend>
            <v-avatar size="24" rounded="0">
              <v-progress-circular v-if="task.status === 'running'" indeterminate size="24" width="2" color="primary" />
              <v-icon v-else size="24" :icon="task.status === 'error' ? 'mdi-alert-circle-outline' : task.status === 'done' ? 'mdi-check-circle-outline' : 'mdi-minus-circle-outline'"
                :color="task.status === 'error' ? 'error' : task.status === 'done' ? 'success' : undefined" />
            </v-avatar>
          </template>
          <v-list-item-title>{{ task.title }}</v-list-item-title>
          <p class="text-body-2 mt-1" :class="task.error ? 'text-error' : 'text-medium-emphasis'" :role="task.error ? 'alert' : undefined">{{ task.error || tm(`guide.applyStatus.${task.status}`) }}</p>
        </v-list-item>
      </v-list>
    </div>
    <div v-if="!completed" v-show="!applying" class="guide-content" :class="{ 'guide-content--chat': step === 3 }">
      <div class="guide-heading" aria-live="polite" aria-atomic="true">
        <span class="text-medium-emphasis text-caption">{{ step }} / {{ steps.length }}</span>
        <h2>{{ steps[step - 1] }}</h2>
        <p class="text-body-2 text-medium-emphasis mt-3">{{ tm(`guide.step${step}Hint`) }}</p>
      </div>
      <v-alert v-if="configError" type="error" variant="tonal" class="mb-4" role="alert">{{ configError }}</v-alert>
      <v-window v-model="step" :touch="false">
      <v-window-item :value="1">
        <ReadmeDialog embedded :show="step === 1" mode="first-notice" />
      </v-window-item>
      <v-window-item :value="2">
        <OnboardingModel ref="modelForm" :disabled="busy" @update:busy="busy = $event" />
      </v-window-item>
      <v-window-item :value="3">
        <div class="guide-trial">
          <div class="guide-chat-model text-body-2 text-medium-emphasis"><v-icon icon="mdi-check-circle-outline" color="success" size="18" /><span>{{ selectedModel }}</span></div>
          <div v-if="modelReady" class="guide-chat"><StandaloneChat /></div>
        </div>
      </v-window-item>
      <v-window-item :value="4">
        <v-alert v-if="platformError" type="error" variant="tonal" class="mb-4" role="alert">{{ platformError }}</v-alert>
        <v-progress-linear v-if="platformLoading" indeterminate color="primary" />
        <template v-else-if="!configError">
          <v-list v-if="configuredPlatforms.length" class="bg-transparent mb-4" role="list">
            <v-list-item v-for="platform in configuredPlatforms" :key="platform.id" role="listitem"
              class="guide-platform px-0 py-3 border-b" :title="platform.id" :subtitle="platform.type">
              <template #prepend>
                <v-avatar :image="getPlatformIcon(platform.type || platform.id)" size="28" rounded="0" />
              </template>
              <template #append>
                <v-chip :color="platform.enable !== false ? 'success' : undefined" size="small" variant="tonal" class="ml-3">
                  {{ tm(platform.enable !== false ? 'guide.adapterEnabled' : 'guide.adapterDisabled') }}
                </v-chip>
              </template>
            </v-list-item>
          </v-list>
          <AddNewPlatform v-if="!platformReady" ref="platformForm" embedded :show="true" :metadata="platformMetadata"
            :config_data="platformConfig" @refresh-config="loadPlatforms" @update:busy="busy = $event"
            @show-toast="platformError = $event.type === 'error' ? $event.message : ''" />
        </template>
        <v-btn v-else variant="text" @click="loadPlatforms">{{ tm('guide.retry') }}</v-btn>
      </v-window-item>
      <v-window-item :value="5">
        <v-alert v-if="installedCount" type="success" variant="tonal" class="mb-3" role="status">
          {{ tm('guide.pluginCount', { count: installedCount }) }}
        </v-alert>
        <v-progress-linear v-if="loading" indeterminate color="primary" :aria-label="tm('guide.loading')" />
        <v-alert v-if="loadError" type="error" variant="tonal" class="mb-3" role="alert">
          {{ loadError }}
          <template #append>
            <v-btn variant="text" :disabled="loading" @click="loadPlugins">{{ tm('guide.retry') }}</v-btn>
          </template>
        </v-alert>
        <p v-if="!loading && !loadError && pluginGroups.every(group => !group.items.length)" class="text-medium-emphasis py-6">
          {{ tm('guide.empty') }}
        </p>
        <template v-for="group in pluginGroups" :key="group.title">
        <section v-if="!loading && !loadError && group.items.length" class="guide-plugin-group">
          <h3 class="text-subtitle-1 font-weight-medium">{{ group.title }}</h3>
          <p v-if="group.community" class="text-caption text-medium-emphasis mt-1">{{ tm('guide.communityHint') }}</p>
          <v-row dense class="mt-3">
            <v-col v-for="plugin in group.items" :key="plugin.repo" cols="12" md="6">
              <MarketPluginCard :plugin="plugin" :default-plugin-icon="defaultPluginIcon"
                show-plugin-full-name class="guide-plugin" @open="togglePlugin(plugin)">
                <template #install-action>
                  <v-progress-circular v-if="installing === plugin.repo" indeterminate size="20"
                    width="2" color="primary" :aria-label="tm('guide.installing')" />
                  <v-chip v-else-if="plugin.installed" color="success" size="small" variant="tonal">
                    {{ tm('guide.installed') }}
                  </v-chip>
                  <v-checkbox-btn v-else v-model="selected" :value="plugin.repo" color="primary"
                    :disabled="busy" :aria-label="plugin.display_name || plugin.name" />
                </template>
              </MarketPluginCard>
              <p v-if="plugin.error" class="text-error text-body-2 mt-2" role="alert">{{ plugin.error }}</p>
            </v-col>
          </v-row>
        </section>
        </template>
      </v-window-item>
      <v-window-item :value="6">
        <OnboardingComputer v-if="step === 6" ref="computerForm" :disabled="busy" />
      </v-window-item>
      </v-window>
    </div>
    </div>
    <footer class="guide-actions">
      <v-btn v-if="completed" variant="tonal" color="primary" @click="close">{{ tm('guide.start') }}</v-btn>
      <template v-else-if="applying">
        <v-btn variant="text" prepend-icon="mdi-arrow-left" :disabled="busy" @click="applying = false">{{ tm('guide.back') }}</v-btn>
        <v-spacer />
        <v-btn v-if="applyTasks.some(task => task.status === 'error')" variant="tonal" color="primary" :loading="busy" @click="finish()">{{ tm('guide.retry') }}</v-btn>
        <v-btn v-else variant="tonal" color="primary" append-icon="mdi-arrow-right" :loading="busy" :disabled="!applyReady" @click="showWelcome">{{ tm('guide.next') }}</v-btn>
      </template>
      <template v-else>
      <p v-if="step === 4" id="guide-adapter-skip-hint" class="guide-skip-hint text-body-2 text-medium-emphasis">{{ tm('guide.adapterSkipHint') }}</p>
      <v-btn v-if="step > 1" variant="text" prepend-icon="mdi-arrow-left" :disabled="busy || platformLoading"
        @click="step === 4 && !modelReady ? step = 2 : step--">{{ tm('guide.back') }}</v-btn>
      <v-btn v-else variant="text" :disabled="busy" @click="close">{{ tm('guide.skipAll') }}</v-btn>
      <v-spacer />
      <v-btn v-if="step > 1" variant="text" :disabled="busy || platformLoading"
        :aria-describedby="step === 4 ? 'guide-adapter-skip-hint' : undefined" @click="skipStep">{{ tm('onboard.skip') }}</v-btn>
      <v-btn v-if="step < steps.length" variant="tonal" color="primary" append-icon="mdi-arrow-right" :loading="busy"
        :disabled="platformLoading || (step === 2 && !modelForm?.ready) || (step === 3 && !modelReady) || (step === 4 && !platformReady && !platformForm?.canSave) || (step === 5 && (loading || !!loadError))" @click="nextStep">
        {{ tm('guide.next') }}
      </v-btn>
      <v-btn v-else variant="tonal" color="primary" append-icon="mdi-arrow-right" :loading="busy" :disabled="!computerForm?.ready" @click="finish()">{{ tm('guide.next') }}</v-btn>
      </template>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue';
import { onBeforeRouteLeave, useRouter } from 'vue-router';
import { configProfileApi, pluginApi, providerApi, systemConfigApi } from '@/api/v1';
import { useModuleI18n } from '@/i18n/composables';
import { getPlatformIcon } from '@/utils/platformUtils';
import OnboardingModel from '@/components/OnboardingModel.vue';
import AddNewPlatform from '@/components/platform/AddNewPlatform.vue';
import StandaloneChat from '@/components/chat/StandaloneChat.vue';
import ReadmeDialog from '@/components/shared/ReadmeDialog.vue';
import OnboardingComputer from '@/components/OnboardingComputer.vue';
import OnboardingWelcome from '@/components/OnboardingWelcome.vue';
import MarketPluginCard from '@/components/extension/MarketPluginCard.vue';
import defaultPluginIcon from '/favicon.svg';

const { tm } = useModuleI18n('features/welcome');
const router = useRouter();
const scrollContainer = ref<HTMLElement>();
const modelReady = ref(false);
const modelForm = ref<InstanceType<typeof OnboardingModel>>();
const platformForm = ref<InstanceType<typeof AddNewPlatform>>();
const computerForm = ref<InstanceType<typeof OnboardingComputer>>();
const selectedModel = ref('');
const platformReady = ref(false);
const platformLoading = ref(false);
const platformError = ref('');
const platformMetadata = ref({});
const platformConfig = ref<Record<string, any>>({});
const configuredPlatforms = computed(() => Array.isArray(platformConfig.value.platform)
  ? platformConfig.value.platform.filter((platform: any) => platform?.id) as { id: string; type?: string; enable?: boolean }[] : []);
const configError = ref('');
const step = ref(1);
const completed = ref(false);
const steps = computed(() => [tm('guide.notice'), tm('guide.modelTitle'), tm('guide.chat'), tm('guide.platform'), tm('guide.plugins'), tm('onboard.step3Title')]);
const plugins = ref<{ repo: string; name: string; display_name?: string; desc: string; author: string; logo?: string; support_platforms?: string[]; i18n?: Record<string, unknown>; stars: number; official: boolean; installed: boolean; error: string }[]>([]);
const pluginGroups = computed(() => [
  { title: tm('guide.official'), community: false, items: plugins.value.filter(p => p.official) },
  { title: tm('guide.popular'), community: true, items: plugins.value.filter(p => !p.official && p.stars > 0).slice(0, 6) },
]);
const selected = ref<string[]>([]);
const loading = ref(false);
const loadError = ref('');
const installing = ref('');
const busy = ref(false);
const installedCount = ref(0);
const applying = ref(false);
const settingsStatus = ref<'pending' | 'running' | 'done' | 'skipped' | 'error'>('pending');
const settingsError = ref('');
const queuedPlugins = ref<(typeof plugins.value)[number][]>([]);
const applyTasks = computed(() => [
  { id: 'settings', title: tm('guide.applySettings'), status: settingsStatus.value, error: settingsError.value },
  ...queuedPlugins.value.map(plugin => ({ id: plugin.repo, title: plugin.display_name || plugin.name,
    status: plugin.installed ? 'done' : installing.value === plugin.repo ? 'running' : plugin.error ? 'error' : 'pending', error: plugin.error })),
]);
const applyReady = computed(() => applying.value && !busy.value && applyTasks.value.every(task => ['done', 'skipped'].includes(task.status)));

async function nextStep() {
  if (busy.value || platformLoading.value || applying.value || (step.value === 5 && (loading.value || loadError.value))) return;
  if (step.value !== 2) {
    if (step.value === 4 && !platformReady.value) {
      await platformForm.value?.newPlatform();
      return;
    }
    step.value++;
    return;
  }
  busy.value = true;
  configError.value = '';
  try {
    const savedId = await modelForm.value?.save();
    if (modelForm.value && !savedId) return;
    const response = await providerApi.schema();
    if (response.data.status !== 'ok') throw new Error(response.data.message || tm('onboard.providerLoadFailed'));
    const { providers = [], provider_sources = [] } = response.data.data || {};
    const sources = new Map(provider_sources.map(source => [source.id, source.provider_type]));
    const provider = providers.find(p => {
      const type = p.provider_type || sources.get(p.provider_source_id) ||
        (String(p.type || '').includes('chat_completion') ? 'chat_completion' : '');
      return p.id && (!savedId || p.id === savedId) && p.enable !== false && type === 'chat_completion';
    });
    if (!provider) throw new Error(tm('guide.modelPending'));
    const profile = await configProfileApi.get('default');
    if (profile.data.status !== 'ok') throw new Error(profile.data.message || tm('onboard.providerLoadFailed'));
    const config = profile.data.data?.config as Record<string, any> | undefined;
    const model = config?.agent_runner?.config?.model;
    if (config?.agent_runner?.runner_type === 'local' && model && !model.provider_id) {
      model.provider_id = provider.id;
      const result = await configProfileApi.update('default', config);
      if (result.data.status !== 'ok') throw new Error(result.data.message || tm('onboard.providerUpdateFailed'));
    }
    modelReady.value = true;
    selectedModel.value = String(model?.provider_id || provider.id);
    step.value = 3;
  } catch (error: any) {
    configError.value = error?.response?.data?.message || error?.message || tm('onboard.providerLoadFailed');
  } finally {
    busy.value = false;
  }
}

async function loadPlatforms(savedId?: string) {
  busy.value = false;
  platformError.value = '';
  platformLoading.value = true;
  platformReady.value = false;
  configError.value = '';
  try {
    const result = await systemConfigApi.runtime();
    if (result.data.status !== 'ok') throw new Error(result.data.message || tm('onboard.platformLoadFailed'));
    platformConfig.value = result.data.data?.config || {};
    platformMetadata.value = result.data.data?.metadata || {};
    platformReady.value = configuredPlatforms.value.some(platform => platform.enable !== false);
    if (savedId && platformReady.value) step.value = 5;
  } catch (error: any) {
    configError.value = error?.response?.data?.message || error?.message || tm('onboard.platformLoadFailed');
  } finally {
    platformLoading.value = false;
  }
}

function officialRepo(value: unknown): string {
  const repo = githubRepo(value);
  return repo.startsWith('https://github.com/AstrBotDevs/') ? repo : '';
}

function githubRepo(value: unknown): string {
  try {
    const url = new URL(String(value));
    if (url.origin !== 'https://github.com' || url.username || url.password || url.search || url.hash) return '';
    const parts = url.pathname.replace(/\/$/, '').split('/');
    if (parts.length !== 3 || !/^[a-z\d](?:[a-z\d-]*[a-z\d])?$/i.test(parts[1])) return '';
    const owner = parts[1].toLowerCase() === 'astrbotdevs' ? 'AstrBotDevs' : parts[1].toLowerCase();
    const repo = parts[2].replace(/\.git$/i, '');
    return /^[\w.-]+$/.test(repo) && repo !== '.' && repo !== '..'
      ? `https://github.com/${owner}/${repo.toLowerCase()}` : '';
  } catch {
    return '';
  }
}

async function loadPlugins() {
  if (loading.value || busy.value) return;
  loading.value = true;
  loadError.value = '';
  try {
    const market = await pluginApi.market();
    const installed = await pluginApi.list();
    if (market.data.status !== 'ok' || installed.data.status !== 'ok') {
      throw new Error(tm('guide.loadFailed'));
    }
    const installedRepos = new Set((installed.data.data || []).map(p => githubRepo(p.repo || p.install_source?.repo)));
    const seen = new Set<string>();
    plugins.value = Object.entries(market.data.data || {}).flatMap(([name, entry]: [string, any]) => {
      const repo = githubRepo(entry?.repo);
      if (name === '$meta' || !repo || seen.has(repo)) return [];
      seen.add(repo);
      return [{ repo, name: entry.name || name, display_name: entry.display_name,
        desc: entry.short_desc || entry.desc || '',
        author: typeof entry.author === 'string' ? entry.author : repo.split('/')[3],
        logo: typeof entry.logo === 'string' && entry.logo.startsWith('https://') ? entry.logo : undefined,
        support_platforms: entry.support_platforms, i18n: entry.i18n,
        stars: typeof entry.stars === 'number' && Number.isFinite(entry.stars) ? Math.max(0, Math.floor(entry.stars)) : 0,
        official: !!officialRepo(repo), installed: installedRepos.has(repo), error: '' }];
    }).sort((a, b) => b.stars - a.stars);
    selected.value = selected.value.filter(repo => pluginGroups.value.some(group => group.items.some(plugin => plugin.repo === repo && !plugin.installed)));
  } catch (error: any) {
    loadError.value = error?.response?.data?.message || error?.message || tm('guide.loadFailed');
  } finally {
    loading.value = false;
  }
}

function togglePlugin(plugin: (typeof plugins.value)[number]) {
  if (busy.value || plugin.installed) return;
  selected.value = selected.value.includes(plugin.repo)
    ? selected.value.filter(repo => repo !== plugin.repo) : [...selected.value, plugin.repo];
}

async function finish(skipComputer = false) {
  if (busy.value || completed.value || loading.value || (!skipComputer && !(applying.value && ['done', 'skipped'].includes(settingsStatus.value)) && !computerForm.value?.ready)) return;
  if (!applying.value) {
    queuedPlugins.value = pluginGroups.value.flatMap(group => group.items).filter(p => selected.value.includes(p.repo) && !p.installed);
    settingsStatus.value = skipComputer ? 'skipped' : 'pending';
    settingsError.value = '';
    applying.value = true;
    void nextTick(() => scrollContainer.value?.scrollTo({ top: 0 }));
  }
  busy.value = true;
  try {
    if (!['done', 'skipped'].includes(settingsStatus.value)) {
      settingsStatus.value = 'running';
      settingsError.value = '';
      try {
        if (!await computerForm.value?.save()) throw new Error(computerForm.value?.error || tm('onboard.computerAccessUpdateFailed'));
        settingsStatus.value = 'done';
      } catch (error: any) {
        settingsStatus.value = 'error';
        settingsError.value = error?.response?.data?.message || error?.message || tm('onboard.computerAccessUpdateFailed');
        return;
      }
    }
    // Install sequentially; never use a market-supplied download URL or bypass version checks.
    for (const plugin of queuedPlugins.value.filter(p => !p.installed)) {
      installing.value = plugin.repo;
      plugin.error = '';
      try {
        const repo = githubRepo(plugin.repo);
        if (!repo) throw new Error(tm('guide.installFailed'));
        const validation = await pluginApi.validateRepo({ url: repo });
        if (validation.data.status !== 'ok') throw new Error(validation.data.message || tm('guide.installFailed'));
        const result = await pluginApi.installGithub({ url: repo, ignore_version_check: false });
        if (result.data.status !== 'ok') throw new Error(result.data.message || tm('guide.installFailed'));
        plugin.installed = true;
        installedCount.value++;
        selected.value = selected.value.filter(value => value !== plugin.repo);
      } catch (error: any) {
        plugin.error = error?.response?.data?.message || error?.message || tm('guide.installFailed');
      }
    }
  } finally {
    installing.value = '';
    busy.value = false;
  }
}

function close() {
  if (!busy.value && !platformLoading.value) void router.push('/dashboard/default');
}

function skipStep() {
  if (busy.value || platformLoading.value || applying.value) return;
  if (step.value === steps.value.length) return finish(true);
  else if (step.value === 2 && !modelReady.value) step.value = 4;
  else {
    if (step.value === 5) selected.value = [];
    step.value++;
  }
}

function showWelcome() {
  if (!applyReady.value) return;
  completed.value = true;
  void nextTick(() => scrollContainer.value?.scrollTo({ top: 0 }));
}

watch(step, value => {
  void nextTick(() => scrollContainer.value?.scrollTo({ top: 0 }));
  configError.value = '';
  if (value === 4) void loadPlatforms();
  if (value === 5) void loadPlugins();
});
onBeforeRouteLeave(() => !busy.value && !platformLoading.value);
</script>

<style scoped>
.onboarding-setup { display: flex; flex-direction: column; flex: 1; min-height: 0; min-width: 0; }
.guide-scroll { flex: 1; min-height: 0; overflow-y: auto; overscroll-behavior: contain; }
.guide-scroll--complete { display: flex; }
.guide-content { width: 100%; padding: 16px 0 24px; }
.guide-content > .v-window { padding-top: 8px; margin-top: -8px; }
.guide-heading { margin-bottom: 28px; }
.guide-heading h2 { margin-top: 6px; font-size: 24px; line-height: 1.35; font-weight: 600; letter-spacing: 0; }
.guide-ready { display: flex; align-items: flex-start; gap: 12px; padding: 20px 0; }
.guide-content--chat { height: 100%; display: flex; flex-direction: column; }
.guide-content--chat > .guide-heading { flex-shrink: 0; margin-bottom: 16px; }
.guide-content--chat > .v-window { flex: 1; min-height: 320px; }
.guide-content--chat :deep(.v-window__container), .guide-content--chat :deep(.v-window-item) { height: 100%; }
.guide-trial { display: flex; flex-direction: column; height: 100%; gap: 12px; }
.guide-chat-model { display: flex; align-items: center; gap: 8px; flex-shrink: 0; overflow-wrap: anywhere; }
.guide-chat-model > span { min-width: 0; }
.guide-chat { flex: 1; min-height: 260px; overflow: hidden; }
.guide-chat :deep(.standalone-chat), .guide-chat :deep(.standalone-composer) { background: transparent; }
.guide-chat :deep(.standalone-messages) { padding: 16px 0; }
.guide-chat :deep(.standalone-composer) { padding-bottom: 0; }
.guide-chat :deep(.input-area) { padding-inline: 0; }
.guide-chat :deep(.input-container) { width: 100% !important; max-width: 100% !important; margin-inline: 0 !important; }
.guide-plugin-group + .guide-plugin-group { margin-top: 28px; }
.guide-apply-task :deep(.v-list-item-title) { white-space: normal; overflow-wrap: anywhere; }
.guide-apply-task p { overflow-wrap: anywhere; }
.guide-platform :deep(.v-list-item-title), .guide-platform :deep(.v-list-item-subtitle) { white-space: normal; overflow-wrap: anywhere; }
.guide-actions { display: flex; flex-shrink: 0; align-items: center; gap: 8px; flex-wrap: wrap; padding: 8px 0 max(8px, env(safe-area-inset-bottom)); border-top: 1px solid rgba(var(--v-theme-on-surface), .1); background: rgb(var(--v-theme-surface)); z-index: 1; }
.guide-actions :deep(.v-btn) { letter-spacing: 0; }
.guide-skip-hint { flex-basis: 100%; margin: 0; text-align: end; overflow-wrap: anywhere; }
.guide-actions > .v-btn:last-child { margin-inline-start: auto; }
@media (max-width: 600px) {
  .guide-actions { gap: 4px; }
  .guide-actions :deep(.v-btn) { padding-inline: 10px; min-width: 0; }
}
</style>
