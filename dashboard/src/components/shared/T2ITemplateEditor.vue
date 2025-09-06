<template>
  <v-dialog v-model="dialog" max-width="1400px" persistent scrollable>
    <template v-slot:activator="{ props }">
      <v-btn 
        v-bind="props"
        variant="outlined" 
        color="primary" 
        size="small"
        :loading="loading"
      >
        自定义 T2I 模板
      </v-btn>
    </template>
    
    <v-card>
      <v-card-title class="d-flex align-center justify-space-between">
        <span>自定义文转图 HTML 模板</span>
        <v-spacer></v-spacer>
        <div class="d-flex align-center gap-2" style="width: 60%">
          <v-text-field
            v-if="isCreatingNew"
            v-model="editingName"
            label="输入新模板名称"
            density="compact"
            hide-details
            variant="outlined"
            class="flex-grow-1"
            autofocus
            :rules="[v => !!v || '名称不能为空']"
          ></v-text-field>
          <v-select
            v-else
            v-model="selectedTemplate"
            :items="templates"
            item-title="name"
            item-value="name"
            label="选择模板"
            density="compact"
            hide-details
            variant="outlined"
            class="flex-grow-1"
            :loading="loading"
          >
            <template v-slot:item="{ props, item }">
              <v-list-item v-bind="props" :title="item.raw.name">
                <template v-slot:append>
                  <v-chip
                    v-if="item.raw.name === activeTemplate"
                    color="success"
                    variant="tonal"
                    size="small"
                    class="ml-2"
                  >
                    已应用
                  </v-chip>
                  <v-btn
                    v-else
                    variant="text"
                    color="primary"
                    size="small"
                    class="ml-2"
                    @click.stop="setActiveTemplate(item.raw.name)"
                    :loading="applyLoading"
                  >
                    应用
                  </v-btn>
                </template>
              </v-list-item>
            </template>
          </v-select>
          <v-btn
            variant="text"
            icon
            @click="closeDialog"
          >
            <v-icon>mdi-close</v-icon>
          </v-btn>
        </div>
      </v-card-title>

      <v-card-text class="pa-0">
        <v-row no-gutters style="height: 70vh;">
          <!-- 左侧编辑器 -->
          <v-col cols="6" class="d-flex flex-column">
            <v-toolbar density="compact" color="surface-variant">
              <v-toolbar-title class="text-subtitle-2">模板编辑器</v-toolbar-title>
              <v-spacer></v-spacer>
              <div class="d-flex align-center pa-1" style="border: 1px solid rgba(0,0,0,0.1); border-radius: 8px;">
                <v-btn
                  variant="text"
                  size="small"
                  @click="newTemplate"
                  color="success"
                >
                  <v-icon left>mdi-plus</v-icon>
                  新建
                </v-btn>
                <v-divider vertical class="mx-1"></v-divider>
                <v-btn
                  variant="text"
                  size="small"
                  @click="resetToDefault"
                  :loading="resetLoading"
                  color="warning"
                >
                  重置Base
                </v-btn>
                <v-btn
                  variant="text"
                  size="small"
                  @click="promptDelete"
                  color="error"
                  :disabled="isCreatingNew || selectedTemplate === 'base' || !selectedTemplate"
                >
                  删除
                </v-btn>
                <v-divider vertical class="mx-1"></v-divider>
                <v-btn
                  variant="text"
                  size="small"
                  @click="saveTemplate"
                  :loading="saveLoading"
                  color="primary"
                  :disabled="(isCreatingNew && !editingName) || (!isCreatingNew && !selectedTemplate)"
                >
                  保存
                </v-btn>
              </div>
            </v-toolbar>
            <div class="flex-grow-1" style="border-right: 1px solid rgba(0,0,0,0.1);">
              <VueMonacoEditor
                v-model:value="templateContent"
                :theme="editorTheme"
                language="html"
                :options="editorOptions"
                style="height: 100%;"
              />
            </div>
          </v-col>

          <!-- 右侧预览 -->
          <v-col cols="6" class="d-flex flex-column">
            <v-toolbar density="compact" color="surface-variant">
              <v-toolbar-title class="text-subtitle-2">实时预览(可能有差异)</v-toolbar-title>
              <v-spacer></v-spacer>
              <v-btn 
                variant="text" 
                size="small" 
                @click="refreshPreview"
                :loading="previewLoading"
              >
                刷新预览
              </v-btn>
            </v-toolbar>
            <div class="flex-grow-1 preview-container">
              <iframe
                ref="previewFrame"
                :srcdoc="previewContent"
                style="width: 100%; height: 100%; border: none; zoom: 0.6;"
              />
            </div>
          </v-col>
        </v-row>
      </v-card-text>

      <v-card-actions class="px-6 py-4">
        <v-row no-gutters class="align-center">
          <v-col>
            <div class="text-caption text-grey">
              <v-icon size="16" class="mr-1">mdi-information</v-icon>
              支持 jinja2 语法。可用变量：<code> text | safe </code>（要渲染的文本）, <code> version </code>（AstrBot 版本）
            </div>
          </v-col>
          <v-col cols="auto">
            <v-btn
              variant="text"
              @click="closeDialog"
            >
              取消
            </v-btn>
            <v-btn
              color="primary"
              @click="promptApplyAndClose"
              :loading="saveLoading"
              :disabled="isCreatingNew || !selectedTemplate"
            >
              保存应用当前编辑模板
            </v-btn>
          </v-col>
        </v-row>
      </v-card-actions>
    </v-card>

    <!-- 确认重置对话框 -->
    <v-dialog v-model="resetDialog" max-width="400px">
      <v-card>
        <v-card-title>确认重置</v-card-title>
        <v-card-text>
          确定要将 'base' 模板恢复为默认内容吗？当前编辑器中的任何未保存更改将丢失。此操作无法撤销。
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn text @click="resetDialog = false">取消</v-btn>
          <v-btn color="warning" @click="confirmReset" :loading="resetLoading">确认重置</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 删除确认对话框 -->
    <v-dialog v-model="deleteDialog" max-width="400px">
      <v-card>
        <v-card-title>确认删除</v-card-title>
        <v-card-text>
          确定要删除模板 '{{ selectedTemplate }}' 吗？此操作无法撤销。
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn text @click="deleteDialog = false">取消</v-btn>
          <v-btn color="error" @click="confirmDelete" :loading="saveLoading">确认删除</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 保存并应用确认对话框 -->
    <v-dialog v-model="applyAndCloseDialog" max-width="500px">
      <v-card>
        <v-card-title>确认操作</v-card-title>
        <v-card-text>
          确定要保存对 '{{ selectedTemplate }}' 的修改，并将其设为新的活动模板吗？
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn text @click="applyAndCloseDialog = false">取消</v-btn>
          <v-btn color="primary" @click="confirmApplyAndClose" :loading="saveLoading">确认</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

  </v-dialog>
