<template>
  <v-slide-y-transition>
    <div v-if="visible" class="batch-operation-bar">
      <v-toolbar
        class="batch-operation-bar__toolbar"
        color="surface"
        density="comfortable"
        elevation="8"
      >
        <div class="d-flex align-center flex-grow-1 ga-3 flex-wrap">
          <div class="d-flex align-center">
            <v-icon size="18" class="mr-2">mdi-checkbox-multiple-marked</v-icon>
            <span class="text-body-2">已选择 {{ totalSelected }} 个插件</span>
          </div>

          <v-divider vertical class="mx-1" />

          <div class="d-flex align-center ga-2 flex-wrap">
            <v-btn
              color="success"
              size="small"
              variant="flat"
              :disabled="isBusy || selectedInactive.length === 0"
              :loading="isBusy"
              @click="handleBatchEnable"
            >
              <v-icon start size="18">mdi-play</v-icon>
              批量启用
              <span v-if="selectedInactive.length" class="ml-1">({{ selectedInactive.length }})</span>
            </v-btn>

            <v-btn
              color="warning"
              size="small"
              variant="flat"
              :disabled="isBusy || selectedActive.length === 0"
              :loading="isBusy"
              @click="handleBatchDisable"
            >
              <v-icon start size="18">mdi-pause</v-icon>
              批量停用
              <span v-if="selectedActive.length" class="ml-1">({{ selectedActive.length }})</span>
            </v-btn>

            <v-btn
              color="primary"
              size="small"
              variant="flat"
              :disabled="isBusy || updatablePlugins.length === 0"
              :loading="isBusy"
              @click="handleBatchUpdate"
            >
              <v-icon start size="18">mdi-update</v-icon>
              批量更新
              <span class="ml-1">({{ updatablePlugins.length }})</span>
            </v-btn>

            <v-btn
              color="error"
              size="small"
              variant="flat"
              :disabled="isBusy || uninstallablePlugins.length === 0"
              :loading="isBusy"
              @click="openUninstallConfirm"
            >
              <v-icon start size="18">mdi-delete</v-icon>
              批量卸载
              <span class="ml-1">({{ uninstallablePlugins.length }})</span>
            </v-btn>
          </div>
        </div>

        <v-spacer />

        <v-btn
          color="grey"
          size="small"
          variant="text"
          :disabled="isBusy"
          :loading="isBusy"
          @click="emit('clear-selection')"
        >
          取消选择
        </v-btn>
      </v-toolbar>

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
            <v-btn
              color="grey"
              variant="text"
              :disabled="isBusy"
              @click="showUninstallDialog = false"
            >
              取消
            </v-btn>
            <v-btn
              color="error"
              variant="elevated"
              :disabled="isBusy || pendingUninstallNames.length === 0"
              :loading="isBusy"
              @click="confirmBatchUninstall"
            >
              卸载
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>
    </div>
  </v-slide-y-transition>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { PluginSummary } from './types'

const props = defineProps<{
  selectedInactive: PluginSummary[]
  selectedActive: PluginSummary[]
  busy?: boolean
}>()

const emit = defineEmits<{
  (e: 'batch-enable', plugins: PluginSummary[]): void
  (e: 'batch-disable', plugins: PluginSummary[]): void
  (e: 'batch-update', names: string[]): void
  (e: 'batch-uninstall', names: string[]): void
  (e: 'clear-selection'): void
}>()

const isBusy = computed(() => props.busy ?? false)

// 总选中数量
const totalSelected = computed(
  () => (props.selectedInactive?.length ?? 0) + (props.selectedActive?.length ?? 0)
)

// 是否显示（有选中项时显示）
const visible = computed(() => totalSelected.value > 0)

const allSelected = computed<PluginSummary[]>(() => [
  ...(props.selectedInactive ?? []),
  ...(props.selectedActive ?? []),
])

// 可更新的插件（选中的且has_update为true）
const updatablePlugins = computed(() => {
  const all = allSelected.value
  return all.filter((p) => Boolean(p.has_update))
})

// 可卸载的插件（选中的且非系统插件）
const uninstallablePlugins = computed(() => {
  const all = allSelected.value
  return all.filter((p) => !p.reserved)
})

const handleBatchEnable = () => emit('batch-enable', props.selectedInactive ?? [])
const handleBatchDisable = () => emit('batch-disable', props.selectedActive ?? [])
const handleBatchUpdate = () => emit('batch-update', updatablePlugins.value.map((p) => p.name))

const showUninstallDialog = ref(false)
const pendingUninstallNames = ref<string[]>([])

const openUninstallConfirm = () => {
  pendingUninstallNames.value = uninstallablePlugins.value.map((p) => p.name)
  showUninstallDialog.value = true
}

const confirmBatchUninstall = () => {
  const names = pendingUninstallNames.value
  showUninstallDialog.value = false
  if (names.length === 0) return
  emit('batch-uninstall', names)
}
</script>

<style scoped>
.batch-operation-bar {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 1000;
  padding: 12px;
  padding-bottom: calc(12px + env(safe-area-inset-bottom));
  pointer-events: none;
}

.batch-operation-bar__toolbar {
  pointer-events: auto;
  border-radius: 14px;
  box-shadow: 0 -6px 22px rgba(0, 0, 0, 0.12);
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
</style>