<script setup lang="ts">
import { computed } from 'vue'
import { useModuleI18n } from '@/i18n/composables'
import ExtensionCard from '@/components/shared/ExtensionCard.vue'
import type { PluginSummary } from './types'

const props = defineProps<{
  plugins: PluginSummary[]
  loading?: boolean
  showReserved: boolean
  isListView: boolean
}>()

type UninstallOptions = { deleteConfig?: boolean; deleteData?: boolean }

const emit = defineEmits<{
  (e: 'update:isListView', value: boolean): void
  (e: 'action-enable', plugin: PluginSummary): void
  (e: 'action-disable', plugin: PluginSummary): void
  (e: 'action-reload', name: string): void
  (e: 'action-update', name: string): void
  (e: 'action-uninstall', name: string, options?: UninstallOptions): void
  (e: 'action-configure', plugin: PluginSummary): void
  (e: 'action-view-handlers', plugin: PluginSummary): void
  (e: 'action-view-readme', plugin: PluginSummary): void
  (e: 'view-changelog', plugin: PluginSummary): void
  (e: 'action-open-repo', url: string): void
}>()

const { tm } = useModuleI18n('features/extension')

const viewMode = computed<boolean>({
  get: () => props.isListView,
  set: (val) => emit('update:isListView', Boolean(val))
})

const safePlugins = computed<PluginSummary[]>(() => (Array.isArray(props.plugins) ? props.plugins : []))

const pluginHeaders = computed(() => [
  { title: tm('table.headers.name'), key: 'name', width: '200px' },
  { title: tm('table.headers.description'), key: 'desc', maxWidth: '250px' },
  { title: tm('table.headers.version'), key: 'version', width: '100px' },
  { title: tm('table.headers.author'), key: 'author', width: '100px' },
  { title: tm('table.headers.status'), key: 'activated', width: '100px' },
  { title: '', key: 'repo', sortable: false, width: '56px' },
  { title: tm('table.headers.actions'), key: 'actions', sortable: false, width: '260px' }
])

const handleToggleView = (isList: boolean) => {
  if (viewMode.value === isList) return
  viewMode.value = isList
}

const handleToggleActivation = (plugin: PluginSummary) => {
  if (plugin.activated) {
    emit('action-disable', plugin)
  } else {
    emit('action-enable', plugin)
  }
}

const handleUninstallFromCard = (plugin: PluginSummary, options?: UninstallOptions) => {
  emit('action-uninstall', plugin.name, options)
}

const handleOpenRepo = (url: string | null | undefined) => {
  if (!url) return
  emit('action-open-repo', url)
}

function toPlugin(item: unknown): PluginSummary {
  const maybeWrapped = item as any
  const raw = maybeWrapped?.raw
  return (raw ?? item) as PluginSummary
}
</script>

