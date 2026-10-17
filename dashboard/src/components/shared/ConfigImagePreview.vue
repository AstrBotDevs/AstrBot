<template>
  <div class="config-image-preview">
    <v-btn v-if="imageUrl" class="preview-button" variant="text" width="48" height="48"
      :aria-label="tm('fileUpload.previewImage', { name: fileName })" @click.stop="previewOpen = true">
      <img :src="imageUrl" :alt="fileName" class="thumbnail" />
    </v-btn>
    <v-progress-circular v-else-if="loading" indeterminate size="20"
      :aria-label="tm('fileUpload.loadingPreview')" />
    <span v-else role="img" :aria-label="tm('fileUpload.previewUnavailable')"
      :title="tm('fileUpload.previewUnavailable')" class="text-medium-emphasis">
      <v-icon size="24">mdi-image-outline</v-icon>
    </span>

    <v-dialog v-model="previewOpen" max-width="960">
      <v-card variant="flat">
        <v-card-title class="text-h3 pa-4 pb-0 pl-6 d-flex align-center">
          <span class="text-truncate">{{ fileName }}</span>
          <v-spacer />
          <v-btn icon="mdi-close" variant="text" :aria-label="tm('fileUpload.closePreview')"
            @click="previewOpen = false" />
        </v-card-title>
        <v-card-text>
          <img v-if="imageUrl" :src="imageUrl" :alt="fileName" class="full-preview" />
        </v-card-text>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { pluginApi } from '@/api/v1'
import { useModuleI18n } from '@/i18n/composables'

const props = defineProps({
  pluginName: { type: String, required: true },
  configKey: { type: String, required: true },
  path: { type: String, required: true }
})

const { tm } = useModuleI18n('features/config')
const fileName = computed(() => props.path.split('/').pop() || props.path)
const imageUrl = ref('')
const loading = ref(false)
const previewOpen = ref(false)

watch(
  () => [props.pluginName, props.configKey, props.path],
  async (_, __, onCleanup) => {
    const controller = new AbortController()
    let active = true
    let objectUrl = ''
    imageUrl.value = ''
    previewOpen.value = false
    loading.value = true
    onCleanup(() => {
      active = false
      controller.abort()
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    })
    try {
      const response = await pluginApi.previewConfigImage(
        props.pluginName, props.configKey, props.path, controller.signal
      )
      if (active && response.data instanceof Blob && response.data.type === 'image/png') {
        objectUrl = URL.createObjectURL(response.data)
        imageUrl.value = objectUrl
      }
    } catch {
      // Unsupported, missing, or oversized images must not block file management.
    } finally {
      if (active) loading.value = false
    }
  },
  { immediate: true }
)
</script>

<style scoped>
.config-image-preview {
  width: 56px;
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.preview-button {
  min-width: 48px;
  padding: 0;
}

.thumbnail {
  width: 48px;
  height: 48px;
  object-fit: contain;
  border-radius: 4px;
}

.full-preview {
  display: block;
  width: 100%;
  max-height: 70vh;
  object-fit: contain;
}
</style>
