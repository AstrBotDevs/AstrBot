<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { ConflictStats, PluginSummary } from './types'

type Mode = 'inactive' | 'active'

const props = defineProps<{
  title: string
  items: PluginSummary[]
  selectedNames: string[]
  selectedPluginName: string | null
  mode: Mode
  conflictStats: ConflictStats
  loading?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:selectedNames', names: string[]): void
  (e: 'row-click', name: string): void
  (e: 'action-primary', plugin: PluginSummary): void

  (e: 'batch-primary', plugins: PluginSummary[]): void
  (e: 'batch-update', names: string[]): void
  (e: 'batch-uninstall', names: string[]): void
  (e: 'clear-selection'): void

  (e: 'action-configure', plugin: PluginSummary): void
  (e: 'action-open-readme', plugin: PluginSummary): void
  (e: 'action-reload', name: string): void
  (e: 'action-update', name: string): void
  (e: 'action-uninstall', name: string): void
  (e: 'action-open-repo', url: string): void
}>()

const selectionModel = computed<string[]>({
  get: () => props.selectedNames ?? [],
  set: (val) => emit('update:selectedNames', val ?? [])
})

const primaryAction = computed(() => {
  if (props.mode === 'inactive') {
    return {
      color: 'success',
      icon: 'mdi-play-circle-outline',
      tooltip: '启用'
    }
  }
  return {
    color: 'error',
    icon: 'mdi-stop-circle-outline',
    tooltip: '停用'
  }
})

const headers = computed(() => [
  { title: '#', key: 'index', sortable: false, width: '36px' },
  { title: '', key: 'data-table-select', sortable: false, width: '32px' },
  { title: '插件', key: 'name', minWidth: '160px' }
])

const pluginCount = computed(() => props.items?.length ?? 0)

const indexByName = computed(() => {
  const map = new Map<string, number>()
  for (const [idx, plugin] of (props.items ?? []).entries()) {
    map.set(plugin.name, idx)
  }
  return map
})

const selectedPlugins = computed<PluginSummary[]>(() => {
  const names = new Set(props.selectedNames ?? [])
  return (props.items ?? []).filter((p) => names.has(p.name))
})

const updatableSelectedNames = computed(() =>
  selectedPlugins.value.filter((p) => Boolean(p.has_update)).map((p) => p.name)
)

const uninstallableSelectedNames = computed(() =>
  selectedPlugins.value.filter((p) => !p.reserved).map((p) => p.name)
)

const batchLabel = computed(() => (props.mode === 'inactive' ? '批量激活' : '批量停用'))
const batchIcon = computed(() => (props.mode === 'inactive' ? 'mdi-play' : 'mdi-pause'))
const batchColor = computed(() => (props.mode === 'inactive' ? 'success' : 'warning'))

const handleBatchPrimary = () => {
  emit('batch-primary', selectedPlugins.value)
}

const handleBatchUpdate = () => {
  const names = updatableSelectedNames.value
  if (names.length === 0) return
  emit('batch-update', names)
}

const showUninstallDialog = ref(false)
const pendingUninstallNames = ref<string[]>([])

const openBatchUninstallConfirm = () => {
  pendingUninstallNames.value = uninstallableSelectedNames.value
  showUninstallDialog.value = true
}

const confirmBatchUninstall = () => {
  const names = pendingUninstallNames.value
  showUninstallDialog.value = false
  if (names.length === 0) return
  emit('batch-uninstall', names)
}

const handleClearSelection = () => emit('clear-selection')

const titleBarRef = ref<HTMLElement | null>(null)
const titleMetaRef = ref<HTMLElement | null>(null)
const secondaryMeasureRef = ref<HTMLElement | null>(null)

const resolveElement = (value: unknown): HTMLElement | null => {
  const candidate = value as any
  if (candidate instanceof HTMLElement) return candidate
  if (candidate?.$el instanceof HTMLElement) return candidate.$el
  return null
}

