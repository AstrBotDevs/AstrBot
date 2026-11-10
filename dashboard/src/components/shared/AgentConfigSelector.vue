<template>
  <div>
    <v-select
      :model-value="modelValue" :items="items" item-title="label" item-value="config_id"
      :label="tm('selection.label')" :loading="loading" multiple chips closable-chips
      variant="outlined" density="comfortable" hide-details="auto"
      @update:model-value="emit('update:modelValue', $event)"
    />
    <v-alert v-if="error" type="error" variant="tonal" class="mt-2">{{ error }}</v-alert>
    <v-btn class="mt-1" variant="text" size="small" prepend-icon="mdi-cog-outline" @click="managerOpen = true">{{ tm('selection.manage') }}</v-btn>
    <v-dialog v-model="managerOpen" max-width="1120" height="640" scrollable @after-leave="load">
      <v-card>
        <v-card-title class="text-h3 pa-4 pb-0 pl-6">{{ tm('selection.manage') }}</v-card-title>
        <v-card-text class="pa-0">
          <AgentConfigManager v-if="managerOpen" embedded @changed="load" />
        </v-card-text>
        <v-card-actions class="px-6 pb-4">
          <v-spacer />
          <v-btn variant="text" @click="managerOpen = false">{{ tm('actions.close') }}</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { agentConfigApi, type AgentConfig } from '@/api/v1';
import AgentConfigManager from '@/components/subagent/AgentConfigManager.vue';
import { useModuleI18n } from '@/i18n/composables';
const props = defineProps<{ modelValue: string[] }>();
const emit = defineEmits<{ 'update:modelValue': [value: string[]] }>();
const { tm } = useModuleI18n('features/subagent');
const managerOpen = ref(false);
const records = ref<AgentConfig[]>([]);
const availableRuntimes = ref<string[]>([]);
const loading = ref(false);
const error = ref('');
const items = computed(() => {
  const result = records.value.map(item => ({
    config_id: item.config_id,
    label: `${item.name} · ${item.runtime}${item.enabled ? '' : ` · ${tm('status.disabled')}`}${availableRuntimes.value.includes(item.runtime) ? '' : ` · ${tm('status.unavailable')}`}`,
    props: { disabled: !item.enabled || !availableRuntimes.value.includes(item.runtime) }
  }));
  for (const id of props.modelValue || []) {
    if (!result.some(item => item.config_id === id)) result.push({ config_id: id, label: `${tm('status.missing')} · ${id}`, props: { disabled: true } });
  }
  return result;
});
async function load() {
  if (loading.value) return;
  loading.value = true;
  error.value = '';
  try {
    const [configs, runtimes] = await Promise.all([agentConfigApi.list(), agentConfigApi.runtimes()]);
    records.value = configs.data.data;
    availableRuntimes.value = runtimes.data.data.map(item => item.runtime);
  } catch (err: any) { error.value = err.response?.data?.message || String(err); }
  finally { loading.value = false; }
}
onMounted(load);
</script>
