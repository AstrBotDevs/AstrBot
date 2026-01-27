<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import AstrBotConfig from '@/components/shared/AstrBotConfig.vue'
import { usePluginConfigCache } from '@/composables/usePluginConfigCache'

const props = defineProps<{
  pluginName: string
  active?: boolean
}>()

const emit = defineEmits<{
  (e: 'saved', pluginName: string): void
  (e: 'error', message: string): void
}>()

const cache = usePluginConfigCache()

const loading = ref(false)
const error = ref<string | null>(null)

const draftMetadata = ref<Record<string, any> | null>(null)
const draftConfig = ref<Record<string, any> | null>(null)
const originalConfig = ref<Record<string, any> | null>(null)

const isDirty = computed(() => {
  if (!draftConfig.value || !originalConfig.value) return false
  return JSON.stringify(draftConfig.value) !== JSON.stringify(originalConfig.value)
})

function deepClone<T>(value: T): T {
  if (typeof structuredClone === 'function') {
    return structuredClone(value)
  }
  return JSON.parse(JSON.stringify(value)) as T
}

const canLoad = computed(() => Boolean(props.pluginName) && Boolean(props.active))

async function loadFromCache() {
  if (!props.pluginName) return
  loading.value = true
  error.value = null
  try {
    const entry = await cache.getOrFetch(props.pluginName)
    const configClone = deepClone(entry.config || {})
    const metadataClone = deepClone(entry.metadata || {})
    draftConfig.value = configClone
    originalConfig.value = deepClone(configClone)
    draftMetadata.value = metadataClone
  } catch (err: any) {
    const message = err?.message || String(err)
    error.value = message
    emit('error', message)
  } finally {
    loading.value = false
  }
}

function resetDraft() {
  if (!originalConfig.value) return
  draftConfig.value = deepClone(originalConfig.value)
}

async function saveDraft() {
  if (!props.pluginName || !draftConfig.value) return
  loading.value = true
  error.value = null
  try {
    await cache.updateConfig(props.pluginName, draftConfig.value)
    originalConfig.value = deepClone(draftConfig.value)
    emit('saved', props.pluginName)
  } catch (err: any) {
    const message = err?.message || String(err)
    error.value = message
    emit('error', message)
  } finally {
    loading.value = false
  }
}

watch(
  () => props.active,
  (isActive) => {
    if (isActive && props.pluginName) {
      loadFromCache()
    }
  },
  { immediate: true }
)

watch(
  () => props.pluginName,
  (name) => {
    if (props.active && name) {
      loadFromCache()
    } else {
      draftMetadata.value = null
      draftConfig.value = null
      originalConfig.value = null
      error.value = null
      loading.value = false
    }
  }
)
</script>

<template>
  <v-card class="h-100 d-flex flex-column" rounded="lg" variant="flat">
    <v-card-title class="d-flex align-center ga-3">
      <div class="text-subtitle-1 font-weight-medium">插件配置</div>
      <v-spacer />

      <v-btn
        color="primary"
        variant="flat"
        :disabled="!draftConfig || !draftMetadata || !isDirty"
        :loading="loading"
        @click="saveDraft"
      >
        保存
      </v-btn>

      <v-btn
        variant="text"
        :disabled="!draftConfig || !isDirty || loading"
        @click="resetDraft"
      >
        取消
      </v-btn>
    </v-card-title>

    <v-divider />

    <v-progress-linear v-if="loading" indeterminate color="primary" />

    <v-card-text class="pa-0 flex-grow-1 d-flex flex-column" style="min-height: 0">
      <div v-if="error" class="pa-6">
        <v-alert type="error" variant="tonal" class="mb-4">
          {{ error }}
        </v-alert>
        <v-btn color="primary" variant="tonal" @click="loadFromCache">
          重试
        </v-btn>
      </div>

      <div v-else class="config-scroll">
        <div v-if="draftMetadata && draftConfig" class="pa-4">
          <AstrBotConfig
            :metadata="draftMetadata"
            :iterable="draftConfig"
            :metadataKey="pluginName"
            :is-editing="true"
          />
        </div>

        <div v-else class="pa-6 text-center text-medium-emphasis">
          <v-icon size="56" class="mb-2">mdi-cog-outline</v-icon>
          <div class="text-body-1">暂无可用配置</div>
        </div>
      </div>
    </v-card-text>
  </v-card>
</template>

<style scoped>
.config-scroll {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
}
</style>