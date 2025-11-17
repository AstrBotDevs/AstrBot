<template>
  <v-dialog v-model="dialog" max-width="500px" persistent>
    <v-card>
      <v-card-title class="text-h5">
        配置 Tavily API Key
      </v-card-title>
      <v-card-text>
        <p class="mb-4 text-body-2 text-medium-emphasis">
          为了使用基于网页的知识库功能，需要提供 Tavily API Key。您可以从 <a href="https://tavily.com/" target="_blank">Tavily 官网</a> 获取。
        </p>
        <v-text-field
          v-model="apiKey"
          label="Tavily API Key"
          variant="outlined"
          :loading="saving"
          :error-messages="errorMessage"
          autofocus
          clearable
          placeholder="tvly-..."
        />
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="closeDialog" :disabled="saving">
          取消
        </v-btn>
        <v-btn color="primary" variant="elevated" @click="saveKey" :loading="saving">
          保存
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import axios from 'axios'

const props = defineProps<{
  modelValue: boolean
}>()

const emit = defineEmits(['update:modelValue', 'success'])

const dialog = ref(props.modelValue)
const apiKey = ref('')
const saving = ref(false)
const errorMessage = ref('')

watch(() => props.modelValue, (val) => {
  dialog.value = val
  if (val) {
    // Reset state when dialog opens
    apiKey.value = ''
    errorMessage.value = ''
    saving.value = false
  }
})

const closeDialog = () => {
  emit('update:modelValue', false)
}

const saveKey = async () => {
  if (!apiKey.value.trim()) {
    errorMessage.value = 'API Key 不能为空'
    return
  }
  errorMessage.value = ''
  saving.value = true
  try {
    // 1. 获取当前配置
    const configResponse = await axios.get('/api/config/abconf', {
      params: { id: 'default' }
    })

    if (configResponse.data.status !== 'ok') {
      throw new Error('获取当前配置失败')
    }

    const currentConfig = configResponse.data.data.config

    // 2. 更新配置
    if (!currentConfig.provider_settings) {
      currentConfig.provider_settings = {}
    }
    currentConfig.provider_settings.websearch_tavily_key = [apiKey.value.trim()]
    // 同时将搜索提供商设置为 tavily
    currentConfig.provider_settings.websearch_provider = 'tavily'

    // 3. 保存整个配置
    const saveResponse = await axios.post('/api/config/astrbot/update', {
      conf_id: 'default',
      config: currentConfig
    })

    if (saveResponse.data.status === 'ok') {
      emit('success')
      closeDialog()
    } else {
      errorMessage.value = saveResponse.data.message || '保存失败，请检查 Key 是否正确'
    }
  } catch (error: any) {
    errorMessage.value = error.response?.data?.message || '保存失败，发生未知错误'
  } finally {
    saving.value = false
  }
}
</script>