<template>
  <div class="chain-management-page">
    <v-container fluid class="pa-0">
      <v-card flat>
        <v-card-title class="d-flex align-center py-3 px-4">
          <span class="text-h4">{{ tm('title') }}</span>
          <v-chip size="small" class="ml-2">{{ totalItems }} {{ tm('chainsCount') }}</v-chip>
          <v-row class="me-4 ms-4" dense>
            <v-text-field
              v-model="searchQuery"
              prepend-inner-icon="mdi-magnify"
              :label="tm('search.placeholder')"
              hide-details
              clearable
              variant="solo-filled"
              flat
              density="compact"
            ></v-text-field>
          </v-row>
          <v-btn color="success" variant="tonal" size="small" class="mr-2" @click="openCreateDialog">
            <v-icon start>mdi-plus</v-icon>
            {{ tm('buttons.create') }}
          </v-btn>
          <v-btn color="secondary" variant="tonal" size="small" class="mr-2" :loading="sortLoading" @click="openSortDialog">
            <v-icon start>mdi-sort</v-icon>
            {{ tm('buttons.sort') }}
          </v-btn>
          <v-btn color="primary" variant="tonal" size="small" :loading="loading" @click="refreshData">
            <v-icon start>mdi-refresh</v-icon>
            {{ tm('buttons.refresh') }}
          </v-btn>
        </v-card-title>

        <v-divider></v-divider>

        <v-card-text class="pa-0">
          <v-data-table-server
            :headers="headers"
            :items="chains"
            :loading="loading"
            :items-length="totalItems"
            v-model:items-per-page="itemsPerPage"
            v-model:page="currentPage"
            @update:options="onTableOptionsUpdate"
            class="elevation-0"
            style="font-size: 12px;"
            item-value="chain_id"
          >
            <template v-slot:item.match_rule="{ item }">
              <div class="d-flex align-center ga-2">
                <v-chip v-if="item.is_default" size="x-small" color="primary" variant="tonal">
                  {{ tm('defaultTag') }}
                </v-chip>
                <span class="font-weight-medium text-caption">{{ formatMatchRule(item.match_rule) }}</span>
              </div>
            </template>

            <template v-slot:item.nodes="{ item }">
              <div class="d-flex flex-wrap ga-1">
                <v-chip
                  v-for="node in enabledNodes(item)"
                  :key="node.uuid || node.name"
                  size="x-small"
                  color="primary"
                  variant="outlined"
                >
                  {{ formatNodeLabel(node) }}
                </v-chip>
                <span v-if="enabledNodes(item).length === 0" class="text-caption text-grey">{{ tm('empty.nodes') }}</span>
              </div>
            </template>

            <template v-slot:item.actions="{ item }">
              <v-btn size="small" variant="tonal" color="primary" class="mr-1" @click="openEditDialog(item)">
                <v-icon>mdi-pencil</v-icon>
              </v-btn>
              <v-btn size="small" variant="tonal" color="error" :disabled="item.is_default" @click="confirmDelete(item)">
                <v-icon>mdi-delete</v-icon>
              </v-btn>
            </template>

            <template v-slot:no-data>
              <div class="text-center py-8">
                <v-icon size="64" color="grey-400">mdi-shuffle-variant</v-icon>
                <div class="text-h6 mt-4 text-grey-600">{{ tm('empty.title') }}</div>
                <div class="text-body-2 text-grey-500">{{ tm('empty.subtitle') }}</div>
                <v-btn color="primary" variant="tonal" class="mt-4" @click="openCreateDialog">
                  <v-icon start>mdi-plus</v-icon>
                  {{ tm('buttons.create') }}
                </v-btn>
              </div>
            </template>
          </v-data-table-server>
        </v-card-text>
      </v-card>
    </v-container>

    <v-dialog v-model="editDialog" max-width="900" scrollable>
      <v-card>
        <v-card-title class="py-3 px-4 d-flex align-center">
          <span>{{ isEditing ? tm('dialogs.editTitle') : tm('dialogs.createTitle') }}</span>
          <v-spacer></v-spacer>
          <v-btn icon="mdi-close" variant="text" @click="closeDialog"></v-btn>
        </v-card-title>
        <v-divider></v-divider>
        <v-card-text class="pa-4">
          <v-row dense>
            <v-col cols="12">
              <div v-if="isDefaultChain" class="text-caption text-grey">
                {{ tm('defaultHint') }}
              </div>
              <RuleEditor
                v-else
                v-model="editingChain.match_rule"
                :modalities="availableOptions.available_modalities"
              />
            </v-col>
            <v-col cols="12">
              <v-select
                v-model="editingChain.config_id"
                :items="configOptions"
                item-title="label"
                item-value="value"
                :label="tm('fields.config')"
                variant="outlined"
                :disabled="isDefaultChain"
              ></v-select>
            </v-col>
            <v-col cols="12">
              <v-switch
                v-model="editingChain.enabled"
                :label="tm('fields.enabled')"
                color="primary"
              ></v-switch>
            </v-col>
          </v-row>

          <v-divider class="my-4"></v-divider>

          <div class="d-flex align-center justify-space-between mb-3">
            <div class="section-title mb-0">{{ tm('sections.nodes') }}</div>
            <v-btn size="small" color="primary" variant="tonal" @click="openAddNodeDialog">
              <v-icon start>mdi-plus</v-icon>
              {{ tm('buttons.addNode') }}
            </v-btn>
          </div>

            <div class="node-list">
              <div
              v-for="(node, index) in editingChain.nodes"
              :key="node.uuid || index"
              class="node-item"
              draggable="true"
              @dragstart="onNodeDragStart(index)"
              @dragover.prevent
              @drop="onNodeDrop(index)"
            >
              <div class="d-flex align-center ga-2 mb-1">
                <v-icon size="small" class="drag-handle">mdi-drag</v-icon>
                <span class="font-weight-medium">{{ formatNodeLabel(node) }}</span>
                <v-spacer></v-spacer>
                <v-btn size="small" color="primary" variant="text" icon @click="openNodeConfigDialog(node)">
                  <v-icon size="small">mdi-cog</v-icon>
                </v-btn>
                <v-btn size="small" color="error" variant="text" icon @click="removeNode(index)">
                  <v-icon size="small">mdi-delete</v-icon>
                </v-btn>
              </div>
            </div>
            <div v-if="editingChain.nodes.length === 0" class="text-center py-4 text-grey">
              {{ tm('empty.nodes') }}
            </div>
          </div>

          <v-divider class="my-4"></v-divider>

          <div class="section-title">{{ tm('sections.pluginFilter') }}</div>
          <v-row dense>
            <v-col cols="12" md="4">
              <v-select
                v-model="editingChain.plugin_filter.mode"
                :items="pluginFilterModeOptions"
                item-title="label"
                item-value="value"
                :label="tm('fields.pluginFilterMode')"
                variant="outlined"
              ></v-select>
            </v-col>
            <v-col cols="12" md="8">
              <v-select
                v-model="editingChain.plugin_filter.plugins"
                :items="availablePluginsForFilter"
                item-title="label"
                item-value="value"
                :label="tm('fields.pluginList')"
                multiple
                chips
                closable-chips
                clearable
                variant="outlined"
                :disabled="isPluginFilterListDisabled"
              ></v-select>
            </v-col>
          </v-row>
          <div class="text-caption text-grey mt-1">
            {{ pluginFilterHint }}
          </div>

        </v-card-text>
        <v-divider></v-divider>
        <v-card-actions class="px-4 py-3">
          <v-spacer></v-spacer>
          <v-btn variant="text" @click="closeDialog">{{ tm('buttons.cancel') }}</v-btn>
          <v-btn color="primary" variant="tonal" :loading="saving" @click="saveChain">
            {{ tm('buttons.save') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="deleteDialog" max-width="420">
      <v-card>
        <v-card-title>{{ tm('dialogs.deleteTitle') }}</v-card-title>
        <v-card-text>{{ tm('dialogs.deleteConfirm') }}</v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn variant="text" @click="deleteDialog = false">{{ tm('buttons.cancel') }}</v-btn>
          <v-btn color="error" variant="tonal" :loading="deleting" @click="deleteChain">
            {{ tm('buttons.delete') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="addNodeDialog" max-width="500">
      <v-card>
        <v-card-title>{{ tm('dialogs.addNodeTitle') }}</v-card-title>
        <v-card-text>
          <v-select
            v-model="selectedNodeToAdd"
            :items="availableNodesToAdd"
            item-title="label"
            item-value="value"
            :label="tm('fields.selectNode')"
            variant="outlined"
          ></v-select>
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn variant="text" @click="addNodeDialog = false">{{ tm('buttons.cancel') }}</v-btn>
          <v-btn color="primary" variant="tonal" @click="addNode" :disabled="!selectedNodeToAdd">
            {{ tm('buttons.add') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="nodeConfigDialog" max-width="900" scrollable>
      <v-card>
        <v-card-title class="py-3 px-4 d-flex align-center">
          <span>{{ tm('dialogs.nodeConfigTitle') }} - {{ nodeConfigTitle }}</span>
          <v-spacer></v-spacer>
          <v-btn icon="mdi-close" variant="text" @click="closeNodeConfigDialog"></v-btn>
        </v-card-title>
        <v-divider></v-divider>
        <v-card-text class="pa-4">
          <v-progress-linear
            v-if="nodeConfigLoading"
            indeterminate
            color="primary"
            class="mb-4"
          ></v-progress-linear>
          <div v-else>
            <AstrBotConfig
              v-if="hasNodeSchema"
              :metadata="nodeConfigMetadata"
              :iterable="nodeConfigData"
              metadataKey="node_config"
              :plugin-name="nodeConfigTarget?.name || ''"
              :is-editing="true"
            />
            <div v-else>
              <v-alert type="info" variant="tonal" class="mb-4">
                {{ tm('messages.nodeConfigRawHint') }}
              </v-alert>
              <v-textarea
                v-model="nodeConfigRaw"
                variant="outlined"
                rows="10"
                auto-grow
                hide-details
              ></v-textarea>
            </div>
          </div>
        </v-card-text>
        <v-divider></v-divider>
        <v-card-actions class="px-4 py-3">
          <v-spacer></v-spacer>
          <v-btn variant="text" @click="closeNodeConfigDialog">{{ tm('buttons.cancel') }}</v-btn>
          <v-btn color="primary" variant="tonal" :loading="nodeConfigSaving" @click="saveNodeConfig">
            {{ tm('buttons.save') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="sortDialog" max-width="700" scrollable>
      <v-card>
        <v-card-title class="py-3 px-4 d-flex align-center">
          <span>{{ tm('dialogs.sortTitle') }}</span>
          <v-spacer></v-spacer>
          <v-btn icon="mdi-close" variant="text" @click="closeSortDialog"></v-btn>
        </v-card-title>
        <v-divider></v-divider>
        <v-card-text class="pa-4">
          <div class="text-caption text-grey mb-3">{{ tm('dialogs.sortHint') }}</div>
          <v-progress-linear
            v-if="sortLoading"
            indeterminate
            color="primary"
            class="mb-4"
          ></v-progress-linear>
          <div v-else class="sort-list">
            <div
              v-for="(chain, index) in sortChains"
              :key="chain.chain_id"
              class="sort-item"
              draggable="true"
              @dragstart="onChainDragStart(index)"
              @dragover.prevent
              @drop="onChainDrop(index)"
            >
              <v-icon size="small" class="drag-handle">mdi-drag</v-icon>
              <div class="d-flex flex-column">
                <span class="font-weight-medium">{{ formatMatchRule(chain.match_rule) }}</span>
                <span class="text-caption text-grey">{{ chain.chain_id }}</span>
              </div>
            </div>
            <div class="sort-item sort-item-disabled">
              <v-icon size="small" class="drag-handle">mdi-drag</v-icon>
              <div class="d-flex flex-column">
                <span class="font-weight-medium">{{ tm('defaultTag') }}</span>
                <span class="text-caption text-grey">{{ tm('dialogs.sortDefaultHint') }}</span>
              </div>
            </div>
            <div v-if="sortChains.length === 0" class="text-center py-6 text-grey">
              {{ tm('empty.title') }}
            </div>
          </div>
        </v-card-text>
        <v-divider></v-divider>
        <v-card-actions class="px-4 py-3">
          <v-spacer></v-spacer>
          <v-btn variant="text" @click="closeSortDialog">{{ tm('buttons.cancel') }}</v-btn>
          <v-btn color="primary" variant="tonal" :loading="sortSaving" @click="saveSortOrder">
            {{ tm('buttons.save') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-snackbar v-model="snackbar.show" :color="snackbar.color" :timeout="3000" location="top">
      {{ snackbar.message }}
    </v-snackbar>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import axios from 'axios'
import { useModuleI18n } from '@/i18n/composables'
import RuleEditor from '@/components/RuleEditor.vue'
import AstrBotConfig from '@/components/shared/AstrBotConfig.vue'

const { tm } = useModuleI18n('features/chain-management')

const loading = ref(false)
const saving = ref(false)
const deleting = ref(false)

const searchQuery = ref('')
const itemsPerPage = ref(10)
const currentPage = ref(1)
const totalItems = ref(0)
const chains = ref([])

const editDialog = ref(false)
const deleteDialog = ref(false)
const addNodeDialog = ref(false)
const nodeConfigDialog = ref(false)
const sortDialog = ref(false)

const deleteTarget = ref(null)
const selectedNodeToAdd = ref('')
const sortChains = ref([])

const availableOptions = ref({
  available_plugins: [],
  available_nodes: [],
  default_nodes: [],
  available_configs: [],
  available_modalities: []
})

const snackbar = ref({
  show: false,
  message: '',
  color: 'success'
})

const headers = computed(() => [
  { title: tm('table.matchRule'), key: 'match_rule', sortable: false },
  { title: tm('table.nodes'), key: 'nodes', sortable: false },
  { title: tm('table.actions'), key: 'actions', sortable: false }
])


const editingChain = ref(buildEmptyChain())
const isEditing = computed(() => Boolean(editingChain.value.chain_id))
const isDefaultChain = computed(() => Boolean(editingChain.value.is_default))

const nodeConfigTarget = ref(null)
const nodeConfigData = ref({})
const nodeConfigSchema = ref({})
const nodeConfigRaw = ref('')
const nodeConfigLoading = ref(false)
const nodeConfigSaving = ref(false)
const sortLoading = ref(false)
const sortSaving = ref(false)

const hasNodeSchema = computed(() => Object.keys(nodeConfigSchema.value || {}).length > 0)
const nodeConfigMetadata = computed(() => {
  if (!hasNodeSchema.value) return null
  return {
    node_config: {
      description: tm('dialogs.nodeConfigTitle'),
      type: 'object',
      items: nodeConfigSchema.value
    }
  }
})
const nodeConfigTitle = computed(() => {
  if (!nodeConfigTarget.value) return ''
  return formatNodeLabel(nodeConfigTarget.value)
})

const availableNodeMap = computed(() => {
  const map = new Map()
  for (const node of availableOptions.value.available_nodes || []) {
    map.set(node.name, node)
  }
  return map
})


const configOptions = computed(() => [
  { label: tm('providers.followDefault'), value: 'default' },
  ...availableOptions.value.available_configs.filter(c => c.id !== 'default').map(c => ({
    label: c.name,
    value: c.id
  }))
])

const pluginFilterModeOptions = computed(() => [
  { label: tm('pluginConfig.inherit'), value: 'inherit' },
  { label: tm('pluginConfig.blacklist'), value: 'blacklist' },
  { label: tm('pluginConfig.whitelist'), value: 'whitelist' },
  { label: tm('pluginConfig.noRestriction'), value: 'none' }
])

const pluginFilterHint = computed(() => {
  const mode = editingChain.value?.plugin_filter?.mode
  if (mode === 'inherit') return tm('pluginConfig.inheritHint')
  if (mode === 'none') return tm('pluginConfig.noRestrictionHint')
  if (mode === 'whitelist') return tm('pluginConfig.whitelistHint')
  return tm('pluginConfig.blacklistHint')
})

const isPluginFilterListDisabled = computed(() => {
  const mode = editingChain.value?.plugin_filter?.mode
  return mode === 'inherit' || mode === 'none'
})

const availablePluginsForFilter = computed(() => {
  return (availableOptions.value.available_plugins || []).map(p => ({
    label: p.display_name || p.name,
    value: p.name
  }))
})

const availableNodesToAdd = computed(() => {
  return (availableOptions.value.available_nodes || [])
    .map(node => ({
      label: node.display_name || node.name,
      value: node.name
    }))
})

function generateNodeUuid() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `${Date.now().toString(16)}-${Math.random().toString(16).slice(2, 10)}`
}

function createNodeEntry(name, uuid) {
  return {
    name,
    uuid: uuid || generateNodeUuid()
  }
}

function coerceNodes(nodes) {
  if (!Array.isArray(nodes)) return []
  return nodes
    .map(node => {
      if (typeof node === 'string') {
        return createNodeEntry(node)
      }
      if (node && typeof node === 'object') {
        const name = node.name || node.node_name || node.node
        if (!name) return null
        return createNodeEntry(name, node.uuid || node.id)
      }
      return null
    })
    .filter(Boolean)
}

function cloneNodes(nodes) {
  return coerceNodes(nodes).map(node => ({ ...node }))
}

function getNodeDisplayName(node) {
  const name = typeof node === 'string' ? node : node?.name
  const info = availableNodeMap.value.get(name)
  return info?.display_name || name || ''
}

function formatNodeLabel(node) {
  const name = getNodeDisplayName(node)
  const uuid = typeof node === 'string' ? '' : node?.uuid
  const shortId = uuid ? uuid.slice(0, 8) : ''
  return shortId ? `${name} (${shortId})` : name
}

function buildEmptyChain() {
  return {
    chain_id: '',
    match_rule: null,
    config_id: 'default',
    enabled: true,
    nodes: [],
    llm_enabled: true,
    plugin_filter: { mode: 'inherit', plugins: [] },
    nodes_is_default: false,
    is_default: false
  }
}

function normalizeChainPayload(chain) {
  const payload = JSON.parse(JSON.stringify(chain))
  delete payload.name
  delete payload.priority
  delete payload.is_default
  if (payload.nodes_is_default) {
    payload.nodes = null
  } else if (payload.nodes) {
    payload.nodes = coerceNodes(payload.nodes).map(node => ({
      name: node.name,
      uuid: node.uuid
    }))
  }
  delete payload.nodes_is_default
  if (!payload.plugin_filter || payload.plugin_filter.mode === 'inherit') {
    payload.plugin_filter = null
  } else {
    payload.plugin_filter = {
      mode: payload.plugin_filter.mode || 'blacklist',
      plugins: payload.plugin_filter.plugins || []
    }
  }
  if (!payload.config_id || payload.config_id === 'default') {
    payload.config_id = null
  }
  return payload
}

function enabledNodes(chain) {
  if (chain.nodes == null) {
    return cloneNodes(availableOptions.value.default_nodes || [])
  }
  return coerceNodes(chain.nodes || [])
}

function formatMatchRule(rule) {
  if (!rule) return '*'
  return formatRuleNode(rule)
}

function formatRuleNode(node) {
  if (!node) return '*'

  if (node.type === 'condition') {
    const cond = node.condition || {}
    const type = cond.type || 'umo'
    const value = cond.value || ''
    const operator = cond.operator || 'include'
    const prefix = operator === 'exclude' ? '!' : ''
    if (type === 'umo') return prefix + (value || '*')
    if (type === 'modality') return `${prefix}[${value}]`
    if (type === 'text_regex') return `${prefix}/${value}/`
    return prefix + value
  }

  if (node.type === 'and') {
    const parts = (node.children || []).map(formatRuleNode)
    return parts.length > 1 ? `(${parts.join(' AND ')})` : parts[0] || '*'
  }

  if (node.type === 'or') {
    const parts = (node.children || []).map(formatRuleNode)
    return parts.length > 1 ? `(${parts.join(' OR ')})` : parts[0] || '*'
  }

  if (node.type === 'not') {
    const child = (node.children || [])[0]
    return `NOT ${formatRuleNode(child)}`
  }

  return '*'
}

function showMessage(message, color = 'success') {
  snackbar.value = { show: true, message, color }
}

async function loadChains() {
  loading.value = true
  try {
    const response = await axios.get('/api/chain/list', {
      params: {
        page: currentPage.value,
        page_size: itemsPerPage.value,
        search: searchQuery.value
      }
    })
    if (response.data.status === 'ok') {
      chains.value = response.data.data.chains || []
      totalItems.value = response.data.data.total || 0
    } else {
      showMessage(response.data.message || tm('messages.loadError'), 'error')
    }
  } catch (error) {
    showMessage(error.response?.data?.message || tm('messages.loadError'), 'error')
  } finally {
    loading.value = false
  }
}

async function loadOptions() {
  try {
    const response = await axios.get('/api/chain/available-options')
    if (response.data.status === 'ok') {
      availableOptions.value = response.data.data || availableOptions.value
    }
  } catch (error) {
    showMessage(error.response?.data?.message || tm('messages.optionsError'), 'error')
  }
}

function onTableOptionsUpdate() {
  loadChains()
}

function refreshData() {
  loadChains()
}

function openCreateDialog() {
  editingChain.value = buildEmptyChain()
  editDialog.value = true
}

function openEditDialog(chain) {
  const cloned = JSON.parse(JSON.stringify(chain))
  const nodesMissing = cloned.nodes == null
  editingChain.value = {
    ...cloned,
    nodes: nodesMissing ? cloneNodes(availableOptions.value.default_nodes || []) : cloneNodes(cloned.nodes || []),
    nodes_is_default: nodesMissing
  }
  editingChain.value.is_default = Boolean(cloned.is_default)
  editingChain.value.config_id = editingChain.value.config_id || 'default'
  if (!editingChain.value.plugin_filter || typeof editingChain.value.plugin_filter !== 'object') {
    editingChain.value.plugin_filter = { mode: 'inherit', plugins: [] }
  } else {
    const mode = editingChain.value.plugin_filter.mode || 'blacklist'
    editingChain.value.plugin_filter = {
      mode,
      plugins: editingChain.value.plugin_filter.plugins || []
    }
  }
  editDialog.value = true
}

function closeDialog() {
  editDialog.value = false
}

const draggingNodeIndex = ref(null)

function onNodeDragStart(index) {
  draggingNodeIndex.value = index
}

function onNodeDrop(targetIndex) {
  const fromIndex = draggingNodeIndex.value
  if (fromIndex === null || fromIndex === targetIndex) {
    draggingNodeIndex.value = null
    return
  }
  const nodes = [...editingChain.value.nodes]
  const [moved] = nodes.splice(fromIndex, 1)
  nodes.splice(targetIndex, 0, moved)
  editingChain.value.nodes = nodes
  editingChain.value.nodes_is_default = false
  draggingNodeIndex.value = null
}

function openAddNodeDialog() {
  selectedNodeToAdd.value = ''
  addNodeDialog.value = true
}

async function openNodeConfigDialog(node) {
  if (!editingChain.value.chain_id) {
    showMessage(tm('messages.nodeConfigNeedSave'), 'error')
    return
  }
  nodeConfigTarget.value = node
  nodeConfigData.value = {}
  nodeConfigRaw.value = ''
  nodeConfigSchema.value = availableNodeMap.value.get(node.name)?.schema || {}
  nodeConfigLoading.value = true
  nodeConfigDialog.value = true
  try {
    const response = await axios.get('/api/chain/node-config', {
      params: {
        chain_id: editingChain.value.chain_id,
        node_name: node.name,
        node_uuid: node.uuid
      }
    })
    if (response.data.status === 'ok') {
      nodeConfigData.value = response.data.data.config || {}
      if (!hasNodeSchema.value && response.data.data.schema) {
        nodeConfigSchema.value = response.data.data.schema || {}
      }
      nodeConfigRaw.value = JSON.stringify(nodeConfigData.value || {}, null, 2)
    } else {
      showMessage(response.data.message || tm('messages.nodeConfigLoadError'), 'error')
    }
  } catch (error) {
    showMessage(error.response?.data?.message || tm('messages.nodeConfigLoadError'), 'error')
  } finally {
    nodeConfigLoading.value = false
  }
}

function closeNodeConfigDialog() {
  nodeConfigDialog.value = false
}

async function saveNodeConfig() {
  if (!nodeConfigTarget.value) return
  let payloadConfig = nodeConfigData.value || {}
  if (!hasNodeSchema.value) {
    try {
      payloadConfig = JSON.parse(nodeConfigRaw.value || '{}')
      nodeConfigData.value = payloadConfig
    } catch (error) {
      showMessage(tm('messages.nodeConfigJsonError'), 'error')
      return
    }
  }
  nodeConfigSaving.value = true
  try {
    const response = await axios.post('/api/chain/node-config/update', {
      chain_id: editingChain.value.chain_id,
      node_name: nodeConfigTarget.value.name,
      node_uuid: nodeConfigTarget.value.uuid,
      config: payloadConfig
    })
    if (response.data.status === 'ok') {
      showMessage(tm('messages.saveSuccess'))
      nodeConfigDialog.value = false
    } else {
      showMessage(response.data.message || tm('messages.nodeConfigSaveError'), 'error')
    }
  } catch (error) {
    showMessage(error.response?.data?.message || tm('messages.nodeConfigSaveError'), 'error')
  } finally {
    nodeConfigSaving.value = false
  }
}

function addNode() {
  if (!selectedNodeToAdd.value) return
  if (!editingChain.value.nodes) {
    editingChain.value.nodes = []
  }
  editingChain.value.nodes.push(createNodeEntry(selectedNodeToAdd.value))
  editingChain.value.nodes_is_default = false
  addNodeDialog.value = false
  selectedNodeToAdd.value = ''
}

function removeNode(index) {
  editingChain.value.nodes.splice(index, 1)
  editingChain.value.nodes_is_default = false
}

async function fetchAllChains() {
  const pageSize = 100
  let page = 1
  let total = 0
  const results = []

  while (true) {
    const response = await axios.get('/api/chain/list', {
      params: {
        page,
        page_size: pageSize,
        search: ''
      }
    })
    if (response.data.status !== 'ok') {
      throw new Error(response.data.message || tm('messages.sortLoadError'))
    }
    const data = response.data.data || {}
    const chainsChunk = data.chains || []
    total = data.total || chainsChunk.length
    results.push(...chainsChunk)
    if (results.length >= total || chainsChunk.length === 0) {
      break
    }
    page += 1
  }

  return results
}

async function openSortDialog() {
  sortDialog.value = true
  sortLoading.value = true
  sortChains.value = []
  try {
    const allChains = await fetchAllChains()
    sortChains.value = allChains.filter(chain => !chain.is_default)
  } catch (error) {
    showMessage(error.message || tm('messages.sortLoadError'), 'error')
  } finally {
    sortLoading.value = false
  }
}

function closeSortDialog() {
  sortDialog.value = false
}

const draggingChainIndex = ref(null)

function onChainDragStart(index) {
  draggingChainIndex.value = index
}

function onChainDrop(targetIndex) {
  const fromIndex = draggingChainIndex.value
  if (fromIndex === null || fromIndex === targetIndex) {
    draggingChainIndex.value = null
    return
  }
  const chains = [...sortChains.value]
  const [moved] = chains.splice(fromIndex, 1)
  chains.splice(targetIndex, 0, moved)
  sortChains.value = chains
  draggingChainIndex.value = null
}

async function saveSortOrder() {
  if (!sortChains.value.length) {
    sortDialog.value = false
    return
  }
  sortSaving.value = true
  try {
    const response = await axios.post('/api/chain/reorder', {
      chain_ids: sortChains.value.map(chain => chain.chain_id)
    })
    if (response.data.status === 'ok') {
      showMessage(tm('messages.sortSuccess'))
      sortDialog.value = false
      await loadChains()
    } else {
      showMessage(response.data.message || tm('messages.sortError'), 'error')
    }
  } catch (error) {
    showMessage(error.response?.data?.message || tm('messages.sortError'), 'error')
  } finally {
    sortSaving.value = false
  }
}

async function saveChain() {
  saving.value = true
  try {
    const payload = normalizeChainPayload(editingChain.value)
    const url = payload.chain_id ? '/api/chain/update' : '/api/chain/create'
    const response = await axios.post(url, payload)
    if (response.data.status === 'ok') {
      showMessage(tm('messages.saveSuccess'))
      editDialog.value = false
      await loadChains()
    } else {
      showMessage(response.data.message || tm('messages.saveError'), 'error')
    }
  } catch (error) {
    showMessage(error.response?.data?.message || tm('messages.saveError'), 'error')
  } finally {
    saving.value = false
  }
}

function confirmDelete(chain) {
  deleteTarget.value = chain
  deleteDialog.value = true
}

async function deleteChain() {
  if (!deleteTarget.value) return
  deleting.value = true
  try {
    const response = await axios.post('/api/chain/delete', { chain_id: deleteTarget.value.chain_id })
    if (response.data.status === 'ok') {
      showMessage(tm('messages.deleteSuccess'))
      deleteDialog.value = false
      deleteTarget.value = null
      await loadChains()
    } else {
      showMessage(response.data.message || tm('messages.deleteError'), 'error')
    }
  } catch (error) {
    showMessage(error.response?.data?.message || tm('messages.deleteError'), 'error')
  } finally {
    deleting.value = false
  }
}

let searchTimer = null
watch(searchQuery, () => {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    currentPage.value = 1
    loadChains()
  }, 300)
})

watch(
  () => editingChain.value?.plugin_filter?.mode,
  mode => {
    if (!editingChain.value?.plugin_filter) return
    if (mode === 'inherit' || mode === 'none') {
      editingChain.value.plugin_filter.plugins = []
    }
  }
)

onMounted(async () => {
  await Promise.all([loadChains(), loadOptions()])
})
</script>

<style scoped>
.chain-management-page {
  padding: 20px;
  padding-top: 8px;
  padding-bottom: 40px;
}

.section-title {
  font-weight: 600;
  margin-bottom: 12px;
}

.node-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.node-item {
  padding: 12px;
  border: 1px solid rgba(0, 0, 0, 0.08);
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.01);
}

.node-item:hover {
  background: rgba(0, 0, 0, 0.02);
}

.drag-handle {
  cursor: grab;
}

.sort-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.sort-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  border: 1px solid rgba(0, 0, 0, 0.08);
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.01);
}

.sort-item:hover {
  background: rgba(0, 0, 0, 0.02);
}

.sort-item-disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

</style>
