<template>
  <div class="onboarding-platform">
    <v-alert
      v-if="loadError"
      type="error"
      variant="tonal"
      class="mb-4"
      role="alert"
    >
      {{ loadError }}
    </v-alert>
    <v-alert
      v-if="platformError"
      type="error"
      variant="tonal"
      class="mb-4"
      role="alert"
    >
      {{ platformError }}
    </v-alert>
    <v-progress-linear
      v-if="loading"
      indeterminate
      color="primary"
      class="mb-4"
    />
    <template v-else-if="!loadError">
      <v-select
        v-if="configuredPlatforms.length"
        :model-value="selectedPlatformId"
        :items="platformChoices"
        :label="tm('guide.adapter')"
        variant="outlined"
        density="compact"
        hide-details
        class="mb-4"
        :disabled="disabled || saving"
        @update:model-value="selectPlatform"
      />
      <div v-if="platformDraft" :inert="disabled || saving">
        <AddNewPlatform
          :key="selectedPlatformId"
          ref="formRef"
          embedded
          :show="true"
          updating-mode
          :updating-platform-config="platformDraft"
          :metadata="existingPlatformMetadata"
          :config_data="platformConfig"
          @show-toast="platformError = $event.type === 'error' ? $event.message : ''"
        />
      </div>
      <AddNewPlatform
        v-else
        ref="formRef"
        embedded
        :show="true"
        :metadata="platformMetadata"
        :config_data="platformConfig"
        @refresh-config="loadPlatforms"
        @update:busy="emit('update:busy', $event)"
        @show-toast="platformError = $event.type === 'error' ? $event.message : ''"
      />
    </template>
    <v-btn v-else variant="text" @click="loadPlatforms()">
      {{ tm('guide.retry') }}
    </v-btn>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { botApi, systemConfigApi } from '@/api/v1';
import { useModuleI18n } from '@/i18n/composables';
import AddNewPlatform from '@/components/platform/AddNewPlatform.vue';

const props = defineProps<{ disabled?: boolean }>();
const emit = defineEmits<{
  saved: [platformId: string];
  'update:busy': [value: boolean];
  'update:loading': [value: boolean];
}>();

const { tm } = useModuleI18n('features/welcome');
const formRef = ref<InstanceType<typeof AddNewPlatform>>();
const loading = ref(false);
const saving = ref(false);
const loadError = ref('');
const platformError = ref('');
const selectedPlatformId = ref('');
const platformDraft = ref<Record<string, any> | null>(null);
const platformMetadata = ref<Record<string, any>>({});
const platformConfig = ref<Record<string, any>>({});

const configuredPlatforms = computed(() =>
  Array.isArray(platformConfig.value.platform)
    ? (platformConfig.value.platform.filter(
        (platform: any) => typeof platform?.id === 'string' && platform.id,
      ) as Record<string, any>[])
    : [],
);

const platformChoices = computed(() => [
  ...configuredPlatforms.value.map((platform) => ({
    title: `${platform.id} (${platform.type || ''})`,
    value: platform.id,
  })),
  { title: tm('guide.newAdapter'), value: '' },
]);

const existingPlatformMetadata = computed(() => {
  const metadata = platformMetadata.value.platform_group?.metadata || {};
  const platform = metadata.platform || {};
  return {
    ...platformMetadata.value,
    platform_group: {
      ...platformMetadata.value.platform_group,
      metadata: {
        ...metadata,
        platform: {
          ...platform,
          items: {
            ...platform.items,
            id: { ...platform.items?.id, invisible: true },
          },
        },
      },
    },
  };
});

const platformReady = computed(
  () => Boolean(selectedPlatformId.value) && platformDraft.value?.id === selectedPlatformId.value,
);

const canSave = computed(
  () =>
    !loading.value &&
    !loadError.value &&
    (platformDraft.value
      ? platformReady.value && Boolean(formRef.value?.initialPlatformRoutes)
      : Boolean(formRef.value?.canSave)),
);

watch(loading, (value) => emit('update:loading', value), { immediate: true });
watch(saving, (value) => emit('update:busy', value));

function selectPlatform(id: string) {
  selectedPlatformId.value = id;
  platformError.value = '';
  const platform = configuredPlatforms.value.find((item) => item.id === id);
  platformDraft.value = platform ? JSON.parse(JSON.stringify(platform)) : null;
}

async function loadPlatforms(savedId?: string) {
  emit('update:busy', false);
  platformError.value = '';
  loading.value = true;
  platformDraft.value = null;
  loadError.value = '';
  try {
    const result = await systemConfigApi.runtime();
    if (result.data.status !== 'ok') {
      throw new Error(result.data.message || tm('onboard.platformLoadFailed'));
    }
    platformConfig.value = result.data.data?.config || {};
    platformMetadata.value = result.data.data?.metadata || {};
    selectPlatform(
      configuredPlatforms.value.find((platform) => platform.id === savedId)?.id ||
        configuredPlatforms.value.find((platform) => platform.enable !== false)?.id ||
        configuredPlatforms.value[0]?.id ||
        '',
    );
    if (savedId && configuredPlatforms.value.some((platform) => platform.id === savedId)) {
      emit('saved', savedId);
    }
  } catch (error: any) {
    loadError.value =
      error?.response?.data?.message || error?.message || tm('onboard.platformLoadFailed');
  } finally {
    loading.value = false;
  }
}

async function save() {
  if (props.disabled || loading.value || saving.value) return;
  if (!platformDraft.value) {
    await formRef.value?.newPlatform();
    return;
  }
  if (!platformReady.value || !formRef.value?.initialPlatformRoutes) return;
  const original = configuredPlatforms.value.find((item) => item.id === selectedPlatformId.value);
  const adapterChanged = JSON.stringify(original) !== JSON.stringify(platformDraft.value);
  const routesChanged = formRef.value.routesChanged;
  if (!adapterChanged && !routesChanged) {
    emit('saved', selectedPlatformId.value);
    return;
  }
  saving.value = true;
  platformError.value = '';
  try {
    const draftCopy = JSON.parse(JSON.stringify(platformDraft.value));
    if (adapterChanged) {
      const result = await botApi.update(selectedPlatformId.value, draftCopy);
      if (result.data.status !== 'ok') {
        throw new Error(result.data.message || tm('guide.adapterSaveFailed'));
      }
    }
    if (routesChanged) await formRef.value.saveRoutesInternal();
    await loadPlatforms(draftCopy.id);
  } catch (error: any) {
    platformError.value =
      error?.response?.data?.message || error?.message || tm('guide.adapterSaveFailed');
  } finally {
    saving.value = false;
  }
}

onMounted(() => {
  void loadPlatforms();
});

defineExpose({ save, canSave, loading });
</script>
