<template>
  <div class="dashboard-page subagent-page" :class="{ 'subagent-page--embedded': embedded }">
    <v-container fluid class="dashboard-shell pa-4 pa-md-6">
      <header class="agent-header">
        <div v-if="!embedded">
          <h1 class="dashboard-title">{{ tm('page.title') }}</h1>
          <p class="dashboard-subtitle">{{ tm('page.subtitle') }}</p>
        </div>
        <div class="d-flex ga-2">
          <v-btn variant="text" color="primary" prepend-icon="mdi-refresh" :loading="loading" @click="load">{{ tm('actions.refresh') }}</v-btn>
          <v-btn variant="tonal" color="primary" prepend-icon="mdi-plus" :disabled="!runtimes.length" @click="openEditor()">{{ tm('actions.create') }}</v-btn>
        </div>
      </header>
      <section>
        <v-progress-linear v-if="loading" indeterminate color="primary" />
        <v-alert v-if="loadError" type="error" variant="tonal" class="ma-4">{{ loadError }}</v-alert>
        <div v-if="!loading && !agents.length" class="empty-state">
          <v-icon size="48" color="primary">mdi-robot-outline</v-icon>
          <p class="text-medium-emphasis mt-3">{{ tm('section.empty') }}</p>
        </div>
        <div v-else class="agent-grid">
          <OutlinedActionListItem v-for="agent in agents" :key="agent.config_id" :title="agent.name" clickable @click="openEditor(agent)">
            <template #title-extra><v-chip size="x-small" variant="tonal" :color="runtimeAvailable(agent.runtime) ? 'primary' : 'warning'">{{ agent.runtime }}</v-chip></template>
            <p class="agent-description text-body-2 text-medium-emphasis">{{ agent.description || tm('section.noDescription') }}</p>
            <div class="text-caption text-medium-emphasis mt-2">{{ summary(agent) }}</div>
            <div v-if="!runtimeAvailable(agent.runtime)" class="text-caption text-warning">{{ tm('status.unavailable') }}</div>
            <template #actions>
              <StyledMenu>
                <template #activator="{ props }"><v-btn v-bind="props" icon="mdi-dots-horizontal" variant="text" size="small" :aria-label="tm('actions.more')" @click.stop /></template>
                <v-list-item prepend-icon="mdi-pencil-outline" :title="tm('actions.edit')" @click="openEditor(agent)" />
                <v-list-item prepend-icon="mdi-delete-outline" :title="tm('actions.remove')" base-color="error" @click="pendingDelete = agent" />
              </StyledMenu>
            </template>
            <template #control><v-switch :model-value="agent.enabled" color="primary" hide-details inset density="compact" :loading="busyId === agent.config_id" :disabled="!!busyId || !runtimeAvailable(agent.runtime)" :aria-label="tm('cards.switchLabel')" @click.stop @update:model-value="setEnabled(agent, Boolean($event))" /></template>
          </OutlinedActionListItem>
        </div>
      </section>

      <v-dialog v-model="dialog" max-width="640" :persistent="saving">
        <v-card class="agent-editor">
          <v-card-title class="text-h3 pa-4 pb-0 pl-6">{{ editingId ? tm('actions.edit') : tm('actions.create') }}</v-card-title>
          <v-card-text class="pa-6">
            <v-form ref="form" class="agent-editor-fields" validate-on="submit" @submit.prevent="save">
              <v-text-field v-model="draft.name" :label="tm('form.nameLabel')" :rules="[value => Boolean(value?.trim()) || tm('messages.nameRequired')]" maxlength="128" variant="outlined" density="comfortable" hide-details="auto" />
              <v-textarea v-model="draft.description" :label="tm('form.descriptionLabel')" :hint="tm('form.descriptionHint')" variant="outlined" density="comfortable" hide-details="auto" rows="2" auto-grow />
              <v-select :model-value="draft.runtime" :items="runtimeOptions" :label="tm('form.runtime')" variant="outlined" density="comfortable" hide-details="auto" @update:model-value="changeRuntime" />
              <v-alert v-if="!runtimeAvailable(draft.runtime)" type="warning" variant="tonal" class="mb-4">{{ tm('status.unavailable') }}</v-alert>
              <NativeAgentConfigForm v-if="draft.runtime === 'astrbot'" v-model="draft.config" />
              <v-textarea v-else v-model="rawConfig" :label="tm('form.runtimeConfig')" :rules="[validateJson]" variant="outlined" rows="12" class="json-editor" />
              <v-alert v-if="saveError" type="error" variant="tonal" class="mt-4">{{ saveError }}</v-alert>
            </v-form>
          </v-card-text>
          <v-card-actions class="px-6 pb-4">
            <v-spacer /><v-btn variant="text" :disabled="saving" @click="dialog = false">{{ tm('actions.cancel') }}</v-btn>
            <v-btn variant="tonal" color="primary" :loading="saving" :disabled="!runtimeAvailable(draft.runtime)" @click="save">{{ tm('actions.save') }}</v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>
      <v-dialog :model-value="!!pendingDelete" max-width="480" :persistent="saving" @update:model-value="!$event && (pendingDelete = null)">
        <v-card>
          <v-card-title class="text-h3 pa-4 pb-0 pl-6">{{ tm('actions.remove') }}</v-card-title>
          <v-card-text class="pa-6">{{ tm('messages.deleteConfirm', { name: pendingDelete?.name || '' }) }}</v-card-text>
          <v-card-actions class="px-6 pb-4"><v-spacer /><v-btn variant="text" :disabled="saving" @click="pendingDelete = null">{{ tm('actions.cancel') }}</v-btn><v-btn variant="tonal" color="error" :loading="saving" @click="remove">{{ tm('actions.remove') }}</v-btn></v-card-actions>
        </v-card>
      </v-dialog>
      <v-snackbar v-model="snackbar.show" :color="snackbar.color" timeout="6000">{{ snackbar.text }}</v-snackbar>
    </v-container>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue';
