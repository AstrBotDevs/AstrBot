<template>
  <section class="ai-config-panel">
    <header class="ai-config-panel__header">
      <div class="ai-config-panel__heading">
        <h2 class="ai-config-panel__title">{{ tm('aiSettings.title') }}</h2>
        <p class="ai-config-panel__subtitle">{{ currentRunner.summary }}</p>
      </div>

      <div class="ai-config-panel__actions">
        <label class="ai-enable-control">
          <v-switch
            v-model="aiEnabled"
            color="primary"
            density="compact"
            hide-details
            inset
            :aria-label="tm('aiSettings.enable')"
            :title="tm('aiSettings.enable')"
          />
        </label>

        <StyledMenu location="bottom end" :offset="8">
          <template #activator="{ props: menuProps }">
            <v-btn
              v-bind="menuProps"
              icon="mdi-dots-horizontal"
              size="small"
              variant="text"
              :aria-label="tm('aiSettings.more')"
              :title="tm('aiSettings.more')"
            />
          </template>
          <v-list-item
            class="styled-menu-item"
            prepend-icon="mdi-swap-horizontal"
            :title="tm('aiSettings.changeRunner')"
            @click="openRunnerDialog"
          />
        </StyledMenu>
      </div>
    </header>

    <template v-if="aiEnabled">
      <section class="ai-config-panel__section">
        <div class="ai-config-panel__section-heading">
          <div>
            <h3 class="ai-config-panel__section-title">
              <span>{{ runnerSettingsTitle }}</span>
              <img
                v-if="runnerType === 'local'"
                class="ai-config-panel__brand-logo"
                src="@/assets/images/plugin_icon.png"
                alt=""
              />
            </h3>
            <p class="ai-config-panel__section-subtitle">
              {{ currentRunner.description }}
            </p>
          </div>
        </div>

        <template v-if="runnerType === 'local'">
          <div
            class="ai-config-tabs"
            role="tablist"
            :aria-label="runnerSettingsTitle"
          >
            <button
              v-for="item in localTabs"
              :key="item.value"
              type="button"
              class="ai-config-tabs__item"
              :class="{
                'ai-config-tabs__item--active': activeLocalTab === item.value,
              }"
              role="tab"
              :aria-selected="activeLocalTab === item.value"
              @click="activeLocalTab = item.value"
            >
              {{ item.label }}
            </button>
          </div>

          <div class="config-product-groups">
            <AstrBotConfigV4
              v-for="group in activeLocalGroups"
              :key="group.key"
              :metadata="{ [group.key]: group.metadata }"
              :iterable="configData"
              :metadata-key="group.key"
              :search-keyword="searchKeyword"
            />
          </div>
        </template>

        <div v-else class="config-product-groups">
          <AstrBotConfigV4
            v-if="thirdPartyRunnerGroup"
            :metadata="{
              [thirdPartyRunnerGroup.key]: thirdPartyRunnerGroup.metadata,
            }"
            :iterable="configData"
            :metadata-key="thirdPartyRunnerGroup.key"
            :search-keyword="searchKeyword"
          />
        </div>
      </section>

      <section
        v-if="commonGroups.length"
        class="ai-config-panel__section ai-config-panel__section--common"
      >
        <div class="ai-config-panel__section-heading">
          <div>
            <h3 class="ai-config-panel__section-title">
              {{ tm('aiSettings.common.title') }}
            </h3>
            <p class="ai-config-panel__section-subtitle">
              {{ tm('aiSettings.common.subtitle') }}
            </p>
          </div>
        </div>

        <div class="config-product-groups">
          <AstrBotConfigV4
            v-for="group in commonGroups"
            :key="group.key"
            :metadata="{ [group.key]: group.metadata }"
            :iterable="configData"
            :metadata-key="group.key"
            :search-keyword="searchKeyword"
          />
        </div>
      </section>
    </template>

    <div v-else class="ai-disabled-state">
      <v-icon size="30">mdi-robot-off-outline</v-icon>
      <div>
        <div class="ai-disabled-state__title">
          {{ tm('aiSettings.disabled.title') }}
        </div>
        <div class="ai-disabled-state__subtitle">
          {{ tm('aiSettings.disabled.subtitle') }}
        </div>
      </div>
    </div>

    <v-dialog v-model="runnerDialog" max-width="560">
      <v-card class="runner-dialog-card">
        <v-card-title class="text-h3 pa-4 pb-0 pl-6">
          {{ tm('aiSettings.runnerDialog.title') }}
        </v-card-title>
        <v-card-text class="px-6 pt-3 pb-2">
          <p class="runner-dialog-description">
            {{ tm('aiSettings.runnerDialog.subtitle') }}
          </p>

          <div class="runner-option-list" role="radiogroup">
            <button
              v-for="runner in runnerOptions"
              :key="runner.value"
              type="button"
              class="runner-option"
              :class="{
                'runner-option--active': pendingRunnerType === runner.value,
              }"
              role="radio"
              :aria-checked="pendingRunnerType === runner.value"
              @click="pendingRunnerType = runner.value"
            >
              <div class="runner-option__copy">
                <div class="runner-option__title">{{ runner.title }}</div>
                <div class="runner-option__description">
                  {{ runner.description }}
                </div>
              </div>
              <v-icon
                v-if="pendingRunnerType === runner.value"
                color="primary"
                size="20"
              >
                mdi-check-circle
              </v-icon>
              <v-icon v-else size="20" class="runner-option__empty-icon">
                mdi-circle-outline
              </v-icon>
            </button>
          </div>

          <v-checkbox
            v-model="runnerChangeAcknowledged"
            class="runner-dialog-acknowledgement"
            color="primary"
            density="compact"
            hide-details
            :disabled="pendingRunnerType === runnerType"
          >
            <template #label>
              <span class="runner-dialog-acknowledgement__label">
                {{ tm('aiSettings.runnerDialog.warningPrefix')
                }}<strong>{{
                  tm('aiSettings.runnerDialog.warningEmphasis')
                }}</strong
                >{{ tm('aiSettings.runnerDialog.warningSuffix') }}
              </span>
            </template>
          </v-checkbox>
        </v-card-text>
        <v-card-actions class="pa-4 pt-2">
          <v-spacer />
          <v-btn variant="text" @click="runnerDialog = false">
            {{ tm('buttons.cancel') }}
          </v-btn>
          <v-btn
            color="primary"
            variant="tonal"
            :disabled="
              pendingRunnerType === runnerType || !runnerChangeAcknowledged
            "
            @click="confirmRunnerChange"
          >
            {{ tm('aiSettings.runnerDialog.confirm') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </section>
</template>

<script setup>
import { computed, ref, watch } from 'vue';
import AstrBotConfigV4 from '@/components/shared/AstrBotConfigV4.vue';
import StyledMenu from '@/components/shared/StyledMenu.vue';
import { useModuleI18n } from '@/i18n/composables';

const props = defineProps({
  metadata: {
    type: Object,
    required: true,
    default: () => ({}),
  },
  configData: {
    type: Object,
    required: true,
    default: () => ({}),
  },
  searchKeyword: {
    type: String,
    default: '',
  },
});

const { tm } = useModuleI18n('features/config');

const runnerDialog = ref(false);
const pendingRunnerType = ref('local');
const runnerChangeAcknowledged = ref(false);
const activeLocalTab = ref('model');

const aiEnabled = computed({
  get() {
    return props.configData?.provider_settings?.enable !== false;
  },
  set(value) {
    if (!props.configData.provider_settings) {
      props.configData.provider_settings = {};
    }
    props.configData.provider_settings.enable = value;
  },
});

const runnerType = computed(
  () => props.configData?.agent_runner?.runner_type || 'local',
);
const runnerTypeMetadata = computed(
  () => props.metadata?.agent_runner?.items?.['agent_runner.runner_type'] || {},
);

const runnerOptions = computed(() => {
  const availableTypes = runnerTypeMetadata.value.options || [
    'local',
    'dify',
    'coze',
    'dashscope',
    'deerflow',
  ];
  return availableTypes.map((value) => ({
    value,
    title: tm(`aiSettings.runners.${value}.title`),
    description: tm(`aiSettings.runners.${value}.description`),
    summary: tm(`aiSettings.runners.${value}.summary`),
  }));
});

const currentRunner = computed(
  () =>
    runnerOptions.value.find((runner) => runner.value === runnerType.value) ||
    runnerOptions.value[0] || {
      value: 'local',
      title: 'AI',
      description: '',
      summary: '',
    },
);

const runnerSettingsTitle = computed(() =>
  runnerType.value === 'local'
    ? tm('aiSettings.localSettingsTitle')
    : `${currentRunner.value.title} ${tm('aiSettings.settingsSuffix')}`,
);

const localTabs = computed(() => [
  { value: 'model', label: tm('aiSettings.tabs.model') },
  { value: 'persona', label: tm('aiSettings.tabs.persona') },
  { value: 'capabilities', label: tm('aiSettings.tabs.capabilities') },
  { value: 'advanced', label: tm('aiSettings.tabs.advanced') },
]);

function filterMetadataGroup(groupKey, itemFilter, overrides = {}) {
  const source = props.metadata?.[groupKey];
  if (!source) return null;
  const items = Object.fromEntries(
    Object.entries(source.items || {}).filter(([itemKey, itemMeta]) =>
      itemFilter(itemKey, itemMeta),
    ),
  );
  if (Object.keys(items).length === 0) return null;
  return {
    key: groupKey,
    metadata: {
      ...source,
      ...overrides,
      items,
    },
  };
}

const localTabGroups = computed(() => {
  const modelGroup = filterMetadataGroup(
    'ai',
    (itemKey) => itemKey.startsWith('agent_runner.config.model.'),
    {
      description: tm('aiSettings.groups.model'),
      hint: tm('aiSettings.groups.modelHint'),
    },
  );
  const executionGroup = filterMetadataGroup(
    'others',
    (itemKey) => itemKey.startsWith('agent_runner.config.misc.'),
    {
      description: tm('aiSettings.groups.execution'),
      hint: tm('aiSettings.groups.executionHint'),
    },
  );

  return {
    model: [modelGroup].filter(Boolean),
    persona: props.metadata?.persona
      ? [{ key: 'persona', metadata: props.metadata.persona }]
      : [],
    capabilities: [
      'knowledgebase',
      'websearch',
      'agent_computer_use',
      'proactive_capability',
    ]
      .filter((key) => props.metadata?.[key])
      .map((key) => ({
        key,
        metadata: props.metadata[key],
      })),
    advanced: [
      props.metadata?.truncate_and_compress
        ? {
            key: 'truncate_and_compress',
            metadata: props.metadata.truncate_and_compress,
          }
        : null,
      executionGroup,
    ].filter(Boolean),
  };
});

const activeLocalGroups = computed(
  () =>
    localTabGroups.value[activeLocalTab.value] || localTabGroups.value.model,
);

const normalizedSearchKeyword = computed(() =>
  String(props.searchKeyword || '')
    .trim()
    .toLowerCase(),
);

function metadataMatchesSearch(metaObject, keyword) {
  if (!metaObject || typeof metaObject !== 'object') {
    return false;
  }
  const directText = [
    tm(metaObject.description || ''),
    tm(metaObject.hint || ''),
  ]
    .join(' ')
    .toLowerCase();
  if (directText.includes(keyword)) {
    return true;
  }
  return Object.entries(metaObject.items || {}).some(
    ([itemKey, itemMeta]) =>
      itemKey.toLowerCase().includes(keyword) ||
      metadataMatchesSearch(itemMeta, keyword),
  );
}

function tabMatchesSearch(tabValue, keyword) {
  return (localTabGroups.value[tabValue] || []).some((group) =>
    metadataMatchesSearch(group.metadata, keyword),
  );
}

const thirdPartyRunnerGroup = computed(() => {
  const key = `${runnerType.value}_runner`;
  return props.metadata?.[key] ? { key, metadata: props.metadata[key] } : null;
});

const commonGroups = computed(() =>
  [
    filterMetadataGroup(
      'ai',
      (itemKey) => !itemKey.startsWith('agent_runner.config.'),
      {
        description: tm('aiSettings.groups.media'),
        hint: tm('aiSettings.groups.mediaHint'),
      },
    ),
    filterMetadataGroup(
      'others',
      (itemKey) => !itemKey.startsWith('agent_runner.config.'),
      {
        description: tm('aiSettings.groups.behavior'),
        hint: tm('aiSettings.groups.behaviorHint'),
      },
    ),
  ].filter(Boolean),
);

watch(
  [runnerType, normalizedSearchKeyword],
  ([nextRunner, keyword], previous) => {
    if (nextRunner !== previous?.[0]) {
      activeLocalTab.value = 'model';
      return;
    }
    if (!keyword || runnerType.value !== 'local') {
      return;
    }
    const matchingTab = localTabs.value.find((tab) =>
      tabMatchesSearch(tab.value, keyword),
    );
    if (matchingTab) {
      activeLocalTab.value = matchingTab.value;
    }
  },
);

watch(pendingRunnerType, () => {
  runnerChangeAcknowledged.value = false;
});

function openRunnerDialog() {
  pendingRunnerType.value = runnerType.value;
  runnerChangeAcknowledged.value = false;
  runnerDialog.value = true;
}

function confirmRunnerChange() {
  const nextRunnerType = pendingRunnerType.value;
  if (nextRunnerType !== runnerType.value) {
    const defaults =
      runnerTypeMetadata.value.runner_defaults?.[nextRunnerType] || {};
    if (!props.configData.agent_runner) {
      props.configData.agent_runner = {};
    }
    props.configData.agent_runner.runner_type = nextRunnerType;
    props.configData.agent_runner.config = JSON.parse(JSON.stringify(defaults));
  }
  runnerChangeAcknowledged.value = false;
  runnerDialog.value = false;
}
</script>

<style scoped>
.ai-config-panel {
  min-width: 0;
}

.ai-config-panel__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 30px;
}

.ai-config-panel__heading {
  min-width: 0;
}

.ai-config-panel__title {
  margin: 0;
  color: rgb(var(--v-theme-on-surface));
  font-size: 1.34rem;
  font-weight: 780;
  letter-spacing: 0;
  line-height: 1.25;
}

.ai-config-panel__subtitle,
.ai-config-panel__section-subtitle {
  margin: 5px 0 0;
  color: rgba(var(--v-theme-on-surface), 0.62);
  font-size: 0.78rem;
  line-height: 1.45;
}

.ai-config-panel__actions {
  display: flex;
  align-items: center;
  gap: 4px;
  flex: 0 0 auto;
}

.ai-enable-control {
  display: flex;
  align-items: center;
  cursor: pointer;
}

.ai-enable-control :deep(.v-switch) {
  flex: 0 0 auto;
}

.ai-config-panel__section {
  min-width: 0;
}

.ai-config-panel__section--common {
  margin-top: 32px;
  padding-top: 28px;
  border-top: 1px solid rgba(17, 24, 39, 0.09);
}

.ai-config-panel__section-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 12px;
}

