<template>
  <div class="spcode-project-indicator">
    <v-tooltip location="bottom" :open-delay="200">
      <template #activator="{ props: tipProps }">
        <v-chip
          v-bind="tipProps"
          :color="status.loaded ? 'success' : undefined"
          :variant="status.loaded ? 'tonal' : 'outlined'"
          :prepend-icon="status.loaded ? 'mdi-folder-check-outline' : 'mdi-folder-outline'"
          size="small"
          density="comfortable"
          class="spcode-project-indicator__chip"
          :class="{
            'spcode-project-indicator__chip--loaded': status.loaded,
            'spcode-project-indicator__chip--empty': !status.loaded,
          }"
          :title="status.loaded ? status.directory ?? '' : ''"
          @click="openLoadDialog"
        >
          <span class="spcode-project-indicator__label">
            {{
              status.loaded
                ? tm('spcodeProjectLoad.indicator.loadedLabel')
                : tm('spcodeProjectLoad.indicator.noProject')
            }}
          </span>
          <span
            v-if="status.loaded && displayPath"
            class="spcode-project-indicator__path"
          >
            {{ displayPath }}
          </span>
        </v-chip>
      </template>
      <!--
        Tooltip deliberately only shows the load time. The directory is
        already visible (truncated) on the chip itself and the click
        opens the full project-load dialog, so neither needs to be
        repeated in the hover hint.
      -->
      <span v-if="status.loaded && loadedAtDisplay">
        {{ tm('spcodeProjectLoad.indicator.loadedAtPrefix') }}: {{ loadedAtDisplay }}
      </span>
      <span v-else>
        {{ tm('spcodeProjectLoad.indicator.noProject') }}
      </span>
    </v-tooltip>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useModuleI18n } from '@/i18n/composables'
import { useSpcodeProjectStatus } from '@/composables/useSpcodeProjectStatus'

const { status } = useSpcodeProjectStatus()
const { tm } = useModuleI18n('features/chat')

const emit = defineEmits<{
  (e: 'open-load-dialog'): void
}>()

/** Trim a long path to keep the chip compact. */
const displayPath = computed(() => {
  if (!status.value.directory) return ''
  const path = status.value.directory
  if (path.length <= 48) return path
  return `\u2026${path.slice(-47)}`
})

const loadedAtDisplay = computed(() => {
  if (!status.value.loadedAt) return ''
  const ts = status.value.loadedAt
  // Backend stores seconds; if the value looks like ms, down-scale.
  const ms = ts > 1e12 ? ts : ts * 1000
  try {
    const d = new Date(ms)
    if (Number.isNaN(d.getTime())) return ''
    return d.toLocaleString()
  } catch {
    return ''
  }
})

function openLoadDialog() {
  // The "加载项目目录" dialog lives in <ProjectLoadDialog/>, mounted
  // at the ChatInput level so it survives the + menu's lazy mount
  // cycle. This chip is just one of two triggers (the + menu's
  // <ProjectLoadMenuItem/> is the other); both bubble up through
  // emit("open-load-dialog") and the parent calls the dialog's
  // exposed opener.
  emit('open-load-dialog')
}
</script>

<style scoped>
.spcode-project-indicator {
  align-items: center;
  display: flex;
  min-width: 0;
}

.spcode-project-indicator__chip {
  cursor: pointer;
  max-width: 100%;
  min-width: 0;
}

.spcode-project-indicator__chip--loaded {
  font-weight: 500;
}

.spcode-project-indicator__label {
  flex: 0 0 auto;
  white-space: nowrap;
}

.spcode-project-indicator__path {
  display: inline-block;
  flex: 0 1 auto;
  font-family: var(--v-font-mono, monospace);
  margin-left: 6px;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.spcode-project-indicator__chip--empty {
  opacity: 0.7;
}
</style>