const showInlinePrimary = ref(true)
const showInlineBatchUpdate = ref(true)
const showInlineBatchUninstall = ref(true)
const showInlineClearSelection = ref(true)

const showSecondaryMenu = computed(
  () =>
    !showInlinePrimary.value ||
    !showInlineBatchUpdate.value ||
    !showInlineBatchUninstall.value ||
    !showInlineClearSelection.value
)

const getMeasuredWidth = (key: string): number => {
  const root = resolveElement(secondaryMeasureRef.value)
  if (!root) return 0
  const el = root.querySelector(`[data-measure="${key}"]`) as HTMLElement | null
  if (!el) return 0
  return el.getBoundingClientRect().width
}

const recomputeSecondaryActions = () => {
  const titleBar = resolveElement(titleBarRef.value)
  const titleMeta = resolveElement(titleMetaRef.value)
  const secondaryMeasure = resolveElement(secondaryMeasureRef.value)

  if (!titleBar || !titleMeta || !secondaryMeasure) {
    showInlinePrimary.value = false
    showInlineBatchUpdate.value = false
    showInlineBatchUninstall.value = false
    showInlineClearSelection.value = false
    return
  }

  const available = titleBar.clientWidth
  const left = Math.max(titleMeta.getBoundingClientRect().width, titleMeta.scrollWidth)

  const wPrimary = getMeasuredWidth('batch-primary')
  const wUpdate = getMeasuredWidth('batch-update')
  const wUninstall = getMeasuredWidth('batch-uninstall')
  const wClear = getMeasuredWidth('clear-selection')
  const wMenu = getMeasuredWidth('more-menu')

  const basePadding = 24

  const calcRequired = (opts: {
    primary: boolean
    update: boolean
    uninstall: boolean
    clear: boolean
  }): number => {
    const inlineWidth =
      (opts.primary ? wPrimary : 0) +
      (opts.update ? wUpdate : 0) +
      (opts.uninstall ? wUninstall : 0) +
      (opts.clear ? wClear : 0)

    const needsMenu = !opts.primary || !opts.update || !opts.uninstall || !opts.clear
    return left + inlineWidth + (needsMenu ? wMenu : 0) + basePadding
  }

  // 标题永远不截断；空间不够时继续折叠按钮（先清理、再卸载、再更新、最后才折叠主按钮）
  let opts = { primary: true, update: true, uninstall: true, clear: true }
  if (calcRequired(opts) <= available) {
    showInlinePrimary.value = opts.primary
    showInlineBatchUpdate.value = opts.update
    showInlineBatchUninstall.value = opts.uninstall
    showInlineClearSelection.value = opts.clear
    return
  }

  opts = { primary: true, update: true, uninstall: true, clear: false }
  if (calcRequired(opts) <= available) {
    showInlinePrimary.value = opts.primary
    showInlineBatchUpdate.value = opts.update
    showInlineBatchUninstall.value = opts.uninstall
    showInlineClearSelection.value = opts.clear
    return
  }

  opts = { primary: true, update: true, uninstall: false, clear: false }
  if (calcRequired(opts) <= available) {
    showInlinePrimary.value = opts.primary
    showInlineBatchUpdate.value = opts.update
    showInlineBatchUninstall.value = opts.uninstall
    showInlineClearSelection.value = opts.clear
    return
  }

  opts = { primary: true, update: false, uninstall: false, clear: false }
  if (calcRequired(opts) <= available) {
    showInlinePrimary.value = opts.primary
    showInlineBatchUpdate.value = opts.update
    showInlineBatchUninstall.value = opts.uninstall
    showInlineClearSelection.value = opts.clear
    return
  }

  opts = { primary: false, update: false, uninstall: false, clear: false }
  showInlinePrimary.value = opts.primary
  showInlineBatchUpdate.value = opts.update
  showInlineBatchUninstall.value = opts.uninstall
  showInlineClearSelection.value = opts.clear
}

let resizeObserver: ResizeObserver | null = null

