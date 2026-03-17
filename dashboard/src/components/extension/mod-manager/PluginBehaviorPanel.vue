<script setup lang="ts">
import { computed } from 'vue'
import type { PluginHandlerInfo } from './types'

const props = defineProps<{
  handlers: PluginHandlerInfo[]
  /**
   * 嵌入模式：用于在其他面板中作为一个分区展示。
   * - 不强制撑满高度
   * - 不使用 fixed-header / height=100%（避免在可滚动容器内布局异常）
   */
  embedded?: boolean
}>()

const headers = computed(() => [
  { title: '事件类型', key: 'event_type_h', width: '160px' },
  { title: '处理器名称', key: 'handler_name', width: '200px' },
  { title: '描述', key: 'desc', minWidth: '240px' },
  { title: '类型', key: 'type', width: '140px' },
  { title: '命令', key: 'cmd', width: '160px' }
])

const items = computed(() => props.handlers ?? [])

const title = computed(() => (props.embedded ? '行为' : '行为面板'))
const emptyPaddingClass = computed(() => (props.embedded ? 'pa-6' : 'pa-10'))
</script>

<template>
  <v-card
    :class="['d-flex flex-column', props.embedded ? 'plugin-behavior-panel--embedded' : 'h-100']"
    rounded="lg"
    :variant="props.embedded ? 'outlined' : 'flat'"
  >
    <v-card-title class="d-flex align-center">
      <div class="text-subtitle-1 font-weight-medium">{{ title }}</div>
      <v-spacer />
      <v-chip size="small" variant="tonal">{{ items.length }}</v-chip>
    </v-card-title>

    <v-divider />

    <v-card-text class="pa-0 flex-grow-1">
      <div v-if="items.length === 0" class="text-center" :class="emptyPaddingClass">
        <v-icon size="64" color="info" class="mb-4">mdi-vector-link</v-icon>
        <div class="text-h6 mb-2">该插件未注册任何处理器</div>
      </div>

      <v-data-table
        v-else
        :headers="headers"
        :items="items"
        item-value="handler_full_name"
        hover
        density="compact"
        :fixed-header="!props.embedded"
        :height="props.embedded ? undefined : '100%'"
        hide-default-footer
        :items-per-page="-1"
      >
        <template #item.desc="{ item }">
          <div class="text-body-2 text-medium-emphasis text-truncate" style="max-width: 520px">
            {{ item.desc }}
          </div>
        </template>

        <template #item.type="{ item }">
          <v-chip v-if="item.type" color="success" size="x-small" variant="tonal">
            {{ item.type }}
          </v-chip>
          <span v-else class="text-medium-emphasis">—</span>
        </template>

        <template #item.cmd="{ item }">
          <span v-if="item.cmd" class="font-weight-medium" style="font-family: monospace">
            {{ item.cmd }}
          </span>
          <span v-else class="text-medium-emphasis">—</span>
        </template>
      </v-data-table>
    </v-card-text>
  </v-card>
</template>

<style scoped>
.text-truncate {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>