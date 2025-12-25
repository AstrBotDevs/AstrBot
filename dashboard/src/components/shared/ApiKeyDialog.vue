<template>
  <div>
    <!-- API Key 管理对话框 -->
    <v-dialog v-model="dialog" :max-width="$vuetify.display.xs ? '100%' : '800'" :fullscreen="$vuetify.display.xs">
      <v-card>
        <v-card-title class="d-flex justify-space-between align-center">
          <span class="text-h3">API Keys 管理</span>
          <v-btn icon @click="closeDialog" variant="text">
            <v-icon>mdi-close</v-icon>
          </v-btn>
        </v-card-title>
        <v-card-text>
          <v-container>
            <v-row class="mb-4">
              <v-text-field v-model="newApiKeyName" label="API Key 名称（可选）" variant="outlined" density="compact"
                prepend-inner-icon="mdi-key-plus" class="mr-2" @keyup.enter="createApiKey"></v-text-field>
              <v-btn color="primary" @click="createApiKey()" variant="tonal" :loading="creatingApiKey"
                :disabled="creatingApiKey" style="display: inline-block; margin-left: 8px;">
                创建 API Key
              </v-btn>
            </v-row>

            <v-alert v-if="apiKeys.length === 0" type="info" variant="tonal">
              还没有创建任何 API Key。点击上方按钮创建一个。
            </v-alert>

            <v-list v-else>
              <v-list-item v-for="key in apiKeys" :key="key.key_id" class="mb-2">
                <template v-slot:prepend>
                  <v-icon>mdi-key</v-icon>
                </template>
                <v-list-item-title>
                  {{ key.name || '未命名 API Key' }}
                </v-list-item-title>
                <v-list-item-subtitle>
                  <div>创建时间: {{ formatDate(key.created_at) }}</div>
                  <div v-if="key.last_used_at">
                    最后使用: {{ formatDate(key.last_used_at) }}
                  </div>
                  <div v-else>从未使用</div>
                </v-list-item-subtitle>
                <template v-slot:append>
                  <v-btn icon variant="text" color="error" @click="deleteApiKey(key.key_id)" size="small">
                    <v-icon>mdi-delete</v-icon>
                  </v-btn>
                </template>
              </v-list-item>
            </v-list>
          </v-container>
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn color="blue-darken-1" variant="text" @click="closeDialog">
            {{ t('core.common.close') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 新建 API Key 显示对话框 -->
    <v-dialog v-model="newApiKeyDialog" max-width="600" persistent>
      <v-card>
        <v-card-title class="text-h5 text-warning">
          <v-icon color="warning" class="mr-2">mdi-alert</v-icon>
          重要：请保存您的 API Key
        </v-card-title>
        <v-card-text>
          <v-alert type="warning" variant="tonal" class="mb-4">
            API Key 只会显示一次，请立即复制并妥善保管。如果丢失，您需要删除并重新创建。
          </v-alert>
          <v-text-field :model-value="newApiKeyValue" label="您的 API Key" variant="outlined" readonly
            append-inner-icon="mdi-content-copy" @click:append-inner="copyApiKey(newApiKeyValue)"
            class="mb-4"></v-text-field>
          <div class="text-caption text-medium-emphasis">
            使用方式：在请求头中添加 <code>Authorization: Bearer {your_api_key}</code>
          </div>
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn color="primary" @click="closeNewApiKeyDialog">
            我已保存
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue';
import axios from 'axios';
import { useI18n } from '@/i18n/composables';

const { t } = useI18n();

interface ApiKey {
  key_id: string;
  name: string | null;
  username: string;
  created_at: string;
  expires_at: string | null;
  last_used_at: string | null;
}

const props = defineProps<{
  modelValue: boolean;
}>();

const emit = defineEmits<{
  'update:modelValue': [value: boolean];
}>();

const dialog = ref(false);
const apiKeys = ref<ApiKey[]>([]);
const newApiKeyName = ref('');
const newApiKeyDialog = ref(false);
const newApiKeyValue = ref('');
const creatingApiKey = ref(false);

// 同步外部 modelValue 和内部 dialog
watch(() => props.modelValue, (newVal) => {
  dialog.value = newVal;
  if (newVal) {
    loadApiKeys();
  }
});

watch(dialog, (newVal) => {
  emit('update:modelValue', newVal);
});

function closeDialog() {
  dialog.value = false;
  newApiKeyName.value = '';
}

function formatDate(dateString: string | null): string {
  if (!dateString) return '';
  return new Date(dateString).toLocaleString();
}

async function loadApiKeys() {
  try {
    const res = await axios.get('/api/api-key');
    if (res.data.status === 'ok') {
      apiKeys.value = res.data.data;
    }
  } catch (err) {
    console.error('Failed to load API keys:', err);
  }
}

async function createApiKey() {
  creatingApiKey.value = true;
  try {
    const res = await axios.post('/api/api-key', {
      name: newApiKeyName.value.trim() || undefined
    });
    if (res.data.status === 'ok') {
      newApiKeyValue.value = res.data.data.api_key;
      newApiKeyDialog.value = true;
      newApiKeyName.value = '';
      await loadApiKeys();
    }
  } catch (err) {
    console.error('Failed to create API key:', err);
  } finally {
    creatingApiKey.value = false;
  }
}

async function deleteApiKey(keyId: string) {
  if (!confirm('确定要删除这个 API Key 吗？删除后无法恢复。')) {
    return;
  }
  try {
    const res = await axios.delete(`/api/api-key/${keyId}`);
    if (res.data.status === 'ok') {
      await loadApiKeys();
    }
  } catch (err) {
    console.error('Failed to delete API key:', err);
  }
}

function copyApiKey(key: string) {
  navigator.clipboard.writeText(key);
  // TODO: 可以添加一个 toast 提示
}

function closeNewApiKeyDialog() {
  newApiKeyDialog.value = false;
  newApiKeyValue.value = '';
}
</script>

<style scoped>
code {
  background-color: rgba(var(--v-theme-on-surface), 0.1);
  padding: 2px 6px;
  border-radius: 4px;
  font-family: 'Courier New', monospace;
  font-size: 0.9em;
}
</style>
