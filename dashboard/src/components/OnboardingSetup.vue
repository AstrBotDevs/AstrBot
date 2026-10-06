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
          <div v-if="modelReady" class="guide-chat"><StandaloneChat minimal /></div>
        </div>
      </v-window-item>
      <v-window-item :value="4">
        <v-alert v-if="platformError" type="error" variant="tonal" class="mb-4" role="alert">{{ platformError }}</v-alert>
        <v-progress-linear v-if="platformLoading" indeterminate color="primary" />
        <template v-else-if="!configError">
          <v-select v-if="configuredPlatforms.length" :model-value="selectedPlatformId" :items="platformChoices"
            :label="tm('guide.adapter')" variant="outlined" hide-details class="mb-4" :disabled="busy"
            @update:model-value="selectPlatform" />
          <div v-if="platformDraft" :inert="busy">
            <AddNewPlatform :key="selectedPlatformId" ref="platformForm" embedded :show="true" updating-mode
              :updating-platform-config="platformDraft" :metadata="existingPlatformMetadata" :config_data="platformConfig"
              @show-toast="platformError = $event.type === 'error' ? $event.message : ''" />
          </div>
          <AddNewPlatform v-else ref="platformForm" embedded :show="true" :metadata="platformMetadata"
            :config_data="platformConfig" @refresh-config="loadPlatforms" @update:busy="busy = $event"
            @show-toast="platformError = $event.type === 'error' ? $event.message : ''" />
        </template>
        <v-btn v-else variant="text" @click="loadPlatforms">{{ tm('guide.retry') }}</v-btn>
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
      <v-btn variant="tonal" color="primary" append-icon="mdi-arrow-right" :loading="busy"
        :disabled="platformLoading || (step === 2 && !modelForm?.ready) || (step === 3 && !modelReady) || (step === 4 && (platformDraft ? !platformReady || !platformForm?.initialPlatformRoutes : !platformForm?.canSave))" @click="nextStep">
        {{ tm('guide.next') }}
      </v-btn>
      </template>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue';
import { onBeforeRouteLeave, useRouter } from 'vue-router';
import { botApi, configProfileApi, providerApi, systemConfigApi } from '@/api/v1';
import { useModuleI18n } from '@/i18n/composables';
import OnboardingModel from '@/components/OnboardingModel.vue';
import AddNewPlatform from '@/components/platform/AddNewPlatform.vue';
import StandaloneChat from '@/components/chat/StandaloneChat.vue';
import ReadmeDialog from '@/components/shared/ReadmeDialog.vue';
import OnboardingWelcome from '@/components/OnboardingWelcome.vue';

const { tm } = useModuleI18n('features/welcome');
const router = useRouter();
const scrollContainer = ref<HTMLElement>();
const modelReady = ref(false);
const modelForm = ref<InstanceType<typeof OnboardingModel>>();
const platformForm = ref<InstanceType<typeof AddNewPlatform>>();
const selectedModel = ref('');
const selectedPlatformId = ref('');
const platformDraft = ref<Record<string, any> | null>(null);
const platformReady = computed(() => Boolean(selectedPlatformId.value) && platformDraft.value?.id === selectedPlatformId.value);
const platformLoading = ref(false);
const platformError = ref('');
const platformMetadata = ref<Record<string, any>>({});
const existingPlatformMetadata = computed(() => {
  const metadata = platformMetadata.value.platform_group?.metadata || {};
  const platform = metadata.platform || {};
  return { ...platformMetadata.value, platform_group: { ...platformMetadata.value.platform_group, metadata: {
    ...metadata, platform: { ...platform, items: {
    ...platform.items, id: { ...platform.items?.id, invisible: true },
  } } } } };
});
const platformConfig = ref<Record<string, any>>({});
const configuredPlatforms = computed(() => Array.isArray(platformConfig.value.platform)
  ? platformConfig.value.platform.filter((platform: any) => typeof platform?.id === 'string' && platform.id) as Record<string, any>[] : []);
