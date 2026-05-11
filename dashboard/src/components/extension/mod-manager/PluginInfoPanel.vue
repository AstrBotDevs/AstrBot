<script setup lang="ts">
import { computed } from 'vue'
import type { PluginSummary } from './types'

import PluginBehaviorPanel from './PluginBehaviorPanel.vue'

const props = defineProps<{
  plugin: PluginSummary
}>()

const emit = defineEmits<{
  (e: 'action-update'): void
  (e: 'open-repo', url: string): void
}>()

const displayTitle = computed(() => props.plugin.display_name || props.plugin.name)

const hasLogo = computed(() => Boolean(props.plugin.logo))

const statusChips = computed(() => {
  const chips: Array<{ text: string; color: string }> = []
  chips.push({
    text: props.plugin.activated ? '已启用' : '已停用',
    color: props.plugin.activated ? 'success' : 'warning'
  })

  if (props.plugin.reserved) {
    chips.push({ text: '系统插件', color: 'primary' })
  }

  if (props.plugin.has_update) {
    chips.push({ text: '有更新', color: 'warning' })
  }

  return chips
})

const handlers = computed(() => props.plugin.handlers ?? [])

const handleOpenRepo = () => {
  if (!props.plugin.repo) return
  emit('open-repo', props.plugin.repo)
}
</script>

<template>
  <v-card class="h-100 d-flex flex-column" rounded="lg" variant="flat">
    <v-card-title class="d-flex align-start justify-space-between ga-4">
      <div class="d-flex ga-4" style="min-width: 0">
        <v-avatar size="56" rounded="lg" class="plugin-avatar">
          <v-img v-if="hasLogo" :src="plugin.logo || ''" cover />
          <v-icon v-else size="30">mdi-puzzle-outline</v-icon>
        </v-avatar>

        <div class="flex-grow-1" style="min-width: 0">
          <div class="d-flex align-center flex-wrap ga-2" style="min-width: 0">
            <div class="text-h6 text-truncate" style="max-width: 520px">
              {{ displayTitle }}
            </div>

            <v-chip
              v-for="chip in statusChips"
              :key="chip.text"
              :color="chip.color"
              size="small"
              variant="tonal"
              class="font-weight-medium"
            >
              {{ chip.text }}
            </v-chip>
          </div>

          <div class="text-caption text-medium-emphasis text-truncate" style="max-width: 720px">
            {{ plugin.name }}
          </div>
        </div>
      </div>

      <div class="d-flex align-center ga-2">
        <v-btn
          v-if="plugin.repo"
          icon
          size="small"
          variant="text"
          @click="handleOpenRepo"
        >
          <v-icon size="20">mdi-github</v-icon>
          <v-tooltip activator="parent" location="top">打开仓库</v-tooltip>
        </v-btn>
      </div>
    </v-card-title>

    <v-card-text class="pt-0 flex-grow-1 d-flex flex-column" style="min-height: 0">
      <div>
        <v-row dense>
          <v-col cols="12" md="6">
            <div class="text-caption text-medium-emphasis mb-1">版本</div>
            <div class="text-body-2">{{ plugin.version }}</div>
          </v-col>

          <v-col cols="12" md="6">
            <div class="text-caption text-medium-emphasis mb-1">作者</div>
            <div class="text-body-2">{{ plugin.author }}</div>
          </v-col>

          <v-col cols="12">
            <div class="text-caption text-medium-emphasis mb-1">描述</div>
            <div class="text-body-2 description">{{ plugin.desc || '—' }}</div>
          </v-col>
        </v-row>

        <v-divider class="my-4" />

        <div class="d-flex align-center flex-wrap ga-2">
          <v-btn
            v-if="plugin.has_update"
            color="warning"
            prepend-icon="mdi-download"
            variant="tonal"
            @click="emit('action-update')"
          >
            更新
          </v-btn>
        </div>

        <v-divider class="my-4" />
      </div>

      <div class="plugin-info-panel__behavior flex-grow-1" style="min-height: 0">
        <PluginBehaviorPanel :handlers="handlers" embedded />
      </div>
    </v-card-text>
  </v-card>
</template>

<style scoped>
.plugin-avatar {
  background: rgba(0, 0, 0, 0.03);
}

.text-truncate {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.description {
  white-space: pre-wrap;
  word-break: break-word;
}

.plugin-info-panel__behavior {
  overflow-y: auto;
}
</style>