<template>
  <div class="legacy-installed-view">
    <v-row class="mb-4">
      <v-col cols="12" class="d-flex align-center flex-wrap ga-2">
        <v-btn-group variant="outlined" density="comfortable" color="primary">
          <v-btn
            @click="handleToggleView(false)"
            :color="!viewMode ? 'primary' : undefined"
            :variant="!viewMode ? 'flat' : 'outlined'"
            aria-label="card-view"
          >
            <v-icon>mdi-view-grid</v-icon>
          </v-btn>
          <v-btn
            @click="handleToggleView(true)"
            :color="viewMode ? 'primary' : undefined"
            :variant="viewMode ? 'flat' : 'outlined'"
            aria-label="list-view"
          >
            <v-icon>mdi-view-list</v-icon>
          </v-btn>
        </v-btn-group>

        <v-spacer />

        <v-chip size="small" variant="tonal" color="primary">
          {{ showReserved ? tm('buttons.showSystemPlugins') : tm('buttons.hideSystemPlugins') }}
        </v-chip>
      </v-col>
    </v-row>

    <v-fade-transition hide-on-leave>
      <div v-if="viewMode">
        <v-card class="rounded-lg overflow-hidden elevation-1">
          <v-data-table
            :headers="pluginHeaders"
            :items="safePlugins"
            :loading="loading"
            item-key="name"
            hover
          >
            <template #loader>
              <v-row class="py-8 d-flex align-center justify-center">
                <v-progress-circular indeterminate color="primary" />
                <span class="ml-2">{{ tm('status.loading') }}</span>
              </v-row>
            </template>

            <template #item.name="{ item }">
              <div class="d-flex align-center py-2">
                <div>
                  <div class="text-subtitle-1 font-weight-medium">{{ toPlugin(item).name }}</div>
                  <div v-if="toPlugin(item).reserved" class="d-flex align-center mt-1">
                    <v-chip color="primary" size="x-small" class="font-weight-medium">
                      {{ tm('status.system') }}
                    </v-chip>
                  </div>
                </div>
              </div>
            </template>

            <template #item.desc="{ item }">
              <div class="text-body-2 text-medium-emphasis">{{ toPlugin(item).desc }}</div>
            </template>

            <template #item.version="{ item }">
              <div class="d-flex align-center">
                <span class="text-body-2">{{ toPlugin(item).version }}</span>
                <v-icon v-if="toPlugin(item).has_update" color="warning" size="small" class="ml-1">mdi-alert</v-icon>
                <v-tooltip v-if="toPlugin(item).has_update" activator="parent">
                  <span>{{ tm('messages.hasUpdate') }} {{ toPlugin(item).online_version }}</span>
                </v-tooltip>
              </div>
            </template>

            <template #item.author="{ item }">
              <div class="text-body-2">{{ toPlugin(item).author }}</div>
            </template>

            <template #item.activated="{ item }">
              <v-chip
                :color="toPlugin(item).activated ? 'success' : 'error'"
                size="small"
                class="font-weight-medium"
                :variant="toPlugin(item).activated ? 'flat' : 'outlined'"
              >
                {{ toPlugin(item).activated ? tm('status.enabled') : tm('status.disabled') }}
              </v-chip>
            </template>

            <template #item.repo="{ item }">
              <v-btn
                v-if="toPlugin(item).repo"
                icon
                size="small"
                variant="text"
                @click.stop="handleOpenRepo(toPlugin(item).repo)"
              >
                <v-icon size="20">mdi-github</v-icon>
                <v-tooltip activator="parent" location="top">打开仓库</v-tooltip>
              </v-btn>
            </template>

            <template #item.actions="{ item }">
              <div class="d-flex align-center">
                <v-btn-group density="comfortable" variant="text" color="primary">
                  <v-btn
                    v-if="!toPlugin(item).activated"
                    icon
                    size="small"
                    color="success"
                    @click.stop="emit('action-enable', toPlugin(item))"
                  >
                    <v-icon>mdi-play</v-icon>
                    <v-tooltip activator="parent" location="top">{{ tm('tooltips.enable') }}</v-tooltip>
                  </v-btn>
                  <v-btn
                    v-else
                    icon
                    size="small"
                    color="error"
                    @click.stop="emit('action-disable', toPlugin(item))"
                  >
                    <v-icon>mdi-pause</v-icon>
                    <v-tooltip activator="parent" location="top">{{ tm('tooltips.disable') }}</v-tooltip>
                  </v-btn>

                  <v-btn icon size="small" color="info" @click.stop="emit('action-reload', toPlugin(item).name)">
                    <v-icon>mdi-refresh</v-icon>
                    <v-tooltip activator="parent" location="top">{{ tm('tooltips.reload') }}</v-tooltip>
                  </v-btn>

                  <v-btn icon size="small" @click.stop="emit('action-configure', toPlugin(item))">
                    <v-icon>mdi-cog</v-icon>
                    <v-tooltip activator="parent" location="top">{{ tm('tooltips.configure') }}</v-tooltip>
                  </v-btn>

                  <v-btn icon size="small" @click.stop="emit('action-view-handlers', toPlugin(item))">
                    <v-icon>mdi-information</v-icon>
                    <v-tooltip activator="parent" location="top">{{ tm('tooltips.viewInfo') }}</v-tooltip>
                  </v-btn>

                  <v-btn v-if="toPlugin(item).repo" icon size="small" @click.stop="emit('action-view-readme', toPlugin(item))">
                    <v-icon>mdi-book-open-page-variant</v-icon>
                    <v-tooltip activator="parent" location="top">{{ tm('tooltips.viewDocs') }}</v-tooltip>
                  </v-btn>

                  <v-btn
                    v-if="toPlugin(item).has_update"
                    icon
                    size="small"
                    color="warning"
                    @click.stop="emit('action-update', toPlugin(item).name)"
                  >
                    <v-icon>mdi-update</v-icon>
                    <v-tooltip activator="parent" location="top">{{ tm('tooltips.update') }}</v-tooltip>
                  </v-btn>

                  <v-btn
                    icon
                    size="small"
                    color="error"
                    :disabled="toPlugin(item).reserved"
                    @click.stop="emit('action-uninstall', toPlugin(item).name)"
                  >
                    <v-icon>mdi-delete</v-icon>
                    <v-tooltip activator="parent" location="top">{{ tm('tooltips.uninstall') }}</v-tooltip>
                  </v-btn>
                </v-btn-group>
              </div>
            </template>

            <template #no-data>
              <div class="text-center pa-8">
                <v-icon size="64" color="info" class="mb-4">mdi-puzzle-outline</v-icon>
                <div class="text-h5 mb-2">{{ tm('empty.noPlugins') }}</div>
                <div class="text-body-1 mb-4">{{ tm('empty.noPluginsDesc') }}</div>
              </div>
            </template>
          </v-data-table>
        </v-card>
      </div>

      <div v-else>
        <v-row v-if="loading" class="text-center">
          <v-col cols="12" class="pa-8 d-flex align-center justify-center ga-3">
            <v-progress-circular indeterminate color="primary" />
            <span class="text-body-2 text-medium-emphasis">{{ tm('status.loading') }}</span>
          </v-col>
        </v-row>

        <v-row v-else-if="safePlugins.length === 0" class="text-center">
          <v-col cols="12" class="pa-2">
            <v-icon size="64" color="info" class="mb-4">mdi-puzzle-outline</v-icon>
            <div class="text-h5 mb-2">{{ tm('empty.noPlugins') }}</div>
            <div class="text-body-1 mb-4">{{ tm('empty.noPluginsDesc') }}</div>
          </v-col>
        </v-row>

        <v-row v-else>
          <v-col
            cols="12"
            md="6"
            lg="4"
            v-for="extension in safePlugins"
            :key="extension.name"
            class="pb-2"
          >
            <div class="legacy-installed-view__card-wrapper">
              <v-btn
                v-if="extension.repo"
                class="legacy-installed-view__repo"
                icon
                size="small"
                variant="text"
                @click.stop="handleOpenRepo(extension.repo)"
              >
                <v-icon size="20">mdi-github</v-icon>
                <v-tooltip activator="parent" location="top">打开仓库</v-tooltip>
              </v-btn>

              <ExtensionCard
                :extension="extension"
                class="rounded-lg"
                style="background-color: rgb(var(--v-theme-mcpCardBg));"
                @configure="emit('action-configure', extension)"
                @uninstall="(ext, options) => handleUninstallFromCard(ext, options)"
                @update="emit('action-update', extension.name)"
                @reload="emit('action-reload', extension.name)"
                @toggle-activation="handleToggleActivation(extension)"
                @view-handlers="emit('action-view-handlers', extension)"
                @view-readme="emit('action-view-readme', extension)"
                @view-changelog="emit('view-changelog', extension)"
              />
            </div>
          </v-col>
        </v-row>
      </div>
    </v-fade-transition>
  </div>
</template>

<style scoped>
.legacy-installed-view__card-wrapper {
  position: relative;
}

.legacy-installed-view__repo {
  position: absolute;
  right: 8px;
  top: 8px;
  z-index: 6;
}
</style>