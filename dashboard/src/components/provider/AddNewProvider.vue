<template>
  <v-dialog v-model="showDialog" max-width="1000px" scrollable>
    <v-card
      class="add-provider-dialog__card"
      :title="tm('dialogs.addProvider.title')"
    >
      <v-card-text class="add-provider-dialog__content">
        <v-tabs v-model="activeProviderTab" grow>
          <v-tab value="speech_to_text" class="font-weight-medium px-3">
            <v-icon start>mdi-microphone-message</v-icon>
            {{ tm('dialogs.addProvider.tabs.speechToText') }}
          </v-tab>
          <v-tab value="text_to_speech" class="font-weight-medium px-3">
            <v-icon start>mdi-volume-high</v-icon>
            {{ tm('dialogs.addProvider.tabs.textToSpeech') }}
          </v-tab>
          <v-tab value="embedding" class="font-weight-medium px-3">
            <v-icon start>mdi-code-json</v-icon>
            {{ tm('dialogs.addProvider.tabs.embedding') }}
          </v-tab>
          <v-tab value="rerank" class="font-weight-medium px-3">
            <v-icon start>mdi-compare-vertical</v-icon>
            {{ tm('dialogs.addProvider.tabs.rerank') }}
          </v-tab>
        </v-tabs>

        <v-window v-model="activeProviderTab" class="mt-4">
          <v-window-item
            v-for="tabType in PROVIDER_WINDOW_TABS"
            :key="tabType"
            :value="tabType"
          >
            <v-row class="mt-1">
              <v-col
                v-for="(template, name) in getTemplatesByType(tabType)"
                :key="name"
                cols="12"
                sm="6"
                md="4"
              >
                <v-card
                  variant="outlined"
                  hover
                  class="provider-card"
                  @click="selectProviderTemplate(name)"
                >
                  <div class="provider-card-content">
                    <div class="provider-card-text">
                      <v-card-title class="provider-card-title">{{
                        name
                      }}</v-card-title>
                      <v-card-text
                        class="text-caption text-medium-emphasis provider-card-description"
                      >
                        {{ getTemplateDescription(template, name) }}
                      </v-card-text>
                    </div>
                    <div class="provider-card-logo">
                      <img
                        v-if="resolveProviderIcon(template.provider)"
                        :src="resolveProviderIcon(template.provider)"
                        :class="[
                          'provider-logo-img',
                          {
                            'provider-icon--monochrome':
                              isMonochromeProviderIcon(template.provider || ''),
                          },
                        ]"
                      />
                      <div v-else class="provider-logo-fallback">
                        {{ name[0].toUpperCase() }}
                      </div>
                    </div>
                  </div>
                </v-card>
              </v-col>
              <v-col
                v-if="Object.keys(getTemplatesByType(tabType)).length === 0"
                cols="12"
              >
                <v-alert type="info" variant="tonal">
                  {{ tm('dialogs.addProvider.noTemplates') }}
                </v-alert>
              </v-col>
            </v-row>
          </v-window-item>
        </v-window>
      </v-card-text>
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn text @click="closeDialog">{{
          tm('dialogs.config.cancel')
        }}</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useModuleI18n } from '@/i18n/composables';
import {
  getProviderIcon,
  getProviderDescription as describeProvider,
  isMonochromeProviderIcon,
} from '@/utils/providerUtils';

type ProviderTab =
  | 'chat_completion'
  | 'speech_to_text'
  | 'text_to_speech'
  | 'embedding'
  | 'rerank';

interface ProviderTemplate {
  type?: string;
  provider?: string;
  provider_type?: ProviderTab;
}

interface ProviderTemplateMetadata {
  provider?: {
    config_template?: Record<string, ProviderTemplate>;
  };
}

const AVAILABLE_PROVIDER_TABS: ProviderTab[] = [
  'speech_to_text',
  'text_to_speech',
  'embedding',
  'rerank',
];

const PROVIDER_WINDOW_TABS: ProviderTab[] = [
  'chat_completion',
  ...AVAILABLE_PROVIDER_TABS,
];

const props = withDefaults(
  defineProps<{
    show?: boolean;
    metadata?: unknown;
    currentProviderType?: ProviderTab;
  }>(),
  {
    show: false,
    metadata: () => ({}),
    currentProviderType: 'speech_to_text',
  },
);

const emit = defineEmits<{
  'update:show': [value: boolean];
  'select-template': [name: string];
}>();

const { tm } = useModuleI18n('features/provider');

const activeProviderTab = ref<ProviderTab>('speech_to_text');

const showDialog = computed({
  get: () => props.show,
  set: (value: boolean) => void emit('update:show', value),
});

const normalizedMetadata = computed<ProviderTemplateMetadata>(() => {
  if (!props.metadata || typeof props.metadata !== 'object') {
    return {};
  }
  const provider = Reflect.get(props.metadata, 'provider');
  if (!provider || typeof provider !== 'object') {
    return {};
  }
  const configTemplate = Reflect.get(provider, 'config_template');
  if (!configTemplate || typeof configTemplate !== 'object') {
    return { provider: {} };
  }
  return {
    provider: {
      config_template: configTemplate as Record<string, ProviderTemplate>,
    },
  };
});

function syncActiveProviderTab() {
  activeProviderTab.value = AVAILABLE_PROVIDER_TABS.includes(
    props.currentProviderType,
  )
    ? props.currentProviderType
    : 'speech_to_text';
}

function closeDialog() {
  showDialog.value = false;
}

function getTemplatesByType(type: ProviderTab) {
  const templates = normalizedMetadata.value.provider?.config_template ?? {};
  return Object.fromEntries(
    Object.entries(templates).filter(
      ([, template]) => template.provider_type === type,
    ),
  );
}

function resolveProviderIcon(provider?: string) {
  return provider ? getProviderIcon(provider) : '';
}

function getTemplateDescription(template: ProviderTemplate, name: string) {
  return describeProvider(template, name, tm);
}

function selectProviderTemplate(name: string) {
  emit('select-template', name);
  closeDialog();
}

watch(
  () => props.show,
  (value) => {
    if (value) {
      syncActiveProviderTab();
    }
  },
);

watch(
  () => props.currentProviderType,
  () => {
    if (showDialog.value) {
      syncActiveProviderTab();
    }
  },
);
</script>

<style scoped>
.provider-card {
  transition: all 0.3s ease;
  height: 100%;
  cursor: pointer;
  overflow: hidden;
  position: relative;
}

.add-provider-dialog__card {
  display: flex;
  flex-direction: column;
  max-height: min(88dvh, 960px);
}

.add-provider-dialog__content {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
}

.provider-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 4px 25px 0 rgba(0, 0, 0, 0.05);
  border-color: var(--v-primary-base);
}

.provider-card-content {
  display: flex;
  align-items: center;
  height: 100px;
  padding: 16px;
  position: relative;
  z-index: 2;
}

.provider-card-text {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.provider-card-title {
  font-size: 15px;
  font-weight: 600;
  margin-bottom: 4px;
  padding: 0;
}

.provider-card-description {
  padding: 0;
  margin: 0;
}

.provider-card-logo {
  position: absolute;
  right: 0;
  top: 0;
  bottom: 0;
  width: 80px;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1;
}

.provider-logo-img {
  width: 60px;
  height: 60px;
  opacity: 0.6;
  object-fit: contain;
}

.provider-logo-fallback {
  width: 50px;
  height: 50px;
  border-radius: 50%;
  background-color: var(--v-primary-base);
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  font-weight: bold;
  opacity: 0.3;
}
</style>
