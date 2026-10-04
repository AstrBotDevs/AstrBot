<template>
  <section class="ai-config-panel">
    <header class="ai-config-panel__header">
      <div class="ai-config-panel__heading">
        <h2 class="ai-config-panel__title">{{ tm("aiSettings.title") }}</h2>
        <p class="ai-config-panel__subtitle">
          {{ tm("hierarchy.descriptions.ai_group") }}
        </p>
      </div>
      <div class="ai-config-panel__actions">
        <v-switch
          v-model="aiEnabled"
          color="primary"
          density="compact"
          hide-details
          inset
          :label="tm('aiSettings.enable')"
        />
        <v-menu>
          <template #activator="{ props: menuProps }">
            <v-btn
              v-bind="menuProps"
              icon="mdi-dots-horizontal"
              variant="text"
              size="small"
              :aria-label="tm('aiSettings.more')"
            />
          </template>
          <v-list density="compact">
            <v-list-item
              prepend-icon="mdi-swap-horizontal"
              :title="tm('aiSettings.changeRunner')"
              @click="openRunnerDialog"
            />
          </v-list>
        </v-menu>
      </div>
    </header>

    <div v-if="!aiEnabled && !searchKeyword.trim()" class="ai-disabled-state">
      <v-icon size="30">mdi-robot-off-outline</v-icon>
      <div>
        <div class="ai-disabled-state__title">
          {{ tm("aiSettings.disabled.title") }}
        </div>
        <div class="ai-disabled-state__subtitle">
          {{ tm("aiSettings.disabled.subtitle") }}
        </div>
      </div>
    </div>

    <section class="ai-config-panel__section">
      <div v-if="aiEnabled" class="ai-config-panel__section-heading">
        <div>
          <h3 class="ai-config-panel__section-title">
            <span>{{ runnerSettingsTitle }}</span>
            <AstrBotLogo
              v-if="runnerType === 'local'"
              class="ai-config-panel__brand-logo"
            />
          </h3>
          <p class="ai-config-panel__section-subtitle">
            {{ currentRunner.description }}
          </p>
        </div>
      </div>
      <ConfigGroupTabs
        v-if="aiEnabled"
        :key="runnerType"
        :metadata="runnerGroups"
        :config-data="configData"
        :tabs="
          runnerType === 'local'
            ? ['model', 'persona', 'input', 'capabilities', 'context']
            : ['connection', 'application']
        "
        :label="runnerSettingsTitle"
        :search-keyword="searchKeyword"
        :show-empty="!searchKeyword.trim()"
      />
    </section>

    <ConfigGroupTabs
      v-if="Object.keys(otherGroups).length > 0"
      :metadata="otherGroups"
      :config-data="configData"
      :label="tm('aiSettings.title')"
      :search-keyword="searchKeyword"
      :show-empty="false"
    />
    <v-dialog v-model="runnerDialog" max-width="560">
      <v-card class="runner-dialog-card">
        <v-card-title class="text-h3 pa-4 pb-0 pl-6">
          {{ tm("aiSettings.runnerDialog.title") }}
        </v-card-title>
        <v-card-text class="px-6 pt-3 pb-2">
          <p class="runner-dialog-description">
            {{ tm("aiSettings.runnerDialog.subtitle") }}
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
                {{ tm("aiSettings.runnerDialog.warningPrefix")
                }}<strong>{{
                  tm("aiSettings.runnerDialog.warningEmphasis")
                }}</strong
                >{{ tm("aiSettings.runnerDialog.warningSuffix") }}
              </span>
            </template>
          </v-checkbox>
        </v-card-text>
        <v-card-actions class="pa-4 pt-2">
          <v-spacer />
          <v-btn variant="text" @click="runnerDialog = false">
            {{ tm("buttons.cancel") }}
          </v-btn>
          <v-btn
            color="primary"
            variant="tonal"
            :disabled="
              pendingRunnerType === runnerType || !runnerChangeAcknowledged
            "
            @click="confirmRunnerChange"
          >
            {{ tm("aiSettings.runnerDialog.confirm") }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </section>
</template>

<script setup>
import { computed, ref, watch } from "vue";
import AstrBotLogo from "@/components/chat/ChatUILogo.vue";
import ConfigGroupTabs from "@/components/config/ConfigGroupTabs.vue";
import { useModuleI18n } from "@/i18n/composables";

const props = defineProps({
  metadata: { type: Object, required: true },
  configData: { type: Object, required: true },
  searchKeyword: { type: String, default: "" },
});
const { tm } = useModuleI18n("features/config");
const runnerDialog = ref(false);
const pendingRunnerType = ref("local");
const runnerChangeAcknowledged = ref(false);
const aiEnabled = computed({
  get: () => props.configData?.provider_settings?.enable !== false,
  set(value) {
    props.configData.provider_settings ||= {};
    props.configData.provider_settings.enable = value;
  },
});
const runnerType = computed(
  () => props.configData?.agent_runner?.runner_type || "local",
);
const runnerTypeMetadata = computed(
  () => props.metadata?.agent_runner?.items?.["agent_runner.runner_type"] || {},
);
const runnerOptions = computed(() =>
  (
    runnerTypeMetadata.value.options || [
      "local",
      "dify",
      "coze",
      "dashscope",
      "deerflow",
    ]
  ).map((value) => ({
    value,
    title: tm(`aiSettings.runners.${value}.title`),
    description: tm(`aiSettings.runners.${value}.description`),
  })),
);
const currentRunner = computed(
  () =>
    runnerOptions.value.find((runner) => runner.value === runnerType.value) ||
    runnerOptions.value[0],
);
const runnerSettingsTitle = computed(() =>
  runnerType.value === "local"
    ? tm("aiSettings.localSettingsTitle")
    : `${currentRunner.value.title} ${tm("aiSettings.settingsSuffix")}`,
);
const runnerGroups = computed(() =>
  Object.fromEntries(
    Object.entries(props.metadata)
      .filter(([, group]) => group.runner === runnerType.value)
      .map(([key, group]) => [
        key,
        key === "local_model"
          ? {
              ...group,
              items: {
                ...group.items,
                "agent_runner.config.model.provider_id": {
                  ...group.items["agent_runner.config.model.provider_id"],
                  hint: "",
                },
              },
            }
          : group,
      ]),
  ),
);
const otherGroups = computed(() =>
  Object.fromEntries(
    Object.entries(props.metadata).filter(
      ([key, group]) => key !== "agent_runner" && !group.runner,
    ),
  ),
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
    props.configData.agent_runner ||= {};
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

.ai-config-panel__section {
  min-width: 0;
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

.ai-config-panel__actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-shrink: 0;
  gap: 8px;
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
}
</style>