import { agentConfigApi, type AgentConfig, type AgentConfigInput, type AgentRuntimeInfo } from '@/api/v1';
import OutlinedActionListItem from '@/components/shared/OutlinedActionListItem.vue';
import StyledMenu from '@/components/shared/StyledMenu.vue';
import NativeAgentConfigForm from '@/components/subagent/NativeAgentConfigForm.vue';
import { useModuleI18n } from '@/i18n/composables';
defineProps<{ embedded?: boolean }>();
const emit = defineEmits<{ changed: [] }>();
const { tm } = useModuleI18n('features/subagent');
const agents = ref<AgentConfig[]>([]);
const runtimes = ref<AgentRuntimeInfo[]>([]);
const loading = ref(false);
const saving = ref(false);
const busyId = ref('');
const loadError = ref('');
const saveError = ref('');
const dialog = ref(false);
const editingId = ref('');
const pendingDelete = ref<AgentConfig | null>(null);
const rawConfig = ref('{}');
const form = ref<{ validate: () => Promise<{ valid: boolean }>; resetValidation: () => void } | null>(null);
const snackbar = ref({ show: false, text: '', color: 'error' });
const draft = ref<AgentConfigInput>({ name: '', description: '', enabled: true, runtime: 'astrbot', config: {} });
const runtimeOptions = computed(() => [...new Set([...runtimes.value.map(item => item.runtime), draft.value.runtime])]);
const runtimeAvailable = (runtime: string) => runtimes.value.some(item => item.runtime === runtime);
const clone = <T,>(value: T): T => JSON.parse(JSON.stringify(value));
const summary = (agent: AgentConfig) => agent.runtime === 'astrbot'
  ? [agent.config.persona?.persona_id || tm('form.followPersona'), agent.config.model?.provider_id || tm('form.followProvider')].join(' · ')
  : tm('form.externalRuntime');
