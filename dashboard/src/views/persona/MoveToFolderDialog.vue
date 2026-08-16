<template>
  <v-dialog v-model="showDialog" max-width="500px" persistent>
    <v-card>
      <v-card-title>
        <v-icon class="mr-2">mdi-folder-move</v-icon>
        {{ tm('moveDialog.title') }}
      </v-card-title>
      <v-card-text>
        <p class="text-body-2 text-medium-emphasis mb-4">
          {{ tm('moveDialog.description', { name: itemName }) }}
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
                tm('folder.rootFolder')
              }}</v-list-item-title>
            </v-list-item>

            <!-- 文件夹树 -->
            <template v-if="!treeLoading">
              <BaseMoveTargetNode
                v-for="folder in availableFolders"
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
          {{ tm('buttons.cancel') }}
        </v-btn>
        <v-btn
          color="primary"
          variant="flat"
          :loading="loading"
          @click="submitMove"
        >
          {{ tm('buttons.move') }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useModuleI18n } from '@/i18n/composables';
import { usePersonaStore } from '@/stores/personaStore';
import { storeToRefs } from 'pinia';
import BaseMoveTargetNode from '@/components/folder/BaseMoveTargetNode.vue';
import { collectFolderAndChildrenIds } from '@/components/folder/useFolderManager';
import type { FolderTreeNode } from '@/components/folder/types';
import { resolveErrorMessage } from '@/utils/errorUtils';

interface PersonaItem {
  persona_id: string;
  folder_id?: string | null;
}

interface FolderItem {
  folder_id: string;
  name: string;
  parent_id?: string | null;
}

function isPersonaItem(item: PersonaItem | FolderItem): item is PersonaItem {
  return 'persona_id' in item;
}

function isFolderItem(item: PersonaItem | FolderItem): item is FolderItem {
  return 'name' in item;
}

const props = withDefaults(
  defineProps<{
    modelValue?: boolean;
    itemType: 'persona' | 'folder';
    item?: PersonaItem | FolderItem | null;
  }>(),
  {
    modelValue: false,
    item: null,
  },
);

const emit = defineEmits<{
  'update:modelValue': [value: boolean];
  moved: [message: string];
  error: [message: string];
}>();

const { tm } = useModuleI18n('features/persona');
const personaStore = usePersonaStore();
const { folderTree, treeLoading } = storeToRefs(personaStore);
const selectedFolderId = ref<string | null>(null);
const loading = ref(false);

const showDialog = computed({
  get: () => props.modelValue,
  set: (value: boolean) => void emit('update:modelValue', value),
});

const itemName = computed(() => {
  if (!props.item) {
    return '';
  }
  if (props.itemType === 'persona' && isPersonaItem(props.item)) {
    return props.item.persona_id;
  }
  return isFolderItem(props.item) ? props.item.name : '';
});

const disabledFolderIds = computed(() => {
  if (props.itemType !== 'folder' || !props.item || !isFolderItem(props.item)) {
    return [];
  }
  return collectFolderAndChildrenIds(folderTree.value, props.item.folder_id);
});

const availableFolders = computed<FolderTreeNode[]>(() => folderTree.value);

watch(
  () => props.modelValue,
  (newValue) => {
    if (newValue && props.item) {
      if (props.itemType === 'persona' && isPersonaItem(props.item)) {
        selectedFolderId.value = props.item.folder_id ?? null;
        return;
      }
      if (isFolderItem(props.item)) {
        selectedFolderId.value = props.item.parent_id ?? null;
        return;
      }
      selectedFolderId.value = null;
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

async function submitMove() {
  if (!props.item) {
    return;
  }

  loading.value = true;
  try {
    if (props.itemType === 'persona' && isPersonaItem(props.item)) {
      await personaStore.movePersonaToFolder(
        props.item.persona_id,
        selectedFolderId.value,
      );
    } else if (isFolderItem(props.item)) {
      await personaStore.moveFolderToFolder(
        props.item.folder_id,
        selectedFolderId.value,
      );
    } else {
      return;
    }
    emit('moved', tm('moveDialog.success'));
    closeDialog();
  } catch (error) {
    emit('error', resolveErrorMessage(error, tm('moveDialog.error')));
  } finally {
    loading.value = false;
  }
}
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