</template>

<script setup>
import { ref, computed, nextTick, watch } from 'vue'
import { VueMonacoEditor } from '@guolao/vue-monaco-editor'
import { useI18n } from '@/i18n/composables'
import axios from 'axios'

const { t } = useI18n()

// --- 响应式数据 ---
const dialog = ref(false)
const loading = ref(false) // 用于加载模板列表
const saveLoading = ref(false)
const resetLoading = ref(false)
const previewLoading = ref(false)
const applyLoading = ref(false)

// 模板管理
const templates = ref([])
const activeTemplate = ref('base')
const selectedTemplate = ref(null)
const editingName = ref('') // 用于新建模式下的名称输入
const templateContent = ref('')
const isCreatingNew = ref(false)

// 对话框状态
const resetDialog = ref(false)
const deleteDialog = ref(false)
const applyAndCloseDialog = ref(false)

const previewFrame = ref(null)

// --- 编辑器配置 ---
const editorTheme = computed(() => 'vs-light')
const editorOptions = {
  automaticLayout: true,
  fontSize: 12,
  lineNumbers: 'on',
  wordWrap: 'on',
  minimap: { enabled: false },
  scrollBeyondLastLine: false,
}

// --- 预览逻辑 ---
const previewData = {
  text: '这是一个示例文本，用于预览模板效果。\n\n这里可以包含多行文本，支持换行和各种格式。',
  version: 'v4.0.0'
}
const previewContent = computed(() => {
  try {
    let content = templateContent.value
    content = content.replace(/\{\{\s*text\s*\|\s*safe\s*\}\}/g, previewData.text)
    content = content.replace(/\{\{\s*version\s*\}\}/g, previewData.version)
    return content
  } catch (error) {
    return `<div style="color: red; padding: 20px;">模板渲染错误: ${error.message}</div>`
  }
})

// --- API 调用方法 ---

const loadInitialData = async () => {
  loading.value = true
  try {
    const [listRes, activeRes] = await Promise.all([
      axios.get('/api/t2i/templates'),
      axios.get('/api/t2i/templates/active')
    ])

    if (listRes.data.status === 'ok') {
      templates.value = listRes.data.data
    } else {
      console.error('加载模板列表失败:', listRes.data.message)
    }

    if (activeRes.data.status === 'ok') {
      activeTemplate.value = activeRes.data.data.active_template
    } else {
      console.error('加载活动模板失败:', activeRes.data.message)
    }

    // 设置初始选中的模板
    if (templates.value.length > 0) {
      selectedTemplate.value = activeTemplate.value
    }

  } catch (error) {
    console.error('加载初始数据失败:', error)
  } finally {
    loading.value = false
  }
}

const loadTemplateContent = async (name) => {
  if (!name) return
  previewLoading.value = true
  try {
    const response = await axios.get(`/api/t2i/templates/${name}`)
    if (response.data.status === 'ok') {
      templateContent.value = response.data.data.content
    } else {
      console.error(`加载模板 '${name}' 失败:`, response.data.message)
    }
  } catch (error) {
    console.error(`加载模板 '${name}' 失败:`, error)
  } finally {
    previewLoading.value = false
  }
}

