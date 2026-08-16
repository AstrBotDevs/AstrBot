<template>
  <v-dialog
    :model-value="modelValue"
    max-width="720"
    @update:model-value="emitModelValue"
  >
    <v-card>
      <v-card-title class="text-h3 pa-4 pb-0 pl-6 d-flex align-center">
        <v-icon class="me-2" color="secondary">
          mdi-lightning-bolt-outline
        </v-icon>
        {{ tm('quickActions.title') }}
      </v-card-title>
      <v-card-text class="px-4 pb-4">
        <div class="quick-actions__intro mb-4">
          {{ tm('quickActions.description') }}
        </div>
        <div class="quick-actions__platform mb-4">
          <strong>{{ tm('quickActions.platformId') }}:</strong>
          {{ platformId || '-' }}
        </div>
        <div
          v-if="quickActionCategories.length > 1"
          class="quick-actions__categories mb-4"
        >
          <div class="quick-actions__categories-label mb-2">
            {{ tm('quickActions.categoryLabel') }}
          </div>
          <v-chip-group
            v-model="selectedQuickActionCategory"
            selected-class="text-secondary"
            mandatory
          >
            <v-chip
              v-for="category in quickActionCategories"
              :key="category"
              :value="category"
              size="small"
              variant="outlined"
              filter
            >
              {{ getQuickActionCategoryLabel(category) }}
            </v-chip>
          </v-chip-group>
        </div>
        <v-select
          v-model="selectedQuickAction"
          :items="quickActionItems"
          item-title="title"
          item-value="value"
          :label="tm('quickActions.selectAction')"
          variant="outlined"
          density="comfortable"
          class="mb-4"
        />
        <v-alert
          v-if="currentQuickActionDefinition?.help"
          variant="tonal"
          color="info"
          class="mb-4"
        >
          {{ currentQuickActionDefinition.help }}
        </v-alert>
        <div
          v-if="currentQuickActionDefinition?.fields.length"
          class="quick-actions__fields"
        >
          <template
            v-for="field in currentQuickActionDefinition.fields"
            :key="field.key"
          >
            <v-textarea
              v-if="field.kind === 'textarea' || field.kind === 'string-list'"
              v-model="quickActionForm[field.key]"
              :label="field.label"
              :hint="field.hint"
              :placeholder="field.placeholder"
              :rows="field.kind === 'string-list' ? 3 : 4"
              :persistent-hint="Boolean(field.hint)"
              variant="outlined"
              density="comfortable"
              auto-grow
              class="mb-3"
            />
            <v-switch
              v-else-if="field.kind === 'boolean'"
              v-model="quickActionForm[field.key]"
              :label="field.label"
              :hint="field.hint"
              :persistent-hint="Boolean(field.hint)"
              color="secondary"
              inset
              class="mb-2"
            />
            <v-text-field
              v-else
              v-model="quickActionForm[field.key]"
              :label="field.label"
              :hint="field.hint"
              :placeholder="field.placeholder"
              :persistent-hint="Boolean(field.hint)"
              :type="field.kind === 'number' ? 'number' : 'text'"
              variant="outlined"
              density="comfortable"
              class="mb-3"
            />
          </template>
        </div>
        <v-alert v-else variant="tonal" color="warning">
          {{ tm('quickActions.noAction') }}
        </v-alert>
        <div v-if="quickActionResult" class="quick-actions__result mt-4">
          <div class="quick-actions__result-header">
            <div class="quick-actions__result-label">
              {{ tm('quickActions.result') }}
            </div>
            <v-btn
              size="small"
              variant="text"
              prepend-icon="mdi-content-copy"
              @click="copyQuickActionResult"
            >
              {{ tm('quickActions.copyResult') }}
            </v-btn>
          </div>
          <div
            v-if="quickActionResultSummary.length > 0"
            class="quick-actions__summary"
          >
            <v-chip
              v-for="item in quickActionResultSummary"
              :key="item.label"
              size="small"
              variant="tonal"
              color="secondary"
            >
              {{ item.label }}: {{ item.value }}
            </v-chip>
          </div>
          <pre class="quick-actions__result-box">{{ quickActionResult }}</pre>
        </div>
      </v-card-text>
      <v-card-actions class="pa-4 pt-0">
        <v-spacer></v-spacer>
        <v-btn variant="text" @click="emitModelValue(false)">
          {{ tm('quickActions.close') }}
        </v-btn>
        <v-btn
          color="secondary"
          variant="tonal"
          :loading="runningQuickAction"
          :disabled="!selectedQuickAction"
          @click="runQuickAction"
        >
          {{
            runningQuickAction
              ? tm('quickActions.running')
              : tm('quickActions.run')
          }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { botApi } from '@/api/v1';
import {
  buildQuickActionDefinitions,
  getQuickActionableActions,
  type QuickActionCategory,
  type QuickActionDefinition,
  type QuickActionName,
} from '@/components/platform/platformQuickActions';
import {
  buildQuickActionPayload as buildQuickActionPayloadData,
  buildQuickActionResultSummary,
  createInitialQuickActionForm as createInitialQuickActionFormData,
} from '@/components/platform/platformQuickActionRuntime';
import { useModuleI18n } from '@/i18n/composables';
import { copyToClipboard } from '@/utils/clipboard';
import { resolveErrorMessage } from '@/utils/errorUtils';

defineOptions({
  name: 'PlatformQuickActionsDialog',
});

const props = defineProps<{
  modelValue: boolean;
  platformId: string;
  supportedActions: string[];
}>();

const emit = defineEmits<{
  'update:modelValue': [value: boolean];
  'show-toast': [payload: { message: string; type: 'success' | 'error' }];
  'action-complete': [];
}>();

const { tm } = useModuleI18n('features/platform');
const selectedQuickAction = ref<QuickActionName | ''>('');
const selectedQuickActionCategory = ref<QuickActionCategory>('all');
const quickActionForm = ref<Record<string, string | number | boolean>>({});
const runningQuickAction = ref(false);
const quickActionResult = ref('');

const quickActionDefinitions = computed<
  Record<QuickActionName, QuickActionDefinition>
>(() => buildQuickActionDefinitions(tm));

const quickActionableActions = computed<QuickActionName[]>(() =>
  getQuickActionableActions(props.supportedActions),
);
const currentQuickActionDefinition = computed<QuickActionDefinition | null>(
  () =>
    selectedQuickAction.value
      ? quickActionDefinitions.value[selectedQuickAction.value]
      : null,
);
const quickActionCategories = computed<QuickActionCategory[]>(() => {
  const categories = new Set<QuickActionCategory>(['all']);
  for (const action of quickActionableActions.value) {
    categories.add(quickActionDefinitions.value[action].category);
  }
  return Array.from(categories);
});
const quickActionItems = computed(() =>
  quickActionableActions.value
    .filter((action) => {
      if (selectedQuickActionCategory.value === 'all') {
        return true;
      }
      return (
        quickActionDefinitions.value[action].category ===
        selectedQuickActionCategory.value
      );
    })
    .map((action) => ({
      title: getSupportedActionLabel(action),
      value: action,
    })),
);
const quickActionResultSummary = computed(() => {
  return buildQuickActionResultSummary(quickActionResult.value, tm);
});

watch(
  () => props.modelValue,
  (newValue) => {
    if (newValue) {
      selectedQuickActionCategory.value = 'all';
      selectedQuickAction.value = quickActionableActions.value[0] ?? '';
      resetQuickActionForm(selectedQuickAction.value);
    }
  },
  { immediate: true },
);

watch(selectedQuickAction, (newValue) => {
  resetQuickActionForm(newValue);
});

watch(quickActionItems, (items) => {
  if (items.length === 0) {
    selectedQuickAction.value = '';
    resetQuickActionForm('');
    return;
  }
  if (!items.some((item) => item.value === selectedQuickAction.value)) {
    selectedQuickAction.value = items[0].value;
  }
});

function emitModelValue(value: boolean) {
  emit('update:modelValue', value);
}

function getSupportedActionLabel(action: string): string {
  const translated = tm(`capabilities.actions.${action}`);
  return translated.startsWith('[MISSING:') ? action : translated;
}

function getQuickActionCategoryLabel(category: QuickActionCategory): string {
  return tm(`quickActions.categories.${category}`);
}

function createInitialQuickActionForm(
  actionName: QuickActionName | '',
): Record<string, string | number | boolean> {
  return createInitialQuickActionFormData(
    actionName,
    quickActionDefinitions.value,
  );
}

function resetQuickActionForm(actionName: QuickActionName | '') {
  quickActionForm.value = createInitialQuickActionForm(actionName);
  quickActionResult.value = '';
}

async function runQuickAction() {
  if (!props.platformId || !selectedQuickAction.value) {
    return;
  }

  runningQuickAction.value = true;
  try {
    const payload = buildQuickActionPayloadData(
      selectedQuickAction.value,
      quickActionForm.value,
      quickActionDefinitions.value,
      tm,
    );
    const res = await botApi.invokeAction(props.platformId, {
      action_name: selectedQuickAction.value,
      payload,
    });
    quickActionResult.value = JSON.stringify(res.data.data, null, 2);
    emit('show-toast', {
      message: res.data.message || tm('quickActions.success'),
      type: 'success',
    });
    emit('action-complete');
  } catch (error) {
    emit('show-toast', {
      message: resolveErrorMessage(error, tm('quickActions.failed')),
      type: 'error',
    });
  } finally {
    runningQuickAction.value = false;
  }
}

async function copyQuickActionResult() {
  if (!quickActionResult.value) {
    return;
  }
  const ok = await copyToClipboard(quickActionResult.value);
  emit('show-toast', {
    message: ok
      ? tm('quickActions.copyResultSuccess')
      : tm('quickActions.copyResultFailed'),
    type: ok ? 'success' : 'error',
  });
}
</script>

<style scoped>
.quick-actions__intro,
.quick-actions__platform,
.quick-actions__result-label {
  font-size: 13px;
  color: rgba(var(--v-theme-on-surface), 0.72);
}

.quick-actions__categories-label {
  color: rgba(var(--v-theme-on-surface), 0.72);
}

.quick-actions__categories-label,
.quick-actions__result-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.quick-actions__summary {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}

.quick-actions__result-box {
  margin-top: 8px;
  padding: 12px;
  border-radius: 8px;
  background-color: rgb(var(--v-theme-code-surface));
  color: rgb(var(--v-theme-code-text));
  font-size: 12px;
  line-height: 1.5;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 260px;
  overflow-y: auto;
}
</style>