onMounted(() => {
  resizeObserver = new ResizeObserver(() => {
    recomputeSecondaryActions()
  })
  const el = resolveElement(titleBarRef.value)
  if (el) {
    resizeObserver.observe(el)
  }
  void nextTick(() => recomputeSecondaryActions())
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  resizeObserver = null
})

watch(
  () => [selectedPlugins.value.length, updatableSelectedNames.value.length, uninstallableSelectedNames.value.length],
  () => nextTick(() => recomputeSecondaryActions()),
  { flush: 'post' }
)

const getOnlineVersion = (plugin: PluginSummary): string | null => {
  return (plugin.online_version || plugin.online_vesion || null) as string | null
}

const getConflict = (pluginName: string) => {
  return props.conflictStats?.byPlugin?.get(pluginName)
}

const isUpgradable = (plugin: PluginSummary) => Boolean(plugin.has_update && getOnlineVersion(plugin))

const shouldIgnoreRowClick = (target: EventTarget | null): boolean => {
  const el = target as HTMLElement | null
  if (!el) return false

  return Boolean(
    el.closest(
      [
        'button',
        'a',
        '[role="button"]',
        '.v-btn',
        '.v-btn-group',
        '.v-selection-control',
        '.v-checkbox',
        '.v-input',
        '.v-field',
        '.v-icon'
      ].join(',')
    )
  )
}

const handleRowClick = (pluginName: string, event: MouseEvent) => {
  if (shouldIgnoreRowClick(event.target)) return
  emit('row-click', pluginName)
}

const getRowProps = ({ item }: { item: PluginSummary }) => {
  const classes: string[] = ['plugin-row']
  if (props.selectedPluginName && item.name === props.selectedPluginName) {
    classes.push('plugin-selected-row')
  }
  if (getConflict(item.name)?.count) {
    classes.push('plugin-conflict-row')
  }

  return {
    class: classes.join(' '),
    'data-plugin-name': item.name,
    onClick: (e: MouseEvent) => handleRowClick(item.name, e)
  }
}
</script>

