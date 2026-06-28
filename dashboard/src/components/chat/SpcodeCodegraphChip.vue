<!--
  SpcodeCodegraphChip.vue

  Status chip that displays the codegraph MCP server state in the
  ChatInput status row. Sits alongside SpcodeProjectIndicator and
  SpcodePlanModeChip.

  Visual states:

  MCP running + project path matches loaded project
    → success tonal chip, "Codegraph已连接", no path shown
  MCP running + project path MISMATCHES loaded project
    → warning outlined chip, "Codegraph不匹配", path shown
  MCP running + no project path set
    → error outlined chip, "Codegraph未加载"
  MCP not running
    → error outlined chip, "Codegraph不可用"

  The chip's visibility is gated by the parent (ChatInput)'s
  showSpcodeIndicator — i.e. the spcode plugin must be enabled
  AND /project* commands must be registered.

  Author: elecvoid243
  Last-Modified: 2026-06-28
-->
<script setup lang="ts">
import { computed } from 'vue'
import { useSpcodeCodegraphStatus } from '@/composables/useSpcodeCodegraphStatus'
import { useSpcodeProjectStatus } from '@/composables/useSpcodeProjectStatus'

const emit = defineEmits<{
  (e: 'open-codegraph-dialog'): void
}>()

const { status } = useSpcodeCodegraphStatus()
const projectStatus = useSpcodeProjectStatus()

// ── Derived chip visuals ─────────────────────────────────────────────────

/** Whether MCP is running. */
const mcpOk = computed<boolean>(() => status.value.mcpRunning)

/** Whether a codegraph project path is set. */
const hasProject = computed<boolean>(
  () => status.value.activeProject.length > 0,
)

/** The loaded project directory from the project indicator. */
const loadedProjectDir = computed<string | null>(
  () => projectStatus.status.value.directory,
)

/** Whether codegraph's project path matches the loaded project path. */
const projectMatch = computed<boolean>(() => {
  if (!loadedProjectDir.value || !hasProject.value) return false
  return status.value.activeProject === loadedProjectDir.value
})

/** Chip color: green on match, dark-yellow on mismatch, red on error. */
const chipColor = computed<string>(() => {
  if (!mcpOk.value) return 'error'
  if (!hasProject.value) return 'error'
  if (!projectMatch.value) return 'warning'
  return 'success'
})

/** Tonal for the nominal state; outlined for any warning/error state. */
const chipVariant = computed<'tonal' | 'outlined'>(() => {
  if (!mcpOk.value) return 'outlined'
  if (!hasProject.value) return 'outlined'
  return projectMatch.value ? 'tonal' : 'outlined'
})

/** MDI icon reflecting the current state. */
const chipIcon = computed<string>(() => {
  if (!mcpOk.value) return 'mdi-database-off-outline'
  if (!hasProject.value) return 'mdi-database-remove-outline'
  if (!projectMatch.value) return 'mdi-alert-circle-outline'
  return 'mdi-database-check'
})

/** Short label on the chip. */
const chipLabel = computed<string>(() => {
  if (!mcpOk.value) return 'Codegraph不可用'
  if (!hasProject.value) return 'Codegraph未加载'
  if (!projectMatch.value) return 'Codegraph不匹配'
  return 'Codegraph已连接'
})

/** Whether to show the codegraph project path on the chip. */
const showPath = computed<boolean>(
  () => mcpOk.value && hasProject.value && !projectMatch.value,
)

/**
 * Trim a long project path so the chip stays compact.
 * Follows the same 48-char threshold as SpcodeProjectIndicator.
 */
const displayPath = computed<string>(() => {
  const path = status.value.activeProject
  if (!path) return ''
  if (path.length <= 48) return path
  return `\u2026${path.slice(-47)}`
})

/** Tooltip text: concise when matched, descriptive on issues. */
const tooltipText = computed<string>(() => {
  if (!mcpOk.value) {
    return 'MCP 未运行, codegraph 不可用'
  }
  if (!hasProject.value) {
    return 'Codegraph 未加载项目'
  }
  if (!projectMatch.value) {
    const parts: string[] = [
      '警告: codegraph 项目与当前加载项目不一致',
      `codegraph: ${status.value.activeProject}`,
    ]
    if (loadedProjectDir.value) {
      parts.push(`加载项目: ${loadedProjectDir.value}`)
    }
    return parts.join(' \u00b7 ')
  }
  return `Codegraph 已连接 \u00b7 ${status.value.activeProject}`
})
</script>

<template>
  <div class="spcode-codegraph-chip">
    <v-tooltip location="bottom" :open-delay="200">
      <template #activator="{ props: tipProps }">
        <v-chip
          v-bind="tipProps"
          :color="chipColor"
          :variant="chipVariant"
          :prepend-icon="chipIcon"
          size="small"
          density="comfortable"
          class="spcode-codegraph-chip__el"
          @click="emit('open-codegraph-dialog')"
          :class="{
            'spcode-codegraph-chip--running': mcpOk && hasProject && projectMatch,
            'spcode-codegraph-chip--degraded': !mcpOk || !hasProject,
            'spcode-codegraph-chip--mismatch': mcpOk && hasProject && !projectMatch,
          }"
        >
          <span class="spcode-codegraph-chip__label">{{ chipLabel }}</span>
          <span
            v-if="showPath"
            class="spcode-codegraph-chip__path"
          >
            {{ displayPath }}
          </span>
        </v-chip>
      </template>
      <span>{{ tooltipText }}</span>
    </v-tooltip>
  </div>
</template>

<style scoped>
.spcode-codegraph-chip {
  align-items: center;
  display: flex;
  min-width: 0;
}

.spcode-codegraph-chip__el {
  cursor: pointer;
  max-width: 100%;
  min-width: 0;
}

.spcode-codegraph-chip--running {
  font-weight: 500;
}

.spcode-codegraph-chip--degraded {
  opacity: 0.8;
}

.spcode-codegraph-chip--mismatch {
  font-weight: 500;
}

.spcode-codegraph-chip__label {
  flex: 0 0 auto;
  white-space: nowrap;
}

.spcode-codegraph-chip__path {
  display: inline-block;
  flex: 0 1 auto;
  font-family: var(--v-font-mono, monospace);
  margin-left: 6px;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
