<template>
  <section class="onboarding-setup">
    <div ref="scrollContainer" class="guide-scroll" :class="{ 'guide-scroll--complete': completed }">
    <OnboardingWelcome v-if="completed" />
    <div v-else class="guide-content" :class="{ 'guide-content--chat': step === 3 }">
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
        <div v-else-if="platformReady" class="guide-ready">
          <v-icon icon="mdi-check-circle-outline" color="success" />
          <strong>{{ tm('guide.platformReady') }}</strong>
        </div>
        <AddNewPlatform v-else-if="!configError" ref="platformForm" embedded :show="true" :metadata="platformMetadata"
          :config_data="platformConfig" @refresh-config="loadPlatforms" @update:busy="busy = $event"
          @show-toast="platformError = $event.type === 'error' ? $event.message : ''" />
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
      <template v-else>
      <p v-if="step === 4" id="guide-adapter-skip-hint" class="guide-skip-hint text-body-2 text-medium-emphasis">{{ tm('guide.adapterSkipHint') }}</p>
      <v-btn v-if="step > 1" variant="text" prepend-icon="mdi-arrow-left" :disabled="busy || platformLoading"
        @click="step === 4 && !modelReady ? step = 2 : step--">{{ tm('guide.back') }}</v-btn>
      <v-btn v-else variant="text" :disabled="busy" @click="close">{{ tm('guide.skipAll') }}</v-btn>
      <v-spacer />
      <v-btn v-if="step > 1" variant="text" :disabled="busy || platformLoading"
        :aria-describedby="step === 4 ? 'guide-adapter-skip-hint' : undefined" @click="skipStep">{{ tm('onboard.skip') }}</v-btn>
      <v-btn v-if="step === 5 && selected.length" variant="tonal" color="primary"
        :loading="busy" :disabled="loading || !!loadError" @click="installSelected">
        {{ tm('guide.next') }}
      </v-btn>
      <v-btn v-else-if="step < steps.length" variant="tonal" color="primary" :loading="busy"
        :disabled="platformLoading || (step === 2 && !modelForm?.ready) || (step === 3 && !modelReady) || (step === 4 && !platformReady && !platformForm?.canSave)" @click="nextStep">
        {{ tm('guide.next') }}
      </v-btn>
      <v-btn v-else variant="tonal" color="primary" :loading="busy" :disabled="!computerForm?.ready" @click="finish">{{ tm('guide.next') }}</v-btn>
      </template>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue';
import { onBeforeRouteLeave, useRouter } from 'vue-router';
import { configProfileApi, pluginApi, providerApi, systemConfigApi } from '@/api/v1';
import { useModuleI18n } from '@/i18n/composables';
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

async function nextStep() {
  if (busy.value || platformLoading.value) return;
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
  configError.value = '';
  try {
    const result = await systemConfigApi.runtime();
    if (result.data.status !== 'ok') throw new Error(result.data.message || tm('onboard.platformLoadFailed'));
    platformConfig.value = result.data.data?.config || {};
    platformMetadata.value = result.data.data?.metadata || {};
    platformReady.value = (platformConfig.value.platform || []).length > 0;
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
  selected.value = [];
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

async function installSelected() {
  if (busy.value || loading.value || loadError.value) return;
  busy.value = true;
  try {
    // Install sequentially; never use a market-supplied download URL or bypass version checks.
    for (const plugin of pluginGroups.value.flatMap(group => group.items).filter(p => selected.value.includes(p.repo) && !p.installed)) {
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
  if (busy.value || platformLoading.value) return;
  if (step.value === steps.value.length) close();
  else if (step.value === 2 && !modelReady.value) step.value = 4;
  else step.value++;
}

async function finish() {
  if (busy.value || completed.value || !computerForm.value?.ready) return;
  busy.value = true;
  try {
    if (await computerForm.value.save()) {
      completed.value = true;
      void nextTick(() => scrollContainer.value?.scrollTo({ top: 0 }));
    }
  } finally {
    busy.value = false;
  }
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
.guide-content { width: 100%; padding: 32px 0 24px; }
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
.guide-actions { display: flex; flex-shrink: 0; align-items: center; gap: 8px; flex-wrap: wrap; padding: 20px 0 max(20px, env(safe-area-inset-bottom)); border-top: 1px solid rgba(var(--v-theme-on-surface), .1); background: rgb(var(--v-theme-surface)); z-index: 1; }
.guide-actions :deep(.v-btn) { letter-spacing: 0; }
.guide-skip-hint { flex-basis: 100%; margin: 0; text-align: end; overflow-wrap: anywhere; }
.guide-actions > .v-btn:last-child { margin-inline-start: auto; }
@media (max-width: 600px) {
  .guide-actions { padding: 16px 0 max(16px, env(safe-area-inset-bottom)); gap: 4px; }
  .guide-actions :deep(.v-btn) { padding-inline: 10px; min-width: 0; }
}
</style>
