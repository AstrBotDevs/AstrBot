<template>
  <BaseFolderItemSelector
    :model-value="modelValue"
    @update:model-value="handleUpdate"
    :folder-tree="folderTree"
    :items="currentPersonas as any"
    :tree-loading="treeLoading"
    :items-loading="itemsLoading"
    :labels="labels"
    :show-create-button="true"
    :default-item="defaultPersona"
    item-id-field="persona_id"
    item-name-field="persona_id"
    item-description-field="system_prompt"
    :display-value-formatter="formatDisplayValue"
    @navigate="handleNavigate"
    @create="openCreatePersona"
  />

  <!-- 创建人格对话框 -->
  <PersonaForm
    v-model="showCreateDialog"
    :editing-persona="undefined"
    :current-folder-id="currentFolderId ?? undefined"
    :current-folder-name="currentFolderName ?? undefined"
    @saved="handlePersonaCreated"
    @error="handleError" />
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import axios from 'axios'
import BaseFolderItemSelector from '@/components/folder/BaseFolderItemSelector.vue'
import PersonaForm from './PersonaForm.vue'
import { useI18n, useModuleI18n } from '@/i18n/composables'
import type { FolderTreeNode, SelectableItem } from '@/components/folder/types'

interface Persona {
  persona_id: string
  system_prompt: string
  folder_id?: string | null
  [key: string]: any
}

const props = defineProps({
  modelValue: {
    type: String,
    default: ''
  },
  buttonText: {
    type: String,
    default: ''
  }
})

const emit = defineEmits(['update:modelValue'])
const { t } = useI18n()
const { tm } = useModuleI18n('core.shared')

// 状态
const folderTree = ref<FolderTreeNode[]>([])
const currentPersonas = ref<Persona[]>([])
const treeLoading = ref(false)
const itemsLoading = ref(false)
const showCreateDialog = ref(false)
const currentFolderId = ref<string | null>(null)

// 默认人格
const defaultPersona: SelectableItem = {
  id: 'default',
  persona_id: 'default',
  name: tm('personaSelector.defaultPersona'),
  system_prompt: 'You are a helpful and friendly assistant.'
}

// 递归查找文件夹名称
function findFolderName(nodes: FolderTreeNode[], folderId: string): string | null {
  for (const node of nodes) {
    if (node.folder_id === folderId) {
      return node.name
    }
    if (node.children && node.children.length > 0) {
      const found = findFolderName(node.children, folderId)
      if (found) return found
    }
  }
  return null
}

// 当前文件夹名称
const currentFolderName = computed(() => {
  if (!currentFolderId.value) {
    return null // 根目录，PersonaForm 会使用 tm('form.rootFolder')
  }
  return findFolderName(folderTree.value, currentFolderId.value)
})

// 标签配置
const labels = computed(() => ({
  dialogTitle: tm('personaSelector.dialogTitle'),
  notSelected: tm('personaSelector.notSelected'),
  buttonText: props.buttonText || tm('personaSelector.buttonText'),
  noItems: tm('personaSelector.noPersonas'),
  defaultItem: tm('personaSelector.defaultPersona'),
  noDescription: tm('personaSelector.noDescription'),
  createButton: tm('personaSelector.createPersona'),
  confirmButton: t('core.common.confirm'),
  cancelButton: t('core.common.cancel'),
  rootFolder: tm('personaSelector.rootFolder') || '全部人格',
  emptyFolder: tm('personaSelector.emptyFolder') || '此文件夹为空'
}))

// 格式化显示值
function formatDisplayValue(value: string): string {
  if (value === 'default') {
    return tm('personaSelector.defaultPersona')
  }
  return value
}

// 处理值更新
function handleUpdate(value: string) {
  emit('update:modelValue', value)
}

// 加载文件夹树
async function loadFolderTree() {
  treeLoading.value = true
  try {
    const response = await axios.get('/api/persona/folder/tree')
    if (response.data.status === 'ok') {
      folderTree.value = response.data.data || []
    }
  } catch (error) {
    console.error('加载文件夹树失败:', error)
    folderTree.value = []
  } finally {
    treeLoading.value = false
  }
}

// 加载指定文件夹的人格
async function loadPersonasInFolder(folderId: string | null) {
  itemsLoading.value = true
  try {
    // 使用 /api/persona/list 端点，通过 folder_id 参数筛选
    const params = new URLSearchParams()
    if (folderId !== null) {
      params.set('folder_id', folderId)
    } else {
      // 根目录：folder_id 为空字符串表示获取根目录下的人格
      params.set('folder_id', '')
    }
    const response = await axios.get(`/api/persona/list?${params.toString()}`)
    if (response.data.status === 'ok') {
      currentPersonas.value = response.data.data || []
    }
  } catch (error) {
    console.error('加载人格列表失败:', error)
    currentPersonas.value = []
  } finally {
    itemsLoading.value = false
  }
}

// 处理文件夹导航
async function handleNavigate(folderId: string | null) {
  currentFolderId.value = folderId
  await loadPersonasInFolder(folderId)
}

// 打开创建人格对话框
function openCreatePersona() {
  showCreateDialog.value = true
}

// 人格创建成功
async function handlePersonaCreated(message: string) {
  console.log('人格创建成功:', message)
  showCreateDialog.value = false
  // 刷新当前文件夹的人格列表
  await loadPersonasInFolder(currentFolderId.value)
}

// 错误处理
function handleError(error: string) {
  console.error('创建人格失败:', error)
}

// 初始化加载文件夹树
onMounted(() => {
  loadFolderTree()
})
</script>

<style scoped>
/* 样式继承自 BaseFolderItemSelector */
</style>