const platformChoices = computed(() => [
  ...configuredPlatforms.value.map(platform => ({ title: `${platform.id} (${platform.type || ''})`, value: platform.id })),
  { title: tm('guide.newAdapter'), value: '' },
]);
const configError = ref('');
const step = ref(1);
const completed = ref(false);
const steps = computed(() => [tm('guide.notice'), tm('guide.modelTitle'), tm('guide.chat'), tm('guide.platform')]);
const busy = ref(false);

async function nextStep() {
  if (busy.value || platformLoading.value || completed.value) return;
  if (step.value !== 2) {
    if (step.value === 4) {
      if (platformDraft.value) await savePlatform();
      else await platformForm.value?.newPlatform();
      return;
    }
    if (step.value === steps.value.length) showWelcome();
    else step.value++;
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
  platformDraft.value = null;
  configError.value = '';
  try {
    const result = await systemConfigApi.runtime();
    if (result.data.status !== 'ok') throw new Error(result.data.message || tm('onboard.platformLoadFailed'));
    platformConfig.value = result.data.data?.config || {};
    platformMetadata.value = result.data.data?.metadata || {};
    selectPlatform(configuredPlatforms.value.find(platform => platform.id === savedId)?.id ||
      configuredPlatforms.value.find(platform => platform.enable !== false)?.id || configuredPlatforms.value[0]?.id || '');
    if (savedId && configuredPlatforms.value.some(platform => platform.id === savedId)) showWelcome();
  } catch (error: any) {
    configError.value = error?.response?.data?.message || error?.message || tm('onboard.platformLoadFailed');
  } finally {
    platformLoading.value = false;
  }
}

function selectPlatform(id: string) {
  selectedPlatformId.value = id;
  platformError.value = '';
  const platform = configuredPlatforms.value.find(platform => platform.id === id);
  platformDraft.value = platform ? JSON.parse(JSON.stringify(platform)) : null;
}

async function savePlatform() {
  if (!platformReady.value || !platformDraft.value || !platformForm.value?.initialPlatformRoutes) return;
  const original = configuredPlatforms.value.find(platform => platform.id === selectedPlatformId.value);
  const adapterChanged = JSON.stringify(original) !== JSON.stringify(platformDraft.value);
  const routesChanged = platformForm.value.routesChanged;
  if (!adapterChanged && !routesChanged) {
    showWelcome();
    return;
  }
  busy.value = true;
  platformError.value = '';
  try {
    const draft = JSON.parse(JSON.stringify(platformDraft.value));
    if (adapterChanged) {
      const result = await botApi.update(selectedPlatformId.value, draft);
      if (result.data.status !== 'ok') throw new Error(result.data.message || tm('guide.adapterSaveFailed'));
    }
    if (routesChanged) await platformForm.value.saveRoutesInternal();
    await loadPlatforms(draft.id);
  } catch (error: any) {
    platformError.value = error?.response?.data?.message || error?.message || tm('guide.adapterSaveFailed');
  } finally {
    busy.value = false;
  }
}

function close() {
  if (!busy.value && !platformLoading.value) void router.push('/dashboard/default');
}

function skipStep() {
  if (busy.value || platformLoading.value || completed.value) return;
  if (step.value === steps.value.length) showWelcome();
  else if (step.value === 2 && !modelReady.value) step.value = 4;
  else step.value++;
}

function showWelcome() {
  completed.value = true;
  void nextTick(() => scrollContainer.value?.scrollTo({ top: 0 }));
}

watch(step, value => {
  void nextTick(() => scrollContainer.value?.scrollTo({ top: 0 }));
  configError.value = '';
  if (value === 4) void loadPlatforms();
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
.guide-actions { display: flex; flex-shrink: 0; align-items: center; gap: 8px; flex-wrap: wrap; padding: 8px 0 max(8px, env(safe-area-inset-bottom)); border-top: 1px solid rgba(var(--v-theme-on-surface), .1); background: rgb(var(--v-theme-surface)); z-index: 1; }
.guide-actions :deep(.v-btn) { letter-spacing: 0; }
.guide-skip-hint { flex-basis: 100%; margin: 0; text-align: end; overflow-wrap: anywhere; }
.guide-actions > .v-btn:last-child { margin-inline-start: auto; }
@media (max-width: 600px) {
  .guide-actions { gap: 4px; }
  .guide-actions :deep(.v-btn) { padding-inline: 10px; min-width: 0; }
}
</style>