<template>
  <v-card class="rounded-lg overflow-hidden elevation-1 plugin-list-table d-flex flex-column">
    <v-card-title ref="titleBarRef" class="d-flex align-center py-3 px-4 plugin-list-table__title">
      <div ref="titleMetaRef" class="d-flex align-center flex-shrink-0">
        <span class="text-subtitle-1 font-weight-medium">{{ title }}</span>
        <v-chip size="small" class="ml-2">{{ pluginCount }}</v-chip>
      </div>

      <v-spacer />

      <span v-if="showInlinePrimary" class="d-flex">
        <v-btn
          :color="batchColor"
          size="small"
          variant="tonal"
          :disabled="selectedPlugins.length === 0"
          @click.stop="handleBatchPrimary"
        >
          <v-icon start size="18">{{ batchIcon }}</v-icon>
          {{ batchLabel }}
          <span v-if="selectedPlugins.length" class="ml-1">({{ selectedPlugins.length }})</span>
        </v-btn>
      </span>

      <!-- 仅用于测量宽度：不参与布局（与实际展示按钮一致） -->
      <div ref="secondaryMeasureRef" class="plugin-list-table__secondary-measure d-flex align-center ga-1 ml-1">
        <span data-measure="batch-primary" class="d-flex">
          <v-btn
            :color="batchColor"
            size="small"
            variant="tonal"
            :disabled="selectedPlugins.length === 0"
          >
            <v-icon start size="18">{{ batchIcon }}</v-icon>
            {{ batchLabel }}
            <span v-if="selectedPlugins.length" class="ml-1">({{ selectedPlugins.length }})</span>
          </v-btn>
        </span>

        <span data-measure="batch-update" class="d-flex">
          <v-btn
            size="small"
            variant="tonal"
            color="warning"
            prepend-icon="mdi-update"
          >
            批量更新
            <span v-if="updatableSelectedNames.length" class="ml-1">({{ updatableSelectedNames.length }})</span>
          </v-btn>
        </span>

        <span data-measure="batch-uninstall" class="d-flex">
          <v-btn
            size="small"
            variant="tonal"
            color="error"
            prepend-icon="mdi-delete"
          >
            批量卸载
            <span v-if="uninstallableSelectedNames.length" class="ml-1">({{ uninstallableSelectedNames.length }})</span>
          </v-btn>
        </span>

        <span data-measure="clear-selection" class="d-flex">
          <v-btn
            size="small"
            variant="tonal"
            color="grey"
            prepend-icon="mdi-close"
          >
            取消选择
          </v-btn>
        </span>

        <span data-measure="more-menu" class="d-flex">
          <v-btn icon size="small" variant="text">
            <v-icon size="20">mdi-dots-vertical</v-icon>
          </v-btn>
        </span>
      </div>

      <div
        v-if="showInlineBatchUpdate || showInlineBatchUninstall || showInlineClearSelection"
        class="d-flex align-center ga-1 ml-1"
      >
        <v-btn
          v-if="showInlineBatchUpdate"
          size="small"
          variant="tonal"
          color="warning"
          prepend-icon="mdi-update"
          :disabled="updatableSelectedNames.length === 0"
          @click.stop="handleBatchUpdate"
        >
          批量更新
          <span v-if="updatableSelectedNames.length" class="ml-1">({{ updatableSelectedNames.length }})</span>
        </v-btn>

        <v-btn
          v-if="showInlineBatchUninstall"
          size="small"
          variant="tonal"
          color="error"
          prepend-icon="mdi-delete"
          :disabled="uninstallableSelectedNames.length === 0"
          @click.stop="openBatchUninstallConfirm"
        >
          批量卸载
          <span v-if="uninstallableSelectedNames.length" class="ml-1">({{ uninstallableSelectedNames.length }})</span>
        </v-btn>

        <v-btn
          v-if="showInlineClearSelection"
          size="small"
          variant="tonal"
          color="grey"
          prepend-icon="mdi-close"
          :disabled="selectedPlugins.length === 0"
          @click.stop="handleClearSelection"
        >
          取消选择
        </v-btn>
      </div>

      <v-menu v-if="showSecondaryMenu" location="bottom end" offset="6">
        <template #activator="{ props: menuProps }">
          <v-btn v-bind="menuProps" icon size="small" variant="text" class="ml-1" aria-label="more-batch">
            <v-icon size="20">mdi-dots-vertical</v-icon>
          </v-btn>
        </template>

        <v-list density="compact" nav class="pa-1">
          <v-list-item
            v-if="!showInlinePrimary"
            :disabled="selectedPlugins.length === 0"
            @click="handleBatchPrimary"
          >
            <template #prepend>
              <v-icon size="18">{{ batchIcon }}</v-icon>
            </template>
            <v-list-item-title>
              {{ batchLabel }}
              <span v-if="selectedPlugins.length" class="text-medium-emphasis">
                ({{ selectedPlugins.length }})
              </span>
            </v-list-item-title>
          </v-list-item>

          <v-divider v-if="!showInlinePrimary && (!showInlineBatchUpdate || !showInlineBatchUninstall || !showInlineClearSelection)" class="my-1" />

          <v-list-item
            v-if="!showInlineBatchUpdate"
            :disabled="updatableSelectedNames.length === 0"
            @click="handleBatchUpdate"
          >
            <template #prepend>
              <v-icon size="18">mdi-update</v-icon>
            </template>
            <v-list-item-title>
              批量更新
              <span v-if="updatableSelectedNames.length" class="text-medium-emphasis">
                ({{ updatableSelectedNames.length }})
              </span>
            </v-list-item-title>
          </v-list-item>

          <v-list-item
            v-if="!showInlineBatchUninstall"
            :disabled="uninstallableSelectedNames.length === 0"
            @click="openBatchUninstallConfirm"
          >
            <template #prepend>
              <v-icon size="18" color="error">mdi-delete</v-icon>
            </template>
            <v-list-item-title>
              批量卸载
              <span v-if="uninstallableSelectedNames.length" class="text-medium-emphasis">
                ({{ uninstallableSelectedNames.length }})
              </span>
            </v-list-item-title>
          </v-list-item>

          <v-divider v-if="!showInlineBatchUpdate || !showInlineBatchUninstall" class="my-1" />

          <v-list-item v-if="!showInlineClearSelection" :disabled="selectedPlugins.length === 0" @click="handleClearSelection">
            <template #prepend>
              <v-icon size="18">mdi-close</v-icon>
            </template>
            <v-list-item-title>取消选择</v-list-item-title>
          </v-list-item>
        </v-list>
      </v-menu>
    </v-card-title>

    <v-divider />

    <v-card-text class="pa-0 flex-grow-1" style="min-height: 0">
      <v-data-table
        v-model="selectionModel"
        class="flex-grow-1"
        style="min-height: 0"
        :headers="headers"
        :items="items"
        :loading="loading"
        show-select
        item-value="name"
        hover
        density="compact"
        hide-default-footer
        fixed-header
        height="100%"
        :items-per-page="-1"
        :row-props="getRowProps"
      >
        <template #loader>
          <v-row class="py-8 d-flex align-center justify-center">
            <v-progress-circular indeterminate color="primary" />
            <span class="ml-2">加载中...</span>
          </v-row>
        </template>

        <template #item.index="{ item }">
          <div class="text-caption text-medium-emphasis">
            {{ (indexByName.get(item.name) ?? 0) + 1 }}
          </div>
        </template>

        <template #item.name="{ item }">
          <div class="d-flex align-center ga-1 py-1" style="min-width: 0">
            <v-avatar size="20" rounded="sm" class="plugin-mini-avatar">
              <v-img v-if="item.logo" :src="item.logo" cover />
              <v-icon v-else size="16">mdi-puzzle-outline</v-icon>
            </v-avatar>

            <div class="text-body-2 font-weight-medium text-truncate flex-grow-1" style="min-width: 0">
              {{ item.display_name || item.name }}
            </div>

            <v-tooltip v-if="item.reserved" location="top">
              <template #activator="{ props: tipProps }">
                <v-icon v-bind="tipProps" size="16" color="primary">mdi-shield</v-icon>
              </template>
              <span>系统插件</span>
            </v-tooltip>

            <v-tooltip v-if="isUpgradable(item)" location="top">
              <template #activator="{ props: tipProps }">
                <v-btn
                  v-bind="tipProps"
                  icon
                  size="x-small"
                  color="warning"
                  variant="text"
                  aria-label="update-plugin"
                  @click.stop="emit('action-update', item.name)"
                >
                  <v-icon size="20">mdi-alert</v-icon>
                </v-btn>
              </template>
              <span>新版本：{{ getOnlineVersion(item) }}（点击更新）</span>
            </v-tooltip>

            <v-tooltip v-if="getConflict(item.name)?.count" location="top">
              <template #activator="{ props: tipProps }">
                <v-icon v-bind="tipProps" size="16" color="error">mdi-alert-circle-outline</v-icon>
              </template>
              <span>存在指令冲突：{{ getConflict(item.name)?.count }}</span>
            </v-tooltip>

            <div class="d-flex align-center ga-1 flex-shrink-0">
              <v-btn
                icon
                size="x-small"
                :color="primaryAction.color"
                variant="text"
                aria-label="toggle-plugin"
                @click.stop="emit('action-primary', item)"
              >
                <v-icon size="20">{{ primaryAction.icon }}</v-icon>
                <v-tooltip activator="parent" location="top">{{ primaryAction.tooltip }}</v-tooltip>
              </v-btn>

              <v-btn
                icon
                size="x-small"
                color="info"
                variant="text"
                aria-label="reload-plugin"
                @click.stop="emit('action-reload', item.name)"
              >
                <v-icon size="20">mdi-refresh</v-icon>
                <v-tooltip activator="parent" location="top">重载</v-tooltip>
              </v-btn>

              <v-btn
                icon
                size="x-small"
                color="error"
                variant="text"
                :disabled="item.reserved"
                aria-label="uninstall-plugin"
                @click.stop="emit('action-uninstall', item.name)"
              >
                <v-icon size="20">mdi-delete</v-icon>
                <v-tooltip activator="parent" location="top">卸载</v-tooltip>
              </v-btn>
            </div>
          </div>
        </template>

        <template #no-data>
          <div class="text-center pa-8">
            <v-icon size="64" color="info" class="mb-4">mdi-puzzle-outline</v-icon>
            <div class="text-h6 mb-2">暂无插件</div>
          </div>
        </template>
      </v-data-table>
    </v-card-text>

    <v-dialog v-model="showUninstallDialog" max-width="520">
      <v-card>
        <v-card-title class="text-h6 d-flex align-center">
          <v-icon color="error" class="mr-2">mdi-delete-alert</v-icon>
          确认卸载
        </v-card-title>

        <v-card-text>
          <div>
            确定要卸载选中的
            <strong>{{ pendingUninstallNames.length }}</strong>
            个插件吗？此操作不可撤销。
          </div>
          <div class="text-caption text-medium-emphasis mt-2">
            系统插件（reserved）不会出现在可卸载列表中。
          </div>

          <v-alert
            v-if="pendingUninstallNames.length === 0"
            type="info"
            variant="tonal"
            density="compact"
            class="mt-3"
          >
            当前选择中没有可卸载插件。
          </v-alert>

          <v-alert
            v-else
            type="warning"
            variant="tonal"
            density="compact"
            class="mt-3"
          >
            将卸载 {{ pendingUninstallNames.length }} 个插件。
          </v-alert>
        </v-card-text>

        <v-card-actions>
          <v-spacer />
          <v-btn color="grey" variant="text" @click="showUninstallDialog = false">取消</v-btn>
          <v-btn
            color="error"
            variant="elevated"
            :disabled="pendingUninstallNames.length === 0"
            @click="confirmBatchUninstall"
          >
            卸载
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-card>
</template>

