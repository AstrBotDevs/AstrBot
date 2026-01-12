<script setup>
import { ref, watch, computed } from 'vue';
import { useI18n } from '@/i18n/composables';
import axios from 'axios';
import { MarkdownRender, enableKatex, enableMermaid } from 'markstream-vue';
import 'markstream-vue/index.css';
import 'katex/dist/katex.min.css';
import 'highlight.js/styles/github.css';

enableKatex();
enableMermaid();

const { t } = useI18n();

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false
  }
});

const emit = defineEmits(['update:modelValue']);

const dialog = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value)
});

const changelogContent = ref('');
const changelogLoading = ref(false);
const changelogError = ref('');
const changelogVersion = ref('');
const selectedVersion = ref('');
const availableVersions = ref([]);
const loadingVersions = ref(false);

// 获取当前版本号（从版本信息中提取）
async function getCurrentVersion() {
  try {
    const res = await axios.get('/api/stat/version');
    const version = res.data.data?.version || '';
    changelogVersion.value = version;
    selectedVersion.value = version;
    return version;
  } catch (err) {
    console.error('Failed to get version:', err);
    return '';
  }
}

// 加载更新日志
async function loadChangelog(version) {
  const targetVersion = version || selectedVersion.value || changelogVersion.value;
  if (!targetVersion) {
    changelogError.value = t('core.navigation.changelogDialog.selectVersion');
    return;
  }

  changelogLoading.value = true;
  changelogError.value = '';
  changelogContent.value = '';

  try {
    const res = await axios.get('/api/stat/changelog', {
      params: { version: targetVersion }
    });
    
    if (res.data.status === 'ok') {
      changelogContent.value = res.data.data.content;
      selectedVersion.value = targetVersion;
    } else {
      changelogError.value = res.data.message || t('core.navigation.changelogDialog.error');
    }
  } catch (err) {
    console.error('Failed to load changelog:', err);
    if (err.response?.status === 404 || err.response?.data?.message?.includes('not found')) {
      changelogError.value = t('core.navigation.changelogDialog.notFound');
    } else {
      changelogError.value = t('core.navigation.changelogDialog.error');
    }
  } finally {
    changelogLoading.value = false;
  }
}

// 获取所有可用版本列表
async function loadAvailableVersions() {
  loadingVersions.value = true;
  try {
    const res = await axios.get('/api/stat/changelog/list');
    if (res.data.status === 'ok') {
      availableVersions.value = res.data.data.versions || [];
    }
  } catch (err) {
    console.error('Failed to load versions:', err);
  } finally {
    loadingVersions.value = false;
  }
}

// 版本选择变化时加载对应的更新日志
function onVersionChange() {
  if (selectedVersion.value) {
    loadChangelog(selectedVersion.value);
  }
}

// 监听对话框打开，初始化数据
watch(dialog, async (newValue) => {
  if (newValue) {
    // 加载版本列表
    await loadAvailableVersions();
    
    // 获取当前版本
    if (!changelogVersion.value) {
      await getCurrentVersion();
    }
    
    // 如果当前版本在列表中，默认选择当前版本
    if (changelogVersion.value && availableVersions.value.includes(changelogVersion.value)) {
      selectedVersion.value = changelogVersion.value;
      await loadChangelog();
    } else if (availableVersions.value.length > 0) {
      // 否则选择第一个（最新的）
      selectedVersion.value = availableVersions.value[0];
      await loadChangelog(availableVersions.value[0]);
    }
  } else {
    // 关闭时重置状态
    changelogContent.value = '';
    changelogError.value = '';
  }
});

// 初始化时获取版本号
getCurrentVersion();
</script>

<template>
  <v-dialog 
    :model-value="dialog" 
    @update:model-value="dialog = $event"
    :width="$vuetify.display.smAndDown ? '100%' : '800'"
    :fullscreen="$vuetify.display.xs" 
    max-width="1000"
  >
    <v-card>
      <v-card-title class="d-flex justify-space-between align-center">
        <span class="text-h3">{{ t('core.navigation.changelogDialog.title') }}</span>
        <v-btn icon @click="dialog = false" flat>
          <v-icon>mdi-close</v-icon>
        </v-btn>
      </v-card-title>
      <v-card-text>
        <!-- 版本选择器 -->
        <div class="mb-4">
          <v-select
            v-model="selectedVersion"
            :items="availableVersions"
            :label="t('core.navigation.changelogDialog.selectVersion')"
            :loading="loadingVersions"
            variant="outlined"
            density="compact"
            @update:model-value="onVersionChange"
          >
            <template v-slot:item="{ item, props }">
              <v-list-item v-bind="props" :title="`v${item.value}`">
                <template v-slot:append v-if="item.value === changelogVersion">
                  <v-chip size="x-small" color="primary" variant="tonal">
                    {{ t('core.navigation.changelogDialog.current') }}
                  </v-chip>
                </template>
              </v-list-item>
            </template>
            <template v-slot:selection="{ item }">
              <span>v{{ item.value }}</span>
            </template>
          </v-select>
        </div>
        
        <!-- 更新日志内容 -->
        <div style="max-height: 70vh; overflow-y: auto;">
          <div v-if="changelogLoading" class="text-center py-8">
            <v-progress-circular indeterminate color="primary"></v-progress-circular>
            <div class="mt-4">{{ t('core.navigation.changelogDialog.loading') }}</div>
          </div>
          <v-alert v-else-if="changelogError" type="error" variant="tonal" border="start">
            {{ changelogError }}
          </v-alert>
          <div v-else-if="changelogContent" class="changelog-content">
            <MarkdownRender :content="changelogContent" :typewriter="false" class="markdown-content" />
          </div>
        </div>
      </v-card-text>
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn color="blue-darken-1" variant="text" @click="dialog = false">
          {{ t('core.common.close') }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<style>
.changelog-content {
  padding: 8px 0;
}
</style>
