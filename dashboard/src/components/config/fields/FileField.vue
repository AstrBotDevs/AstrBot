<script setup lang="ts">
import { ref, onMounted, watch, computed } from 'vue';
import { listFiles, uploadFile, deleteFile, type FileItem } from '@/api/configFileField';
import FilePickButton from '@/components/shared/FilePickButton.vue'

const props = defineProps<{
  pluginName: string,
  fieldKey: string,
  schema: any,
  modelValue: string | string[]
}>();

const emit = defineEmits<{ (e: 'update:modelValue', v: any): void }>();

const files = ref<FileItem[]>([]);
const loading = ref(false);
const uploading = ref(false);
const fileToUpload = ref<File | null>(null);

const acceptAttr = computed(() => {
  const a = props.schema?.accept;
  if (Array.isArray(a) && a.length) {
    return a.join(',');
  }
  return undefined;
});

const multiple = computed(() => Boolean(props.schema?.multiple));

async function refresh() {
  try {
    loading.value = true;
    files.value = await listFiles(props.pluginName, props.fieldKey);
  } catch (e) {
    console.error(e);
  } finally {
    loading.value = false;
  }
}

async function doUpload() {
  if (!fileToUpload.value) return;
  try {
    uploading.value = true;
    const info = await uploadFile(props.pluginName, props.fieldKey, fileToUpload.value);
    // backend already writes config value. Just update local value for immediate UI feedback.
    if (!multiple.value) {
      emit('update:modelValue', info.path);
    } else {
      const cur = Array.isArray(props.modelValue) ? [...props.modelValue] : [];
      cur.unshift(info.path);
      emit('update:modelValue', cur);
    }
    await refresh();
    fileToUpload.value = null;
  } catch (e) {
    console.error(e);
  } finally {
    uploading.value = false;
  }
}

watch(fileToUpload, async (f) => {
  if (f) {
    await doUpload();
  }
});

async function remove(f: FileItem) {
  try {
    await deleteFile(props.pluginName, props.fieldKey, f.rel_path);
    // Sync current config value
    if (!multiple.value) {
      if (props.modelValue === f.rel_path) emit('update:modelValue', '');
    } else if (Array.isArray(props.modelValue)) {
      emit('update:modelValue', props.modelValue.filter((p: string) => p !== f.rel_path));
    }
    await refresh();
  } catch (e) {
    console.error(e);
  }
}

function setCurrent(path: string) {
  if (!multiple.value) {
    emit('update:modelValue', path);
  } else {
    const cur = Array.isArray(props.modelValue) ? [...props.modelValue] : [];
    if (!cur.includes(path)) cur.unshift(path);
    emit('update:modelValue', cur);
  }
}

onMounted(() => {
  refresh();
});

watch(() => props.pluginName + props.fieldKey, () => refresh());

function humanSize(n: number) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n/1024).toFixed(1)} KB`;
  return `${(n/1024/1024).toFixed(2)} MB`;
}

function copy(text: string) {
  navigator.clipboard?.writeText(text).catch(()=>{});
}

function onPicked(val: any) {
  const list: File[] = Array.isArray(val) ? val : (val ? [val as File] : []);
  if (!list.length) return;
  (async () => {
    for (const f of list) {
      fileToUpload.value = f;
      await doUpload();
    }
  })();
}
</script>

<template>
  <div class="filefield">
    <div class="current">
      <small class="text-medium-emphasis">当前�?/small>
      <div v-if="!multiple">
        <code v-if="(modelValue as any)">{{ modelValue }}</code>
        <span v-else class="text-disabled">(�?</span>
        <div class="actions">
          <v-btn size="x-small" variant="tonal" @click="() => copy(String(modelValue||''))" :disabled="!modelValue">复制路径</v-btn>
          <v-btn size="x-small" variant="text" color="error" @click="() => emit('update:modelValue','')" :disabled="!modelValue">清空</v-btn>
        </div>
      </div>
      <div v-else>
        <div v-if="Array.isArray(modelValue) && (modelValue as any).length">
          <v-chip v-for="p in (modelValue as any)" :key="p" class="mr-1 mb-1" size="x-small" @click="copy(p)">{{ p }}</v-chip>
        </div>
        <div v-else class="text-disabled">(�?</div>
      </div>
    </div>

    <div class="upload">
      <FilePickButton :accept="acceptAttr" :multiple="multiple" :loading="uploading" button-text="选择文件" @picked="onPicked" />
    </div>

    <div class="list">
      <div class="d-flex align-center mb-2">
        <small class="text-medium-emphasis">文件�?/small>
        <v-spacer></v-spacer>
        <v-btn size="x-small" variant="text" @click="refresh" :loading="loading">刷新</v-btn>
      </div>
      <v-alert v-if="!files.length" type="info" variant="tonal" density="compact">暂无文件</v-alert>
      <v-table v-else density="compact">
        <thead>
          <tr>
            <th>文件�?/th>
            <th>大小</th>
            <th>更新时间</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="f in files" :key="f.rel_path">
            <td>
              <code class="path" @click="copy(f.rel_path)">{{ f.rel_path }}</code>
            </td>
            <td>{{ humanSize(f.size) }}</td>
            <td>{{ new Date(f.mtime*1000).toLocaleString() }}</td>
            <td>
              <v-btn size="x-small" variant="text" @click="setCurrent(f.rel_path)">设为当前</v-btn>
              <v-btn size="x-small" variant="text" color="error" @click="remove(f)">删除</v-btn>
            </td>
          </tr>
        </tbody>
      </v-table>
    </div>
  </div>
</template>

<style scoped>
.filefield { width: 100%; }
.current { margin-bottom: 8px; }
.current .actions { display: inline-flex; gap: 6px; margin-left: 8px; }
.upload { display: flex; align-items: center; margin: 8px 0; }
.list .path { cursor: pointer; }
</style>
