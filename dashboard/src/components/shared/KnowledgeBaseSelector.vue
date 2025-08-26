<template>
  <div class="d-flex align-center justify-space-between">
    <span v-if="!modelValue" style="color: rgb(var(--v-theme-primaryText));">
      未选择
    </span>
    <span v-else>
      {{ modelValue }}
    </span>
    <v-btn size="small" color="primary" variant="tonal" @click="openDialog">
      {{ buttonText }}
    </v-btn>
  </div>

  <!-- Knowledge Base Selection Dialog -->
  <v-dialog v-model="dialog" max-width="600px">
    <v-card>
      <v-card-title class="text-h3 py-4" style="font-weight: normal;">
        选择知识库
      </v-card-title>
      
      <v-card-text class="pa-0" style="max-height: 400px; overflow-y: auto;">
        <v-progress-linear v-if="loading" indeterminate color="primary"></v-progress-linear>
        
        <!-- 插件未安装提示 -->
        <div v-if="!loading && !pluginInstalled" class="text-center py-8">
          <v-icon size="64" color="grey-lighten-1">mdi-puzzle-outline</v-icon>
          <p class="text-grey mt-4 mb-4">知识库插件未安装</p>
          <v-btn color="primary" variant="tonal" @click="goToKnowledgeBasePage">
            前往知识库页面
          </v-btn>
        </div>
        
        <!-- 知识库列表 -->
        <v-list v-else-if="!loading && pluginInstalled" density="compact">
          <!-- 不使用选项 -->
          <v-list-item
            :value="''"
            @click="selectKnowledgeBase({ collection_name: '' })"
            :active="selectedKnowledgeBase === ''"
            rounded="md"
            class="ma-1">
            <template v-slot:prepend>
              <v-icon color="grey-lighten-1">mdi-close-circle-outline</v-icon>
            </template>
            <v-list-item-title>不使用</v-list-item-title>
            <v-list-item-subtitle>不使用任何知识库</v-list-item-subtitle>
            
            <template v-slot:append>
              <v-icon v-if="selectedKnowledgeBase === ''" color="primary">mdi-check-circle</v-icon>
            </template>
          </v-list-item>
          
          <v-divider v-if="knowledgeBaseList.length > 0" class="my-2"></v-divider>
          
          <!-- 知识库选项 -->
          <v-list-item
            v-for="kb in knowledgeBaseList"
            :key="kb.collection_name"
            :value="kb.collection_name"
            @click="selectKnowledgeBase(kb)"
            :active="selectedKnowledgeBase === kb.collection_name"
            rounded="md"
            class="ma-1">
            <template v-slot:prepend>
              <span class="emoji-icon">{{ kb.emoji || '🙂' }}</span>
            </template>
            <v-list-item-title>{{ kb.collection_name }}</v-list-item-title>
            <v-list-item-subtitle>
              {{ kb.description || '无描述' }}
              <span v-if="kb.count !== undefined"> - {{ kb.count }} 项知识</span>
            </v-list-item-subtitle>
            
            <template v-slot:append>
              <v-icon v-if="selectedKnowledgeBase === kb.collection_name" color="primary">mdi-check-circle</v-icon>
            </template>
          </v-list-item>
          
          <!-- 当没有知识库时显示创建提示 -->
          <div v-if="knowledgeBaseList.length === 0" class="text-center py-4">
            <p class="text-grey mb-4">暂无知识库</p>
            <v-btn color="primary" variant="tonal" size="small" @click="goToKnowledgeBasePage">
              创建知识库
            </v-btn>
          </div>
        </v-list>
        
        <!-- 空状态（插件未安装时保留原有逻辑） -->
        <div v-else-if="!loading && !pluginInstalled && knowledgeBaseList.length === 0" class="text-center py-8">
          <v-icon size="64" color="grey-lighten-1">mdi-database-off</v-icon>
          <p class="text-grey mt-4 mb-4">暂无知识库</p>
          <v-btn color="primary" variant="tonal" @click="goToKnowledgeBasePage">
            创建知识库
          </v-btn>
        </div>
      </v-card-text>
      
      <v-card-actions class="pa-4">
        <v-spacer></v-spacer>
        <v-btn variant="text" @click="cancelSelection">取消</v-btn>
        <v-btn 
          color="primary" 
          @click="confirmSelection"
          :disabled="selectedKnowledgeBase === null || selectedKnowledgeBase === undefined">
          确认选择
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup>
import { ref, watch } from 'vue'
import axios from 'axios'
import { useRouter } from 'vue-router'

const props = defineProps({
  modelValue: {
    type: String,
    default: ''
  },
  buttonText: {
    type: String,
    default: '选择知识库...'
  }
})

const emit = defineEmits(['update:modelValue'])
const router = useRouter()

const dialog = ref(false)
const knowledgeBaseList = ref([])
const loading = ref(false)
const selectedKnowledgeBase = ref('')
const pluginInstalled = ref(false)

// 监听 modelValue 变化，同步到 selectedKnowledgeBase
watch(() => props.modelValue, (newValue) => {
  selectedKnowledgeBase.value = newValue || ''
}, { immediate: true })

async function openDialog() {
  selectedKnowledgeBase.value = props.modelValue || ''
  dialog.value = true
  await checkPluginAndLoadKnowledgeBases()
}

async function checkPluginAndLoadKnowledgeBases() {
  loading.value = true
  try {
    // 首先检查插件是否安装
    const pluginResponse = await axios.get('/api/plugin/get?name=astrbot_plugin_knowledge_base')
    
    if (pluginResponse.data.status === 'ok' && pluginResponse.data.data.length > 0) {
      pluginInstalled.value = true
      // 插件已安装，获取知识库列表
      await loadKnowledgeBases()
    } else {
      pluginInstalled.value = false
      knowledgeBaseList.value = []
    }
  } catch (error) {
    console.error('检查知识库插件失败:', error)
    pluginInstalled.value = false
    knowledgeBaseList.value = []
  } finally {
    loading.value = false
  }
}

async function loadKnowledgeBases() {
  try {
    const response = await axios.get('/api/plug/alkaid/kb/collections')
    if (response.data.status === 'ok') {
      knowledgeBaseList.value = response.data.data || []
    } else {
      knowledgeBaseList.value = []
    }
  } catch (error) {
    console.error('加载知识库列表失败:', error)
    knowledgeBaseList.value = []
  }
}

function selectKnowledgeBase(kb) {
  selectedKnowledgeBase.value = kb.collection_name
}

function confirmSelection() {
  emit('update:modelValue', selectedKnowledgeBase.value)
  dialog.value = false
}

function cancelSelection() {
  selectedKnowledgeBase.value = props.modelValue || ''
  dialog.value = false
}

function goToKnowledgeBasePage() {
  dialog.value = false
  router.push('/alkaid/knowledge-base')
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
</style>