const saveTemplate = async () => {
  saveLoading.value = true
  try {
    if (isCreatingNew.value) {
      // --- 创建新模板 ---
      if (!editingName.value) return
      const response = await axios.post('/api/t2i/templates/create', {
        name: editingName.value,
        content: templateContent.value
      })
      await loadInitialData() // 重新加载所有数据
      selectedTemplate.value = response.data.data.name
      isCreatingNew.value = false
    } else {
      // --- 更新现有模板 ---
      if (!selectedTemplate.value) return
      await axios.put(`/api/t2i/templates/${selectedTemplate.value}`, {
        content: templateContent.value
      })
    }
  } catch (error) {
    console.error('保存模板失败:', error)
    // 可以在此添加错误提示
  } finally {
    saveLoading.value = false
  }
}

const setActiveTemplate = async (name) => {
  applyLoading.value = true
  try {
    await axios.post('/api/t2i/templates/set_active', { name })
    activeTemplate.value = name
  } catch (error) {
    console.error(`应用模板 '${name}' 失败:`, error)
  } finally {
    applyLoading.value = false
  }
}

const confirmDelete = async () => {
  if (!selectedTemplate.value || selectedTemplate.value === 'base') return
  saveLoading.value = true
  try {
    const nameToDelete = selectedTemplate.value
    await axios.delete(`/api/t2i/templates/${nameToDelete}`)
    deleteDialog.value = false
    
    // 如果删除的是当前活动模板，则将活动模板重置为base
    if (activeTemplate.value === nameToDelete) {
        await setActiveTemplate('base')
    }
    await loadInitialData()
    selectedTemplate.value = 'base'
  } catch (error) {
    console.error(`删除模板 '${selectedTemplate.value}' 失败:`, error)
  } finally {
    saveLoading.value = false
  }
}

const confirmReset = async () => {
  resetLoading.value = true
  try {
    await axios.post('/api/t2i/templates/reset_default')
    resetDialog.value = false
    if (selectedTemplate.value === 'base') {
      await loadTemplateContent('base')
    }
    if (activeTemplate.value !== 'base') {
        await setActiveTemplate('base')
    }
  } catch (error) {
    console.error('重置模板失败:', error)
  } finally {
    resetLoading.value = false
  }
}

// --- UI 交互方法 ---

const resetToDefault = () => {
  resetDialog.value = true
}

const newTemplate = () => {
  isCreatingNew.value = true
  selectedTemplate.value = null
  editingName.value = ''
  templateContent.value = `<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>New Template</title>
</head>
<body>
  <!-- 从这里开始编辑 -->
  <article>{{ text | safe }}</article>
</body>
</html>
`
}

const promptDelete = () => {
  if (selectedTemplate.value && selectedTemplate.value !== 'base') {
    deleteDialog.value = true
  }
}

const promptApplyAndClose = () => {
  if (!isCreatingNew.value && selectedTemplate.value) {
    applyAndCloseDialog.value = true
  }
}

const confirmApplyAndClose = async () => {
  if (isCreatingNew.value) return
  
  await saveTemplate()
  await setActiveTemplate(selectedTemplate.value)
  applyAndCloseDialog.value = false
  closeDialog()
}

const refreshPreview = () => {
  previewLoading.value = true
  nextTick(() => {
    if (previewFrame.value) {
      previewFrame.value.contentWindow.location.reload()
    }
    setTimeout(() => previewLoading.value = false, 500)
  })
}

const closeDialog = () => {
  dialog.value = false
}

// --- 监听器和生命周期 ---

watch(dialog, (newVal) => {
  if (newVal) {
    loadInitialData()
  } else {
    // 关闭时重置状态
    selectedTemplate.value = null
    templateContent.value = ''
    isCreatingNew.value = false
  }
})

watch(selectedTemplate, (newName) => {
  if (newName) {
    isCreatingNew.value = false
    loadTemplateContent(newName)
  }
})

defineExpose({
  openDialog: () => {
    dialog.value = true
  }
})
</script>

<style scoped>
.preview-container {
  background-color: #f5f5f5;
  position: relative;
}

.preview-container::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-image: 
    linear-gradient(45deg, #ccc 25%, transparent 25%), 
    linear-gradient(-45deg, #ccc 25%, transparent 25%), 
    linear-gradient(45deg, transparent 75%, #ccc 75%), 
    linear-gradient(-45deg, transparent 75%, #ccc 75%);
  background-size: 20px 20px;
  background-position: 0 0, 0 10px, 10px -10px, -10px 0px;
  opacity: 0.1;
  pointer-events: none;
}

code {
  background-color: rgba(0,0,0,0.05);
  padding: 2px 4px;
  border-radius: 3px;
  font-size: 0.875em;
}
</style>