<style scoped>
.plugin-list-table {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.plugin-list-table__title {
  position: relative;
  min-width: 0;
}

.plugin-list-table__secondary-measure {
  position: absolute;
  left: -99999px;
  top: -99999px;
  visibility: hidden;
  pointer-events: none;
}

.plugin-list-table :deep(.v-data-table__table) {
  table-layout: fixed;
}

.plugin-list-table :deep(.v-data-table__th),
.plugin-list-table :deep(.v-data-table__td) {
  padding-left: 6px !important;
  padding-right: 6px !important;
}

.plugin-list-table :deep(.v-data-table__td--select),
.plugin-list-table :deep(.v-data-table__th--select) {
  padding-left: 0px !important;
  padding-right: 0px !important;
}

.plugin-mini-avatar {
  background: rgba(0, 0, 0, 0.03);
}

.text-truncate {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>

<style>
.v-data-table .plugin-selected-row {
  background: linear-gradient(90deg, rgba(var(--v-theme-primary), 0.12) 0%, rgba(var(--v-theme-primary), 0.04) 100%) !important;
  border-left: 3px solid rgb(var(--v-theme-primary)) !important;
}

.v-data-table .plugin-selected-row:hover {
  background: linear-gradient(90deg, rgba(var(--v-theme-primary), 0.18) 0%, rgba(var(--v-theme-primary), 0.06) 100%) !important;
}

.v-data-table .plugin-conflict-row {
  background: linear-gradient(90deg, rgba(var(--v-theme-error), 0.12) 0%, rgba(var(--v-theme-error), 0.04) 100%) !important;
}

.v-data-table .plugin-conflict-row:hover {
  background: linear-gradient(90deg, rgba(var(--v-theme-error), 0.18) 0%, rgba(var(--v-theme-error), 0.06) 100%) !important;
}

.plugin-list-table .v-data-table__td {
  vertical-align: middle;
}
</style>