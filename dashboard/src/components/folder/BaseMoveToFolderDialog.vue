<template>
  <v-dialog v-model="showDialog" max-width="500px" persistent>
    <v-card>
      <v-card-title>
        <v-icon class="mr-2">mdi-folder-move</v-icon>
        {{ mergedLabels.title }}
      </v-card-title>
      <v-card-text>
        <p class="text-body-2 text-medium-emphasis mb-4">
          {{ mergedLabels.description }}
        </p>

        <!-- 文件夹选择树 -->
        <div class="folder-select-tree">
          <v-list density="compact" nav class="tree-list">
            <!-- 根目录选项 -->
            <v-list-item
              :active="selectedFolderId === null"
              rounded="md"
              class="mb-1"
              @click="selectFolder(null)"
            >
              <template #prepend>
                <v-icon>mdi-home</v-icon>
              </template>
              <v-list-item-title>{{
                mergedLabels.rootFolder
              }}</v-list-item-title>
            </v-list-item>

            <!-- 文件夹树 -->
            <template v-if="!treeLoading">
              <BaseMoveTargetNode
                v-for="folder in folderTree"
                :key="folder.folder_id"
                :folder="folder"
                :depth="0"
                :selected-folder-id="selectedFolderId"
                :disabled-folder-ids="disabledFolderIds"
                @select="selectFolder"
              />
            </template>

            <!-- 加载状态 -->
            <div v-if="treeLoading" class="text-center pa-4">
              <v-progress-circular indeterminate size="24" />
            </div>
          </v-list>
        </div>
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="closeDialog">
          {{ mergedLabels.cancelButton }}
        </v-btn>
        <v-btn
          color="primary"
          variant="flat"
          :loading="loading"
          @click="submitMove"
        >
          {{ mergedLabels.moveButton }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import type { FolderTreeNode } from './types';
import BaseMoveTargetNode from './BaseMoveTargetNode.vue';
import { collectFolderAndChildrenIds } from './useFolderManager';

interface DefaultLabels {
  title: string;
  description: string;
  rootFolder: string;
  cancelButton: string;
  moveButton: string;
}

const defaultLabels: DefaultLabels = {
  title: '移动到文件夹',
  description: '选择目标文件夹',
  rootFolder: '根目录',
  cancelButton: '取消',
  moveButton: '移动',
};

const props = withDefaults(
  defineProps<{
    modelValue?: boolean;
    folderTree: FolderTreeNode[];
    treeLoading?: boolean;
    currentFolderId?: string | null;
    itemCurrentFolderId?: string | null;
    isMovingFolder?: boolean;
    labels?: Partial<DefaultLabels>;
  }>(),
  {
    modelValue: false,
    treeLoading: false,
    currentFolderId: null,
    itemCurrentFolderId: null,
    isMovingFolder: false,
    labels: () => ({}),
  },
);

const emit = defineEmits<{
  'update:modelValue': [value: boolean];
  move: [folderId: string | null];
}>();

const selectedFolderId = ref<string | null>(null);
const loading = ref(false);

const showDialog = computed({
  get: () => props.modelValue,
  set: (value: boolean) => void emit('update:modelValue', value),
});

const mergedLabels = computed<DefaultLabels>(() => ({
  ...defaultLabels,
  ...props.labels,
}));

const disabledFolderIds = computed(() => {
  if (!props.isMovingFolder || !props.currentFolderId) {
    return [];
  }
  return collectFolderAndChildrenIds(props.folderTree, props.currentFolderId);
});

watch(
  () => props.modelValue,
  (newValue) => {
    if (newValue) {
      selectedFolderId.value = props.itemCurrentFolderId;
    }
  },
);

function selectFolder(folderId: string | null) {
  if (folderId && disabledFolderIds.value.includes(folderId)) {
    return;
  }
  selectedFolderId.value = folderId;
}

function closeDialog() {
  showDialog.value = false;
}

function submitMove() {
  emit('move', selectedFolderId.value);
}

function setLoading(value: boolean) {
  loading.value = value;
}

defineExpose({
  setLoading,
});
</script>

<style scoped>
.folder-select-tree {
  max-height: 400px;
  overflow-y: auto;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 8px;
}

.tree-list {
  padding: 8px;
}
</style>