.ai-config-panel__section-title {
  display: flex;
  align-items: center;
  gap: 7px;
  margin: 0;
  color: rgb(var(--v-theme-on-surface));
  font-size: 1.04rem;
  font-weight: 760;
  line-height: 1.32;
}

.ai-config-panel__brand-logo {
  flex: 0 0 auto;
  width: 18px;
  height: 18px;
}

.ai-config-tabs {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-bottom: 14px;
  overflow-x: auto;
}

.ai-config-tabs__item {
  flex: 0 0 auto;
  min-height: 30px;
  padding: 5px 12px;
  border: 0;
  border-radius: 7px;
  background: transparent;
  color: rgba(var(--v-theme-on-surface), 0.58);
  cursor: pointer;
  font: inherit;
  font-size: 0.78rem;
  font-weight: 650;
}

.ai-config-tabs__item:hover {
  color: rgb(var(--v-theme-on-surface));
  background: rgba(var(--v-theme-on-surface), 0.045);
}

.ai-config-tabs__item--active {
  color: rgb(var(--v-theme-on-surface));
  background: rgba(var(--v-theme-on-surface), 0.08);
  font-weight: 740;
}

.ai-disabled-state {
  display: flex;
  align-items: center;
  gap: 14px;
  min-height: 88px;
  padding: 16px 18px;
  border: 1px solid rgba(17, 24, 39, 0.13);
  border-radius: 10px;
  color: rgba(var(--v-theme-on-surface), 0.5);
  background: rgb(var(--v-theme-surface));
}

