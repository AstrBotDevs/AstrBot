<template>
  <div>
    <v-list-item
      class="styled-menu-item"
      rounded="md"
      :disabled="loadingConfigs || saving"
      @click="openDialog"
    >
      <template #prepend>
        <v-icon icon="mdi-cog-outline" size="small"></v-icon>
      </template>
      <v-list-item-title>
        {{ tm('config.title') }}
      </v-list-item-title>
      <v-list-item-subtitle class="text-caption">
        {{ selectedConfigLabel }}
      </v-list-item-subtitle>
      <template #append>
        <v-icon
          icon="mdi-chevron-right"
          size="small"
          class="text-medium-emphasis"
        ></v-icon>
      </template>
    </v-list-item>

    <v-dialog v-model="dialog" max-width="480" scrollable>
      <v-card class="config-selector-dialog">
        <v-card-title class="d-flex align-center justify-space-between">
          <span>选择配置文件</span>
          <v-btn icon variant="text" @click="closeDialog">
            <v-icon>mdi-close</v-icon>
          </v-btn>
        </v-card-title>
        <v-card-text class="config-selector-dialog__content">
          <div v-if="loadingConfigs" class="text-center py-6">
            <v-progress-circular
              indeterminate
              color="primary"
            ></v-progress-circular>
          </div>

          <v-list v-else class="config-list" density="comfortable">
            <v-list-item
              v-for="config in configOptions"
              :key="config.id"
              :active="tempSelectedConfig === config.id"
              rounded="md"
              variant="text"
              @click="tempSelectedConfig = config.id"
            >
              <v-list-item-title>{{ config.name }}</v-list-item-title>
              <v-list-item-subtitle class="text-caption text-grey">
                {{ config.id }}
              </v-list-item-subtitle>
              <template #append>
                <v-icon v-if="tempSelectedConfig === config.id" color="primary"
                  >mdi-check</v-icon
                >
              </template>
            </v-list-item>
            <div
              v-if="configOptions.length === 0"
              class="text-center text-body-2 text-medium-emphasis"
            >
              暂无可选配置，请先在配置页创建。
            </div>
          </v-list>
        </v-card-text>
        <v-card-actions class="config-selector-dialog__actions">
          <v-spacer></v-spacer>
          <v-btn variant="text" @click="closeDialog">取消</v-btn>
          <v-btn
            color="primary"
            :disabled="!tempSelectedConfig"
            :loading="saving"
            @click="confirmSelection"
          >
            应用
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { configProfileApi, configRouteApi } from '@/api/v1';
import { useToast } from '@/utils/toast';
import { useModuleI18n } from '@/i18n/composables';
import {
  getStoredDashboardUsername,
  getStoredSelectedChatConfigId,
  setStoredSelectedChatConfigId,
} from '@/utils/chatConfigBinding';
import { resolveErrorMessage } from '@/utils/errorUtils';

interface ConfigInfo {
  id: string;
  name: string;
}

interface ConfigProfileInfo {
  id?: string;
  name?: string;
}

interface ConfigChangedPayload {
  configId: string;
  agentRunnerType: string;
}

interface DashboardConfigProfile {
  provider_settings?: {
    agent_runner_type?: string;
  };
}

const props = withDefaults(
  defineProps<{
    sessionId?: string | null;
    platformId?: string;
    isGroup?: boolean;
    initialConfigId?: string | null;
  }>(),
  {
    sessionId: null,
    platformId: 'webchat',
    isGroup: false,
    initialConfigId: null,
  },
);

const emit = defineEmits<{ 'config-changed': [ConfigChangedPayload] }>();

const { tm } = useModuleI18n('features/chat');

const configOptions = ref<ConfigInfo[]>([]);
const loadingConfigs = ref(false);
const dialog = ref(false);
const tempSelectedConfig = ref('');
const selectedConfigId = ref('default');
const agentRunnerType = ref('local');
const saving = ref(false);
const pendingSync = ref(false);
const routingEntries = ref<Array<{ pattern: string; confId: string }>>([]);
const configCache = ref<Record<string, string>>({});

const toast = useToast();

const normalizedSessionId = computed(() => {
  const id = props.sessionId?.trim();
  return id ? id : null;
});

const messageType = computed(() =>
  props.isGroup ? 'GroupMessage' : 'FriendMessage',
);

const username = computed(() => getStoredDashboardUsername());

const sessionKey = computed(() => {
  if (!normalizedSessionId.value) {
    return null;
  }
  return `${props.platformId}!${username.value}!${normalizedSessionId.value}`;
});

const targetUmo = computed(() => {
  if (!sessionKey.value) {
    return null;
  }
  return `${props.platformId}:${messageType.value}:${sessionKey.value}`;
});

const selectedConfigLabel = computed(() => {
  const target = configOptions.value.find(
    (item) => item.id === selectedConfigId.value,
  );
  return target?.name || selectedConfigId.value || 'default';
});