function errorText(error: any) {
  const payload = error.response?.data;
  const references = payload?.data?.references;
  return `${payload?.message || String(error)}${references?.length ? `: ${references.map((item: any) => item.name || item.id).join(', ')}` : ''}`;
}
async function load() {
  loading.value = true;
  loadError.value = '';
  try {
    const [configs, registered] = await Promise.all([agentConfigApi.list(), agentConfigApi.runtimes()]);
    agents.value = configs.data.data;
    runtimes.value = registered.data.data;
  } catch (error) { loadError.value = errorText(error); }
  finally { loading.value = false; }
}
async function openEditor(agent?: AgentConfig) {
  editingId.value = agent?.config_id || '';
  const runtime = agent?.runtime || runtimes.value[0]?.runtime || 'astrbot';
  draft.value = agent ? clone({ name: agent.name, description: agent.description, enabled: agent.enabled, runtime, config: agent.config })
    : { name: '', description: '', enabled: true, runtime, config: clone(runtimes.value.find(item => item.runtime === runtime)?.config || {}) };
  rawConfig.value = JSON.stringify(draft.value.config, null, 2);
  saveError.value = '';
  dialog.value = true;
  await nextTick();
  form.value?.resetValidation();
}
function changeRuntime(runtime: string) {
  if (runtime === draft.value.runtime) return;
  draft.value.runtime = runtime;
  draft.value.config = clone(runtimes.value.find(item => item.runtime === runtime)?.config || {});
  rawConfig.value = JSON.stringify(draft.value.config, null, 2);
}
function validateJson(value: string) {
  try { const parsed = JSON.parse(value); return parsed !== null && !Array.isArray(parsed) && typeof parsed === 'object' || tm('messages.jsonObject'); }
  catch { return tm('messages.jsonObject'); }
}
async function save() {
  if (!(await form.value?.validate())?.valid) return;
  saving.value = true;
  saveError.value = '';
  try {
    if (draft.value.runtime === 'astrbot') {
      draft.value.config = {
        persona: { persona_id: draft.value.config.persona?.persona_id || '' },
        model: { provider_id: draft.value.config.model?.provider_id || '' }
      };
    } else draft.value.config = JSON.parse(rawConfig.value);
    const response = editingId.value ? await agentConfigApi.update(editingId.value, draft.value) : await agentConfigApi.create(draft.value);
    const item = response.data.data;
    agents.value = editingId.value ? agents.value.map(agent => agent.config_id === item.config_id ? item : agent) : [...agents.value, item];
    dialog.value = false;
    emit('changed');
  } catch (error) { saveError.value = errorText(error); }
  finally { saving.value = false; }
}
async function setEnabled(agent: AgentConfig, enabled: boolean) {
  busyId.value = agent.config_id;
  try {
    const { config_id, ...body } = agent;
    const response = await agentConfigApi.update(config_id, { ...body, enabled });
    agents.value = agents.value.map(item => item.config_id === config_id ? response.data.data : item);
    emit('changed');
  } catch (error) { snackbar.value = { show: true, text: errorText(error), color: 'error' }; }
  finally { busyId.value = ''; }
}
async function remove() {
  if (!pendingDelete.value) return;
  saving.value = true;
  try {
    const id = pendingDelete.value.config_id;
    await agentConfigApi.delete(id);
    agents.value = agents.value.filter(item => item.config_id !== id);
    emit('changed');
  } catch (error) { snackbar.value = { show: true, text: errorText(error), color: 'error' }; }
  finally { saving.value = false; pendingDelete.value = null; }
}
onMounted(load);
</script>

<style scoped>
@import "@/styles/dashboard-shell.css";

.subagent-page--embedded { min-height: auto; background: transparent; }
.subagent-page--embedded .agent-header { justify-content: flex-end; margin-bottom: 16px; }
.agent-editor-fields { display: grid; gap: 20px; }
.agent-editor { font-size: .875rem; }
.agent-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 20px; margin-bottom: 24px; }
.agent-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.agent-description { margin: 0; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; overflow-wrap: anywhere; }
.empty-state { text-align: center; padding: 48px 20px; }
.json-editor :deep(textarea) { font-family: monospace; }
@media (max-width: 959px) { .agent-grid { grid-template-columns: 1fr; } }
@media (max-width: 599px) { .agent-header { flex-direction: column; } }
</style>