.ai-disabled-state__title {
  color: rgba(var(--v-theme-on-surface), 0.78);
  font-size: 0.88rem;
  font-weight: 700;
}

.ai-disabled-state__subtitle {
  margin-top: 3px;
  font-size: 0.78rem;
  line-height: 1.45;
}

.runner-dialog-card {
  border-radius: 14px !important;
}

.runner-dialog-description {
  margin: 0 0 16px;
  color: rgba(var(--v-theme-on-surface), 0.64);
  font-size: 0.84rem;
  line-height: 1.5;
}

.runner-option-list {
  overflow: hidden;
  border: 1px solid rgba(17, 24, 39, 0.13);
  border-radius: 10px;
}

.runner-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  width: 100%;
  min-height: 64px;
  padding: 11px 14px;
  border: 0;
  border-bottom: 1px solid rgba(17, 24, 39, 0.09);
  background: transparent;
  color: inherit;
  cursor: pointer;
  font: inherit;
  text-align: left;
}

.runner-option:last-child {
  border-bottom: 0;
}

.runner-option:hover,
.runner-option--active {
  background: rgba(var(--v-theme-primary), 0.055);
}

.runner-option__copy {
  min-width: 0;
}

.runner-option__title {
  color: rgb(var(--v-theme-on-surface));
  font-size: 0.86rem;
  font-weight: 700;
}

.runner-option__description {
  margin-top: 3px;
  color: rgba(var(--v-theme-on-surface), 0.58);
  font-size: 0.76rem;
  line-height: 1.4;
}

.runner-option__empty-icon {
  color: rgba(var(--v-theme-on-surface), 0.28);
}

.runner-dialog-acknowledgement {
  margin-top: 14px;
}

.runner-dialog-acknowledgement__label {
  color: rgba(var(--v-theme-on-surface), 0.58);
  font-size: 0.76rem;
  line-height: 1.45;
}

.runner-dialog-acknowledgement__label strong {
  font-weight: 700;
}

@media (max-width: 600px) {
  .ai-config-panel__header {
    align-items: stretch;
    flex-direction: column;
    gap: 14px;
  }

  .ai-config-panel__actions {
    justify-content: space-between;
  }

  .ai-enable-control {
    flex: 1;
  }
}
</style>