function openDialog() {
  tempSelectedConfig.value = selectedConfigId.value;
  dialog.value = true;
}

function closeDialog() {
  dialog.value = false;
}

async function fetchConfigList() {
  loadingConfigs.value = true;
  try {
    const res = await configProfileApi.list();
    const infoList = Array.isArray(res.data.data?.info_list)
      ? (res.data.data.info_list as ConfigProfileInfo[])
      : [];
    configOptions.value = infoList.map((item) => ({
      id: String(item.id || ''),
      name: String(item.name || item.id || 'default'),
    }));
  } catch (error) {
    console.error('加载配置文件列表失败', error);
    configOptions.value = [];
  } finally {
    loadingConfigs.value = false;
  }
}

async function fetchRoutingEntries() {
  try {
    const res = await configRouteApi.list();
    const routing = res.data.data?.routing || {};
    routingEntries.value = Object.entries(routing).map(([pattern, confId]) => ({
      pattern,
      confId,
    }));
  } catch (error) {
    console.error('获取配置路由失败', error);
    routingEntries.value = [];
  }
}

function matchesPattern(pattern: string, target: string): boolean {
  const parts = pattern.split(':');
  const targetParts = target.split(':');
  if (parts.length !== 3 || targetParts.length !== 3) {
    return false;
  }
  return parts.every(
    (part, index) => part === '' || part === '*' || part === targetParts[index],
  );
}

function resolveConfigId(umo: string | null): string {
  if (!umo) {
    return 'default';
  }
  for (const entry of routingEntries.value) {
    if (matchesPattern(entry.pattern, umo)) {
      return entry.confId;
    }
  }
  return 'default';
}

async function getAgentRunnerType(confId: string): Promise<string> {
  if (configCache.value[confId]) {
    return configCache.value[confId];
  }
  try {
    const res = await configProfileApi.get(confId);
    const payload = res.data.data as
      { config?: DashboardConfigProfile } | undefined;
    const config = payload?.config || {};
    const type = config?.provider_settings?.agent_runner_type || 'local';
    configCache.value[confId] = type;
    return type;
  } catch (error) {
    console.error('获取配置文件详情失败', error);
    return 'local';
  }
}

async function setSelection(confId: string) {
  const normalized = confId || 'default';
  selectedConfigId.value = normalized;
  const runnerType = await getAgentRunnerType(normalized);
  agentRunnerType.value = runnerType;
  emit('config-changed', {
    configId: normalized,
    agentRunnerType: runnerType,
  });
}

async function applySelectionToBackend(confId: string): Promise<boolean> {
  if (!targetUmo.value) {
    pendingSync.value = true;
    return true;
  }
  saving.value = true;
  try {
    await configRouteApi.upsert(targetUmo.value, { config_id: confId });
    const filtered = routingEntries.value.filter(
      (entry) => entry.pattern !== targetUmo.value,
    );
    if (confId !== 'default') {
      filtered.push({ pattern: targetUmo.value, confId });
    }
    routingEntries.value = filtered;
    return true;
  } catch (error) {
    console.error('更新配置文件失败', error);
    toast.error(resolveErrorMessage(error, '配置文件应用失败'));
    return false;
  } finally {
    saving.value = false;
  }
}

async function confirmSelection() {
  if (!tempSelectedConfig.value) {
    return;
  }
  const previousId = selectedConfigId.value;
  await setSelection(tempSelectedConfig.value);
  setStoredSelectedChatConfigId(tempSelectedConfig.value);
  const applied = await applySelectionToBackend(tempSelectedConfig.value);
  if (!applied) {
    setStoredSelectedChatConfigId(previousId);
    await setSelection(previousId);
  }
  dialog.value = false;
}

async function syncSelectionForSession() {
  if (!targetUmo.value) {
    pendingSync.value = true;
    return;
  }
  if (pendingSync.value) {
    pendingSync.value = false;
    await applySelectionToBackend(selectedConfigId.value);
    return;
  }
  await fetchRoutingEntries();
  const resolved = resolveConfigId(targetUmo.value);
  await setSelection(resolved);
  setStoredSelectedChatConfigId(resolved);
}

watch(
  () => [props.sessionId, props.platformId, props.isGroup],
  async () => {
    await syncSelectionForSession();
  },
);

onMounted(async () => {
  await fetchConfigList();
  const stored = props.initialConfigId || getStoredSelectedChatConfigId();
  selectedConfigId.value = stored;
  await setSelection(stored);
  await syncSelectionForSession();
});
</script>

<style scoped>
.config-selector-dialog {
  display: flex;
  flex-direction: column;
  max-height: min(80dvh, 720px);
  overflow: hidden;
}

.config-selector-dialog__content {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
}

.config-selector-dialog__actions {
  flex: 0 0 auto;
}

.config-list {
  max-height: min(48dvh, 420px);
  overflow-y: auto;
}
</style>
