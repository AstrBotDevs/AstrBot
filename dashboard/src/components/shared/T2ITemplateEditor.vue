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
        <div class="d-flex gap-2">
          <v-btn
            v-if="hasCustomTemplate"
            variant="outlined"
            color="warning"
            size="small"
            @click="resetToDefault"
            :loading="resetLoading"
          >
            恢复默认
          </v-btn>
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
              <v-toolbar-title class="text-subtitle-2">HTML 模板编辑器</v-toolbar-title>
              <v-spacer></v-spacer>
              <v-btn 
                variant="text" 
                size="small" 
                @click="saveTemplate"
                :loading="saveLoading"
                color="primary"
              >
                保存模板
              </v-btn>
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
              @click="saveTemplate"
              :loading="saveLoading"
            >
              保存并应用
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
          确定要恢复默认模板吗？这将删除您的自定义模板，此操作无法撤销。
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn text @click="resetDialog = false">取消</v-btn>
          <v-btn color="warning" @click="confirmReset" :loading="resetLoading">确认重置</v-btn>
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

// 响应式数据
const dialog = ref(false)
const resetDialog = ref(false)
const loading = ref(false)
const saveLoading = ref(false)
const resetLoading = ref(false)
const previewLoading = ref(false)
const templateContent = ref('')
const hasCustomTemplate = ref(false)
const previewFrame = ref(null)

// 编辑器配置
const editorTheme = computed(() => 'vs-light')
const editorOptions = {
  automaticLayout: true,
  fontSize: 12,
  lineNumbers: 'on',
  wordWrap: 'on',
  minimap: { enabled: false },
  scrollBeyondLastLine: false,
}

// 示例数据用于预览
const previewData = {
  text: '这是一个示例文本，用于预览模板效果。\n\n这里可以包含多行文本，支持换行和各种格式。',
  version: 'v4.0.0'
}

// 生成预览内容
const previewContent = computed(() => {
  try {
    // 简单的模板替换，模拟 Jinja2 渲染
    let content = templateContent.value
    content = content.replace(/\{\{\s*text\s*\|\s*safe\s*\}\}/g, previewData.text)
    content = content.replace(/\{\{\s*version\s*\}\}/g, previewData.version)
    return content
  } catch (error) {
    return `<div style="color: red; padding: 20px;">模板渲染错误: ${error.message}</div>`
  }
})

// 方法
const loadTemplate = async () => {
  loading.value = true
  try {
    const response = await axios.get('/api/config/astrbot/t2i-template/get')
    if (response.data.status === 'ok') {
      templateContent.value = response.data.data.template
      hasCustomTemplate.value = response.data.data.has_custom_template
    } else {
      console.error('加载模板失败:', response.data.message)
    }
  } catch (error) {
    console.error('加载模板失败:', error)
  } finally {
    loading.value = false
  }
}

const saveTemplate = async () => {
  saveLoading.value = true
  try {
    const response = await axios.post('/api/config/astrbot/t2i-template/save', {
      template: templateContent.value
    })
    if (response.data.status === 'ok') {
      hasCustomTemplate.value = true
      closeDialog()
    } else {
      console.error('保存模板失败:', response.data.message)
    }
  } catch (error) {
    console.error('保存模板失败:', error)
  } finally {
    saveLoading.value = false
  }
}

const resetToDefault = () => {
  resetDialog.value = true
}

const confirmReset = async () => {
  resetLoading.value = true
  try {
    const response = await axios.delete('/api/config/astrbot/t2i-template/delete')
    if (response.data.status === 'ok') {
      hasCustomTemplate.value = false
      resetDialog.value = false
      // 重新加载默认模板
      await loadTemplate()
    } else {
      console.error('重置模板失败:', response.data.message)
    }
  } catch (error) {
    console.error('重置模板失败:', error)
  } finally {
    resetLoading.value = false
  }
}

const refreshPreview = () => {
  previewLoading.value = true
  nextTick(() => {
    if (previewFrame.value) {
      previewFrame.value.contentWindow.location.reload()
    }
    setTimeout(() => {
      previewLoading.value = false
    }, 500)
  })
}

const closeDialog = () => {
  dialog.value = false
}

watch(dialog, (newVal) => {
  if (newVal && !templateContent.value) {
    loadTemplate()
  }
})

defineExpose({
  openDialog: () => {
    dialog.value = true
    if (!templateContent.value) {
      loadTemplate()
    }
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
