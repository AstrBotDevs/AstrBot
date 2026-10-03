<template>
  <v-progress-linear v-if="loading" indeterminate color="primary" />
  <v-alert v-if="error" type="error" variant="tonal" class="mb-4" role="alert">
    {{ error }}
    <template v-if="!loaded" #append>
      <v-btn variant="text" :disabled="loading" @click="load">{{ tm('guide.retry') }}</v-btn>
    </template>
  </v-alert>
  <div class="computer-permission">
    <div class="d-flex align-center justify-space-between ga-6 py-4 border-b">
      <div>
        <label for="onboarding-computer-access" class="text-subtitle-1 font-weight-medium">{{ tm('onboard.step3SelectLabel') }}</label>
        <p class="text-body-2 text-medium-emphasis mt-1">{{ tm('guide.computerOptional') }}</p>
      </div>
      <v-switch id="onboarding-computer-access" v-model="allowed" :disabled="disabled || !ready"
        color="primary" inset density="compact" hide-details class="flex-grow-0 flex-shrink-0"
        :aria-label="tm('onboard.step3Title')" aria-describedby="computer-permission-details" />
    </div>
    <v-alert v-if="originalRuntime === 'sandbox'" type="info" variant="tonal" class="mt-4">
      {{ tm('guide.computerSandbox') }}
    </v-alert>
    <div id="computer-permission-details" class="text-body-2 mt-6">
      <p>{{ tm('onboard.step3HelpItem1') }}</p>
      <p class="mt-4">{{ tm('onboard.step3HelpItem2') }}</p>
      <p class="text-medium-emphasis mt-4">{{ tm('onboard.step3HelpItem3') }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { configProfileApi, type OpenConfig } from '@/api/v1';
import { useModuleI18n } from '@/i18n/composables';

defineProps<{ disabled?: boolean }>();
type ComputerConfig = OpenConfig & {
  provider_settings: Record<string, unknown> & { computer_use_runtime?: string };
};
const { tm } = useModuleI18n('features/welcome');
const allowed = ref(false);
const originalRuntime = ref('none');
const loading = ref(false);
const loaded = ref(false);
const error = ref('');
const ready = computed(() => loaded.value && !loading.value);

async function load() {
  loading.value = true;
  error.value = '';
  try {
    const response = await configProfileApi.get('default');
    const config = response.data.data?.config as ComputerConfig | undefined;
    if (response.data.status !== 'ok' || !config?.provider_settings ||
      typeof config.provider_settings !== 'object' || Array.isArray(config.provider_settings)) {
      throw new Error(response.data.message || tm('guide.computerLoadFailed'));
    }
    originalRuntime.value = config.provider_settings.computer_use_runtime || 'none';
    allowed.value = ['local', 'sandbox'].includes(originalRuntime.value);
    loaded.value = true;
  } catch (err: any) {
    error.value = err?.response?.data?.message || err?.message || tm('guide.computerLoadFailed');
  } finally {
    loading.value = false;
  }
}

async function save() {
  if (!ready.value) return false;
  if (allowed.value === ['local', 'sandbox'].includes(originalRuntime.value)) return true;
  loading.value = true;
  error.value = '';
  try {
    // Re-read before saving to preserve other settings changed during onboarding.
    const profile = await configProfileApi.get('default');
    const config = profile.data.data?.config as ComputerConfig | undefined;
    if (profile.data.status !== 'ok' || !config?.provider_settings ||
      typeof config.provider_settings !== 'object' || Array.isArray(config.provider_settings)) {
      throw new Error(profile.data.message || tm('guide.computerLoadFailed'));
    }
    const runtime = allowed.value ? 'local' : 'none';
    config.provider_settings.computer_use_runtime = runtime;
    const response = await configProfileApi.update('default', config);
    if (response.data.status !== 'ok') throw new Error(response.data.message || tm('onboard.computerAccessUpdateFailed'));
    originalRuntime.value = runtime;
    return true;
  } catch (err: any) {
    error.value = err?.response?.data?.message || err?.message || tm('onboard.computerAccessUpdateFailed');
    return false;
  } finally {
    loading.value = false;
  }
}

onMounted(load);
defineExpose({ save, ready, error });
</script>
