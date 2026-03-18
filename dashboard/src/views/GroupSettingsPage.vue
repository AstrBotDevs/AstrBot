<template>
  <div class="group-settings-page">
    <v-container fluid class="pa-0">
      <v-card flat>
        <v-card-title class="d-flex align-center py-3 px-4">
          <span class="text-h4">{{ tm('title') }}</span>
          <v-btn icon="mdi-information-outline" size="small" variant="text"
            href="https://astrbot.app/use/group-settings.html" target="_blank"></v-btn>
          <v-chip size="small" class="ml-1">{{ totalItems }} {{ tm('settingsCount') }}</v-chip>
          <v-row class="me-4 ms-4" dense>
            <v-text-field v-model="searchQuery" prepend-inner-icon="mdi-magnify" :label="tm('search.placeholder')"
              hide-details clearable variant="solo-filled" flat class="me-4" density="compact"></v-text-field>
          </v-row>
          <v-btn v-if="selectedItems.length > 0" color="error" prepend-icon="mdi-delete" variant="tonal"
            @click="confirmBatchDelete" class="mr-2" size="small">
            {{ tm('buttons.batchDelete') }} ({{ selectedItems.length }})
          </v-btn>
          <v-btn color="success" prepend-icon="mdi-plus" variant="tonal" @click="openAddDialog" class="mr-2"
            size="small">
            {{ tm('buttons.add') }}
          </v-btn>
          <v-btn color="primary" prepend-icon="mdi-refresh" variant="tonal" @click="refreshData" :loading="loading"
            size="small">
            {{ tm('buttons.refresh') }}
          </v-btn>
        </v-card-title>

        <v-divider></v-divider>

        <v-card-text class="pa-0">
          <v-data-table-server :headers="headers" :items="filteredSettingsList" :loading="loading"
            :items-length="totalItems" v-model:items-per-page="itemsPerPage" v-model:page="currentPage"
            @update:options="onTableOptionsUpdate" class="elevation-0" style="font-size: 12px;" v-model="selectedItems"
            show-select item-value="umo" return-object>

            <!-- UMO 信息 -->
            <template v-slot:item.umo_info="{ item }">
              <div>
                <div class="d-flex align-center">
                  <v-chip size="x-small" :color="getPlatformColor(item.platform)" class="mr-2">
                    {{ item.platform || 'unknown' }}
                  </v-chip>
                  <span class="text-truncate" style="max-width: 300px;">{{ item.umo }}</span>
                  <v-tooltip location="top">
                    <template v-slot:activator="{ props }">
                      <v-icon v-bind="props" size="small" class="ml-1">mdi-information-outline</v-icon>
                    </template>
                    <div>
                      <p>UMO: {{ item.umo }}</p>
                      <p v-if="item.platform">{{ tm('table.platform') }}: {{ item.platform }}</p>
                      <p v-if="item.message_type">{{ tm('table.messageType') }}: {{ item.message_type }}</p>
                      <p v-if="item.group_id">{{ tm('table.groupId') }}: {{ item.group_id }}</p>
                    </div>
                  </v-tooltip>
                </div>
              </div>
            </template>

            <!-- Provider -->
            <template v-slot:item.provider_id="{ item }">
              <v-chip v-if="item.provider_id" size="small" color="primary" variant="outlined">
                {{ item.provider_id }}
              </v-chip>
              <span v-else class="text-medium-emphasis">-</span>
            </template>

            <!-- Persona -->
            <template v-slot:item.persona_id="{ item }">
              <v-chip v-if="item.persona_id" size="small" color="secondary" variant="outlined">
                {{ item.persona_id }}
              </v-chip>
              <span v-else class="text-medium-emphasis">-</span>
            </template>

            <!-- Model -->
            <template v-slot:item.model="{ item }">
              <span v-if="item.model" class="text-caption">{{ item.model }}</span>
              <span v-else class="text-medium-emphasis">-</span>
            </template>

            <!-- Set By -->
            <template v-slot:item.set_by="{ item }">
              <v-chip v-if="item.set_by" size="x-small" :color="item.set_by === 'webui' ? 'info' : 'default'"
                variant="tonal">
                {{ item.set_by }}
              </v-chip>
              <span v-else class="text-medium-emphasis">-</span>
            </template>

            <!-- Set At -->
            <template v-slot:item.set_at="{ item }">
              <span v-if="item.set_at" class="text-caption">{{ formatDate(item.set_at) }}</span>
              <span v-else class="text-medium-emphasis">-</span>
            </template>

            <!-- 操作按钮 -->
            <template v-slot:item.actions="{ item }">
              <v-btn size="small" variant="tonal" color="primary" @click="openEditDialog(item)" class="mr-1">
                <v-icon>mdi-pencil</v-icon>
                <v-tooltip activator="parent" location="top">{{ tm('buttons.edit') }}</v-tooltip>
              </v-btn>
              <v-btn size="small" variant="tonal" color="error" @click="confirmDelete(item)">
                <v-icon>mdi-delete</v-icon>
                <v-tooltip activator="parent" location="top">{{ tm('buttons.delete') }}</v-tooltip>
              </v-btn>
            </template>

            <!-- 空状态 -->
            <template v-slot:no-data>
              <div class="text-center py-8">
                <v-icon size="64" color="grey-400">mdi-account-group-outline</v-icon>
                <div class="text-h6 mt-4 text-grey-600">{{ tm('empty.title') }}</div>
                <div class="text-body-2 text-grey-500">{{ tm('empty.description') }}</div>
                <v-btn color="primary" variant="tonal" class="mt-4" @click="openAddDialog">
                  <v-icon start>mdi-plus</v-icon>
                  {{ tm('buttons.add') }}
                </v-btn>
              </div>
            </template>
          </v-data-table-server>
        </v-card-text>
      </v-card>
    </v-container>

    <!-- 添加/编辑对话框 -->
    <v-dialog v-model="dialogVisible" max-width="600px" persistent>
      <v-card>
        <v-card-title class="text-h5 pa-4">
          {{ isEditing ? tm('dialog.editTitle') : tm('dialog.addTitle') }}
        </v-card-title>
        <v-card-text class="pa-4">
          <v-form ref="formRef" v-model="formValid">
            <v-text-field v-model="formData.umo" :label="tm('dialog.umoLabel')" :rules="umoRules"
              :disabled="isEditing" variant="outlined" density="comfortable" class="mb-3"
              :hint="tm('dialog.umoHint')" persistent-hint></v-text-field>

            <v-select v-model="formData.provider_id" :items="availableProviders" item-title="id" item-value="id"
              :label="tm('dialog.providerLabel')" variant="outlined" density="comfortable" class="mb-3" clearable
              :hint="tm('dialog.providerHint')" persistent-hint>
              <template v-slot:item="{ props, item }">
                <v-list-item v-bind="props">
                  <v-list-item-subtitle class="text-caption">
                    {{ item.raw.model }}
                  </v-list-item-subtitle>
                </v-list-item>
              </template>
            </v-select>

            <v-select v-model="formData.persona_id" :items="availablePersonas" item-title="name" item-value="id"
              :label="tm('dialog.personaLabel')" variant="outlined" density="comfortable" class="mb-3" clearable
              :hint="tm('dialog.personaHint')" persistent-hint>
              <template v-slot:item="{ props, item }">
                <v-list-item v-bind="props">
                  <v-list-item-subtitle class="text-caption">
                    {{ item.raw.prompt }}
                  </v-list-item-subtitle>
                </v-list-item>
              </template>
            </v-select>
          </v-form>
        </v-card-text>
        <v-card-actions class="pa-4">
          <v-spacer></v-spacer>
          <v-btn variant="tonal" @click="dialogVisible = false">{{ tm('dialog.cancel') }}</v-btn>
          <v-btn color="primary" variant="tonal" @click="saveSetting" :loading="saving" :disabled="!formValid">
            {{ tm('dialog.save') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 删除确认对话框 -->
    <v-dialog v-model="deleteDialogVisible" max-width="400px">
      <v-card>
        <v-card-title class="text-h5 pa-4">{{ tm('deleteDialog.title') }}</v-card-title>
        <v-card-text class="pa-4">
          {{ tm('deleteDialog.message') }}
          <div class="mt-2 text-caption text-medium-emphasis">{{ deleteTarget?.umo }}</div>
        </v-card-text>
        <v-card-actions class="pa-4">
          <v-spacer></v-spacer>
          <v-btn variant="tonal" @click="deleteDialogVisible = false">{{ tm('deleteDialog.cancel') }}</v-btn>
          <v-btn color="error" variant="tonal" @click="deleteSetting" :loading="deleting">
            {{ tm('deleteDialog.confirm') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 批量删除确认对话框 -->
    <v-dialog v-model="batchDeleteDialogVisible" max-width="400px">
      <v-card>
        <v-card-title class="text-h5 pa-4">{{ tm('batchDeleteDialog.title') }}</v-card-title>
        <v-card-text class="pa-4">
          {{ tm('batchDeleteDialog.message', { count: selectedItems.length }) }}
        </v-card-text>
        <v-card-actions class="pa-4">
          <v-spacer></v-spacer>
          <v-btn variant="tonal" @click="batchDeleteDialogVisible = false">{{ tm('batchDeleteDialog.cancel') }}</v-btn>
          <v-btn color="error" variant="tonal" @click="batchDelete" :loading="batchDeleting">
            {{ tm('batchDeleteDialog.confirm') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue';
import axios from 'axios';
import { useModuleI18n } from '@/i18n/composables';
import { useToastStore } from '@/stores/toast';

const { tm } = useModuleI18n('features/groupSettings');
const toastStore = useToastStore();

// Table state
const loading = ref(false);
const settingsList = ref([]);
const totalItems = ref(0);
const currentPage = ref(1);
const itemsPerPage = ref(20);
const searchQuery = ref('');
const selectedItems = ref([]);

// Dialog state
const dialogVisible = ref(false);
const deleteDialogVisible = ref(false);
const batchDeleteDialogVisible = ref(false);
const isEditing = ref(false);
const saving = ref(false);
const deleting = ref(false);
const batchDeleting = ref(false);
const formValid = ref(false);
const formRef = ref(null);
const deleteTarget = ref(null);

// Form data
const formData = ref({
  umo: '',
  provider_id: '',
  persona_id: ''
});

// Available options
const availableProviders = ref([]);
const availablePersonas = ref([]);

// Platform colors
const platformColors = {
  'qq': 'primary',
  'wecom': 'success',
  'wechat': 'success',
  'dingtalk': 'info',
  'feishu': 'info',
  'telegram': 'primary',
  'discord': 'secondary',
  'gewechat': 'success',
  'unknown': 'grey'
};

// Table headers
const headers = computed(() => [
  { title: tm('table.umo'), key: 'umo_info', sortable: false },
  { title: tm('table.provider'), key: 'provider_id', sortable: false },
  { title: tm('table.persona'), key: 'persona_id', sortable: false },
  { title: tm('table.model'), key: 'model', sortable: false },
  { title: tm('table.setBy'), key: 'set_by', sortable: false },
  { title: tm('table.setAt'), key: 'set_at', sortable: false },
  { title: tm('table.actions'), key: 'actions', sortable: false, align: 'end' }
]);

// Validation rules
const umoRules = [
  v => !!v || tm('validation.umoRequired'),
  v => v.includes(':') || tm('validation.umoFormat')
];

// Filtered settings list
const filteredSettingsList = computed(() => {
  if (!searchQuery.value) return settingsList.value;
  const query = searchQuery.value.toLowerCase();
  return settingsList.value.filter(item =>
    item.umo.toLowerCase().includes(query) ||
    (item.provider_id && item.provider_id.toLowerCase().includes(query)) ||
    (item.persona_id && item.persona_id.toLowerCase().includes(query))
  );
});

// Methods
const showToast = (message, color = 'success') => {
  toastStore.add({
    message,
    color,
    timeout: 3000
  });
};

const formatDate = (value) => {
  if (!value) return '-';
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return value;
  return dt.toLocaleString();
};

const getPlatformColor = (platform) => {
  return platformColors[platform?.toLowerCase()] || 'grey';
};

const loadSettings = async () => {
  loading.value = true;
  try {
    const res = await axios.get('/api/group-settings/list', {
      params: {
        page: currentPage.value,
        page_size: itemsPerPage.value,
        search: searchQuery.value
      }
    });
    if (res.data.status === 'ok') {
      settingsList.value = res.data.data.settings;
      totalItems.value = res.data.data.total;
    } else {
      showToast(res.data.message || tm('messages.loadFailed'), 'error');
    }
  } catch (e) {
    showToast(e?.response?.data?.message || tm('messages.loadFailed'), 'error');
  } finally {
    loading.value = false;
  }
};

const loadAvailableOptions = async () => {
  try {
    const [providersRes, personasRes] = await Promise.all([
      axios.get('/api/group-settings/providers'),
      axios.get('/api/group-settings/personas')
    ]);

    if (providersRes.data.status === 'ok') {
      availableProviders.value = providersRes.data.data.providers;
    }

    if (personasRes.data.status === 'ok') {
      availablePersonas.value = personasRes.data.data.personas;
    }
  } catch (e) {
    console.error('Failed to load available options:', e);
  }
};

const onTableOptionsUpdate = (options) => {
  currentPage.value = options.page;
  itemsPerPage.value = options.itemsPerPage;
  loadSettings();
};

const refreshData = () => {
  currentPage.value = 1;
  loadSettings();
};

const openAddDialog = () => {
  isEditing.value = false;
  formData.value = {
    umo: '',
    provider_id: '',
    persona_id: ''
  };
  dialogVisible.value = true;
};

const openEditDialog = (item) => {
  isEditing.value = true;
  formData.value = {
    umo: item.umo,
    provider_id: item.provider_id || '',
    persona_id: item.persona_id || ''
  };
  dialogVisible.value = true;
};

const saveSetting = async () => {
  if (!formValid.value) return;

  saving.value = true;
  try {
    const promises = [];

    // Set provider if specified
    if (formData.value.provider_id) {
      promises.push(axios.post('/api/group-settings/set-provider', {
        umo: formData.value.umo,
        provider_id: formData.value.provider_id
      }));
    }

    // Set persona if specified
    if (formData.value.persona_id) {
      promises.push(axios.post('/api/group-settings/set-persona', {
        umo: formData.value.umo,
        persona_id: formData.value.persona_id
      }));
    }

    // If neither is specified, just clear (which effectively means no change for editing)
    if (promises.length === 0 && !isEditing.value) {
      showToast(tm('messages.nothingToSave'), 'warning');
      saving.value = false;
      return;
    }

    const results = await Promise.all(promises);
    const hasError = results.some(r => r.data.status !== 'ok');

    if (hasError) {
      const errorMsg = results.find(r => r.data.status !== 'ok')?.data?.message;
      showToast(errorMsg || tm('messages.saveFailed'), 'error');
    } else {
      showToast(isEditing.value ? tm('messages.updateSuccess') : tm('messages.addSuccess'), 'success');
      dialogVisible.value = false;
      loadSettings();
    }
  } catch (e) {
    showToast(e?.response?.data?.message || tm('messages.saveFailed'), 'error');
  } finally {
    saving.value = false;
  }
};

const confirmDelete = (item) => {
  deleteTarget.value = item;
  deleteDialogVisible.value = true;
};

const deleteSetting = async () => {
  if (!deleteTarget.value) return;

  deleting.value = true;
  try {
    const res = await axios.post('/api/group-settings/clear', {
      umo: deleteTarget.value.umo
    });

    if (res.data.status === 'ok') {
      showToast(tm('messages.deleteSuccess'), 'success');
      deleteDialogVisible.value = false;
      loadSettings();
    } else {
      showToast(res.data.message || tm('messages.deleteFailed'), 'error');
    }
  } catch (e) {
    showToast(e?.response?.data?.message || tm('messages.deleteFailed'), 'error');
  } finally {
    deleting.value = false;
  }
};

const confirmBatchDelete = () => {
  if (selectedItems.value.length === 0) return;
  batchDeleteDialogVisible.value = true;
};

const batchDelete = async () => {
  batchDeleting.value = true;
  try {
    const promises = selectedItems.value.map(item =>
      axios.post('/api/group-settings/clear', { umo: item.umo })
    );

    const results = await Promise.all(promises);
    const successCount = results.filter(r => r.data.status === 'ok').length;
    const failCount = results.length - successCount;

    if (failCount === 0) {
      showToast(tm('messages.batchDeleteSuccess', { count: successCount }), 'success');
    } else {
      showToast(tm('messages.batchDeletePartial', { success: successCount, fail: failCount }), 'warning');
    }

    batchDeleteDialogVisible.value = false;
    selectedItems.value = [];
    loadSettings();
  } catch (e) {
    showToast(tm('messages.batchDeleteFailed'), 'error');
  } finally {
    batchDeleting.value = false;
  }
};

// Watch for search query changes
watch(searchQuery, () => {
  currentPage.value = 1;
  loadSettings();
});

onMounted(() => {
  loadSettings();
  loadAvailableOptions();
});
</script>

<style scoped>
.group-settings-page {
  padding: 16px;
}
</style>
