<template>
  <div class="d-flex align-center justify-space-between" style="gap: 8px;">
    <div style="flex: 1; min-width: 0; overflow: hidden;">
      <span v-if="!modelValue || (Array.isArray(modelValue) && modelValue.length === 0)" 
            style="color: rgb(var(--v-theme-primaryText));">
        {{ tm('knowledgeBaseSelector.notSelected') }}
      </span>
      <div v-else class="d-flex flex-wrap gap-1">
        <v-chip 
          v-for="name in modelValue" 
          :key="name" 
          size="small" 
          color="primary" 
          variant="tonal"
          closable
          @click:close="removeKnowledgeBase(name)"
          style="max-width: 100%;">
          <span class="text-truncate" style="max-width: 200px;">{{ name }}</span>
        </v-chip>
      </div>
    </div>
    <v-btn size="small" color="primary" variant="tonal" @click="openDialog" style="flex-shrink: 0;">
      {{ buttonText || tm('knowledgeBaseSelector.buttonText') }}
    </v-btn>
  </div>

  <!-- Knowledge Base Selection Dialog -->
  <v-dialog v-model="dialog" max-width="600px">
    <v-card>
      <v-card-title class="text-h3 py-4" style="font-weight: normal;">
        {{ tm('knowledgeBaseSelector.dialogTitle') }}
      </v-card-title>
      
      <v-card-text class="pa-0" style="max-height: 400px; overflow-y: auto;">
        <v-progress-linear v-if="loading" indeterminate color="primary"></v-progress-linear>
        
        <!-- 知识库列表 -->
        <v-list v-if="!loading" density="compact">
          <!-- 知识库选项 -->
          <v-list-item
            v-for="kb in knowledgeBaseList"
            :key="kb.kb_id"
            :value="kb.kb_name"
            @click="selectKnowledgeBase(kb.kb_name)"
            :active="isSelected(kb.kb_name)"
            rounded="md"
            class="ma-1">
            <template v-slot:prepend>
              <span class="emoji-icon">{{ kb.emoji || '📚' }}</span>
            </template>
            <v-list-item-title>{{ kb.kb_name }}</v-list-item-title>
            <v-list-item-subtitle>
              {{ kb.description || tm('knowledgeBaseSelector.noDescription') }}
              <span v-if="kb.doc_count !== undefined"> - {{ tm('knowledgeBaseSelector.documentCount', { count: kb.doc_count }) }}</span>
              <span v-if="kb.chunk_count !== undefined"> - {{ tm('knowledgeBaseSelector.chunkCount', { count: kb.chunk_count }) }}</span>
            </v-list-item-subtitle>
            
            <template v-slot:append>
              <v-icon v-if="isSelected(kb.kb_name)" color="primary">
                mdi-checkbox-marked
              </v-icon>
              <v-icon v-else color="grey-lighten-1">
                mdi-checkbox-blank-outline
              </v-icon>
            </template>
          </v-list-item>
          
          <!-- 当没有知识库时显示创建提示 -->
          <div v-if="knowledgeBaseList.length === 0" class="text-center py-8">
            <v-icon size="64" color="grey-lighten-1">mdi-database-off</v-icon>
            <p class="text-grey mt-4 mb-4">{{ tm('knowledgeBaseSelector.noKnowledgeBases') }}</p>
            <v-btn color="primary" variant="tonal" @click="goToKnowledgeBasePage">
              {{ tm('knowledgeBaseSelector.createKnowledgeBase') }}
            </v-btn>
          </div>
        </v-list>
      </v-card-text>
      
      <v-card-actions class="pa-4">
        <div v-if="selectedKnowledgeBases.length > 0" class="text-caption text-grey">
          {{ tm('knowledgeBaseSelector.selectedCount', { count: selectedKnowledgeBases.length }) }}
        </div>
        <v-spacer></v-spacer>
        <v-btn variant="text" @click="cancelSelection">{{ tm('knowledgeBaseSelector.cancelSelection') }}</v-btn>
        <v-btn 
          color="primary" 
          @click="confirmSelection">
          {{ tm('knowledgeBaseSelector.confirmSelection') }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup>
import { ref, watch } from 'vue'
import axios from 'axios'
import { useRouter } from 'vue-router'
import { useModuleI18n } from '@/i18n/composables'

const props = defineProps({
  modelValue: {
    type: Array,
    default: () => []
  },
  buttonText: {
    type: String,
    default: ''
  }
})

const emit = defineEmits(['update:modelValue'])
const router = useRouter()
const { tm } = useModuleI18n('core.shared')

const dialog = ref(false)
const knowledgeBaseList = ref([])
const loading = ref(false)
const selectedKnowledgeBases = ref([])

// 监听 modelValue 变化，同步到 selectedKnowledgeBases
watch(() => props.modelValue, (newValue) => {
  selectedKnowledgeBases.value = Array.isArray(newValue) ? [...newValue] : []
}, { immediate: true })

async function openDialog() {
  // 初始化选中状态
  selectedKnowledgeBases.value = Array.isArray(props.modelValue) 
    ? [...props.modelValue] 
    : []
  
  dialog.value = true
  await loadKnowledgeBases()
}

async function loadKnowledgeBases() {
  loading.value = true
  try {
    const response = await axios.get('/api/kb/list', {
      params: {
        page: 1,
        page_size: 100
      }
    })
    
    if (response.data.status === 'ok') {
      knowledgeBaseList.value = response.data.data.items || []
    } else {
      console.error('加载知识库列表失败:', response.data.message)
      knowledgeBaseList.value = []
    }
  } catch (error) {
    console.error('加载知识库列表失败:', error)
    knowledgeBaseList.value = []
  } finally {
    loading.value = false
  }
}

function isSelected(kbName) {
  return selectedKnowledgeBases.value.includes(kbName)
}

function selectKnowledgeBase(kbName) {
  // 多选模式：切换选中状态
  const index = selectedKnowledgeBases.value.indexOf(kbName)
  if (index > -1) {
    selectedKnowledgeBases.value.splice(index, 1)
  } else {
    selectedKnowledgeBases.value.push(kbName)
  }
}

function removeKnowledgeBase(kbName) {
  const index = selectedKnowledgeBases.value.indexOf(kbName)
  if (index > -1) {
    selectedKnowledgeBases.value.splice(index, 1)
  }
  
  // 立即更新父组件
  emit('update:modelValue', [...selectedKnowledgeBases.value])
}

function confirmSelection() {
  emit('update:modelValue', [...selectedKnowledgeBases.value])
  dialog.value = false
}

function cancelSelection() {
  // 恢复到原始值
  selectedKnowledgeBases.value = Array.isArray(props.modelValue) 
    ? [...props.modelValue] 
    : []
  dialog.value = false
}

function goToKnowledgeBasePage() {
  dialog.value = false
  router.push('/knowledge-base')
}
</script>

<style scoped>
.v-list-item {
  transition: all 0.2s ease;
}

.v-list-item:hover {
  background-color: rgba(var(--v-theme-primary), 0.04);
}

.v-list-item.v-list-item--active {
  background-color: rgba(var(--v-theme-primary), 0.08);
}

.emoji-icon {
  font-size: 20px;
  margin-right: 8px;
  min-width: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.gap-1 {
  gap: 4px;
}

.text-truncate {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  display: inline-block;
}
</style>
