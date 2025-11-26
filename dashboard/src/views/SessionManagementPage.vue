<template>
  <div class="session-management-page">
    <v-container fluid class="pa-0">
      <v-card flat>
        <v-card-title class="d-flex align-center py-3 px-4">
          <span class="text-h4">{{ tm('customRules.title') }}</span>
          <v-chip size="small" class="ml-2">{{ totalItems }} {{ tm('customRules.rulesCount') }}</v-chip>
          <v-row class="me-4 ms-4" dense>
            <v-text-field v-model="searchQuery" prepend-inner-icon="mdi-magnify" :label="tm('search.placeholder')"
              hide-details clearable variant="solo-filled" flat class="me-4" density="compact"></v-text-field>
          </v-row>
          <v-btn v-if="selectedItems.length > 0" color="error" prepend-icon="mdi-delete" variant="tonal"
            @click="confirmBatchDelete" class="mr-2" size="small">
            {{ tm('buttons.batchDelete') }} ({{ selectedItems.length }})
          </v-btn>
          <v-btn color="success" prepend-icon="mdi-plus" variant="tonal" @click="openAddRuleDialog" class="mr-2"
            size="small">
            {{ tm('buttons.addRule') }}
          </v-btn>
          <v-btn color="primary" prepend-icon="mdi-refresh" variant="tonal" @click="refreshData" :loading="loading"
            size="small">
            {{ tm('buttons.refresh') }}
          </v-btn>
        </v-card-title>

        <v-divider></v-divider>

        <v-card-text class="pa-0">
          <v-data-table-server :headers="headers" :items="filteredRulesList" :loading="loading"
            :items-length="totalItems" v-model:items-per-page="itemsPerPage" v-model:page="currentPage"
            @update:options="onTableOptionsUpdate" class="elevation-0" style="font-size: 12px;"
            v-model="selectedItems" show-select item-value="umo" return-object>

            <!-- UMO 信息 -->
            <template v-slot:item.umo_info="{ item }">
              <div>
                <div class="d-flex align-center">
                  <v-chip size="x-small" :color="getPlatformColor(item.platform)" class="mr-2">
                    {{ item.platform || 'unknown' }}
                  </v-chip>
                  <span class="text-truncate" style="max-width: 300px;">{{ item.umo }}</span>
                  <div class="d-flex align-center" v-if="item.rules?.session_service_config?.custom_name || true">
                    <span class="ml-2" style="color: gray; font-size: 10px;" v-if="item.rules?.session_service_config?.custom_name">
                      ({{ item.rules?.session_service_config?.custom_name }})
                    </span>
                    <v-btn icon size="x-small" variant="text" class="ml-1" @click.stop="openQuickEditName(item)">
                      <v-icon size="small" color="grey">mdi-pencil-outline</v-icon>
                      <v-tooltip activator="parent" location="top">{{ tm('buttons.editCustomName') }}</v-tooltip>
                    </v-btn>
                  </div>
                  <v-tooltip location="top">
                    <template v-slot:activator="{ props }">
                      <v-icon v-bind="props" size="small" class="ml-1">mdi-information-outline</v-icon>
                    </template>
                    <div>
                      <p>UMO: {{ item.umo }}</p>
                      <p v-if="item.platform">平台: {{ item.platform }}</p>
                      <p v-if="item.message_type">消息类型: {{ item.message_type }}</p>
                      <p v-if="item.session_id">会话 ID: {{ item.session_id }}</p>
                    </div>
                  </v-tooltip>
                </div>

              </div>
            </template>

            <!-- 规则概览 -->
            <template v-slot:item.rules_overview="{ item }">
              <div class="d-flex flex-wrap ga-1">
                <v-chip v-if="item.rules.session_service_config" size="x-small" color="primary" variant="outlined">
                  {{ tm('customRules.serviceConfig') }}
                </v-chip>
                <v-chip v-if="item.rules.session_plugin_config" size="x-small" color="secondary" variant="outlined">
                  {{ tm('customRules.pluginConfig') }}
                </v-chip>
                <v-chip v-if="item.rules.kb_config" size="x-small" color="info" variant="outlined">
                  {{ tm('customRules.kbConfig') }}
                </v-chip>
                <v-chip v-if="hasProviderConfig(item.rules)" size="x-small" color="warning" variant="outlined">
                  {{ tm('customRules.providerConfig') }}
                </v-chip>
              </div>
            </template>

            <!-- 操作按钮 -->
            <template v-slot:item.actions="{ item }">
              <v-btn size="small" variant="tonal" color="primary" @click="openRuleEditor(item)" class="mr-1">
                <v-icon>mdi-pencil</v-icon>
                <v-tooltip activator="parent" location="top">{{ tm('buttons.editRule') }}</v-tooltip>
              </v-btn>
              <v-btn size="small" variant="tonal" color="error" @click="confirmDeleteRules(item)">
                <v-icon>mdi-delete</v-icon>
                <v-tooltip activator="parent" location="top">{{ tm('buttons.deleteAllRules') }}</v-tooltip>
              </v-btn>
            </template>

            <!-- 空状态 -->
            <template v-slot:no-data>
              <div class="text-center py-8">
                <v-icon size="64" color="grey-400">mdi-file-document-edit-outline</v-icon>
                <div class="text-h6 mt-4 text-grey-600">{{ tm('customRules.noRules') }}</div>
                <div class="text-body-2 text-grey-500">{{ tm('customRules.noRulesDesc') }}</div>
                <v-btn color="primary" variant="tonal" class="mt-4" @click="openAddRuleDialog">
                  <v-icon start>mdi-plus</v-icon>
                  {{ tm('buttons.addRule') }}
                </v-btn>
              </div>
            </template>
          </v-data-table-server>
        </v-card-text>
      </v-card>

      <!-- 添加规则对话框 - 选择 UMO -->
      <v-dialog v-model="addRuleDialog" max-width="600">
        <v-card>
          <v-card-title class="py-3 px-4" style="display: flex; align-items: center;">
            <span>{{ tm('addRule.title') }}</span>
            <v-spacer></v-spacer>
            <v-btn icon variant="text" @click="addRuleDialog = false">
              <v-icon>mdi-close</v-icon>
            </v-btn>
          </v-card-title>

          <v-card-text class="pa-4">
            <v-alert type="info" variant="tonal" class="mb-4">
              {{ tm('addRule.description') }}
            </v-alert>

            <v-autocomplete v-model="selectedNewUmo" :items="availableUmos" :loading="loadingUmos"
              :label="tm('addRule.selectUmo')" variant="outlined" clearable :no-data-text="tm('addRule.noUmos')" />
          </v-card-text>

          <v-card-actions class="px-4 pb-4">
            <v-spacer></v-spacer>
            <v-btn variant="text" @click="addRuleDialog = false">{{ tm('buttons.cancel') }}</v-btn>
            <v-btn color="primary" variant="tonal" @click="createNewRule" :disabled="!selectedNewUmo">
              {{ tm('buttons.next') }}
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>

      <!-- 规则编辑对话框 -->
      <v-dialog v-model="ruleDialog" max-width="700" scrollable>
        <v-card v-if="selectedUmo" class="d-flex flex-column" height="600">
          <v-card-title class="py-3 px-6 d-flex align-center border-b">
            <span>{{ tm('ruleEditor.title') }}</span>
            <v-chip size="small" class="ml-4 font-weight-regular" variant="outlined">
              {{ selectedUmo.umo }}
            </v-chip>
            <v-spacer></v-spacer>
            <v-btn icon="mdi-close" variant="text" @click="closeRuleEditor"></v-btn>
          </v-card-title>

          <v-card-text class="pa-0 overflow-y-auto">
            <div class="px-6 py-4">
              <!-- Service Config Section -->
              <div class="d-flex align-center mb-4">
                <h3 class="font-weight-bold mb-0">{{ tm('ruleEditor.serviceConfig.title') }}</h3>
              </div>

              <v-row dense>
                <v-col cols="12">
                  <v-checkbox v-model="serviceConfig.session_enabled"
                    :label="tm('ruleEditor.serviceConfig.sessionEnabled')" color="success" hide-details class="mb-2" />
                </v-col>
                <v-col cols="12" md="6">
                  <v-checkbox v-model="serviceConfig.llm_enabled" :label="tm('ruleEditor.serviceConfig.llmEnabled')"
                    color="primary" hide-details />
                </v-col>
                <v-col cols="12" md="6">
                  <v-checkbox v-model="serviceConfig.tts_enabled" :label="tm('ruleEditor.serviceConfig.ttsEnabled')"
                    color="secondary" hide-details />
                </v-col>
                <v-col cols="12" class="mt-2">
                  <v-text-field v-model="serviceConfig.custom_name" :label="tm('ruleEditor.serviceConfig.customName')"
                    variant="outlined" hide-details clearable />
                </v-col>
              </v-row>

              <div class="d-flex justify-end mt-4">
                <v-btn variant="text" color="error" size="small" @click="clearServiceConfig" class="mr-2">
                  {{ tm('buttons.clear') }}
                </v-btn>
                <v-btn color="primary" variant="tonal" size="small" @click="saveServiceConfig" :loading="saving"
                  prepend-icon="mdi-content-save">
                  {{ tm('buttons.save') }}
                </v-btn>
              </div>

              <!-- Provider Config Section -->
              <div class="d-flex align-center mb-4 mt-4">
                <h3 class="font-weight-bold mb-0">{{ tm('ruleEditor.providerConfig.title') }}</h3>
              </div>

              <v-row dense>
                <v-col cols="12">
                  <v-select v-model="providerConfig.chat_completion" :items="chatProviderOptions" item-title="label"
                    item-value="value" :label="tm('ruleEditor.providerConfig.chatProvider')" variant="outlined"
                    hide-details clearable class="mb-2" />
                </v-col>
                <v-col cols="12">
                  <v-select v-model="providerConfig.speech_to_text" :items="sttProviderOptions" item-title="label"
                    item-value="value" :label="tm('ruleEditor.providerConfig.sttProvider')" variant="outlined"
                    hide-details clearable :disabled="sttProviderOptions.length === 0" class="mb-2" />
                </v-col>
                <v-col cols="12">
                  <v-select v-model="providerConfig.text_to_speech" :items="ttsProviderOptions" item-title="label"
                    item-value="value" :label="tm('ruleEditor.providerConfig.ttsProvider')" variant="outlined"
                    hide-details clearable :disabled="ttsProviderOptions.length === 0" />
                </v-col>
              </v-row>

              <div class="d-flex justify-end mt-4">
                <v-btn variant="text" color="error" size="small" @click="clearProviderConfig" class="mr-2">
                  {{ tm('buttons.clear') }}
                </v-btn>
                <v-btn color="primary" variant="tonal" size="small" @click="saveProviderConfig" :loading="saving"
                  prepend-icon="mdi-content-save">
                  {{ tm('buttons.save') }}
                </v-btn>
              </div>

              <!-- Persona Config Section -->
              <div class="d-flex align-center mb-4 mt-4">
                <h3 class="font-weight-bold mb-0">{{ tm('ruleEditor.personaConfig.title') }}</h3>
              </div>

              <v-row dense>
                <v-col cols="12">
                  <v-select v-model="serviceConfig.persona_id" :items="personaOptions" item-title="label"
                    item-value="value" :label="tm('ruleEditor.personaConfig.selectPersona')" variant="outlined"
                    hide-details clearable />
                </v-col>
                <v-col cols="12">
                  <v-alert type="info" variant="tonal" class="mt-2" icon="mdi-information-outline">
                    {{ tm('ruleEditor.personaConfig.hint') }}
                  </v-alert>
                </v-col>
              </v-row>

              <div class="d-flex justify-end mt-4">
                <v-btn color="primary" variant="tonal" size="small" @click="saveServiceConfig" :loading="saving"
                  prepend-icon="mdi-content-save">
                  {{ tm('buttons.save') }}
                </v-btn>
              </div>
            </div>
          </v-card-text>
        </v-card>
      </v-dialog>

      <!-- 确认删除对话框 -->
      <v-dialog v-model="deleteDialog" max-width="400">
        <v-card>
          <v-card-title class="text-h6">{{ tm('deleteConfirm.title') }}</v-card-title>
          <v-card-text>
            {{ tm('deleteConfirm.message') }}
            <br><br>
            <code>{{ deleteTarget?.umo }}</code>
          </v-card-text>
          <v-card-actions>
            <v-spacer></v-spacer>
            <v-btn variant="text" @click="deleteDialog = false">{{ tm('buttons.cancel') }}</v-btn>
            <v-btn color="error" variant="tonal" @click="deleteAllRules" :loading="deleting">{{ tm('buttons.delete')
              }}</v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>

      <!-- 批量删除确认对话框 -->
      <v-dialog v-model="batchDeleteDialog" max-width="500">
        <v-card>
          <v-card-title class="text-h6">{{ tm('batchDeleteConfirm.title') }}</v-card-title>
          <v-card-text>
            {{ tm('batchDeleteConfirm.message', { count: selectedItems.length }) }}
            <div class="mt-3" style="max-height: 200px; overflow-y: auto;">
              <v-chip v-for="item in selectedItems" :key="item.umo" size="small" class="ma-1" variant="outlined">
                {{ item.rules?.session_service_config?.custom_name || item.umo }}
              </v-chip>
            </div>
          </v-card-text>
          <v-card-actions>
            <v-spacer></v-spacer>
            <v-btn variant="text" @click="batchDeleteDialog = false">{{ tm('buttons.cancel') }}</v-btn>
            <v-btn color="error" variant="tonal" @click="batchDeleteRules" :loading="deleting">
              {{ tm('buttons.delete') }}
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>

      <!-- 提示信息 -->
      <v-snackbar v-model="snackbar" :timeout="3000" elevation="24" :color="snackbarColor" location="top">
        {{ snackbarText }}
      </v-snackbar>

      <!-- 快速编辑备注名对话框 -->
      <v-dialog v-model="quickEditNameDialog" max-width="400">
        <v-card>
          <v-card-title class="py-3 px-4">{{ tm('quickEditName.title') }}</v-card-title>
          <v-card-text class="pa-4">
            <v-text-field v-model="quickEditNameValue" :label="tm('ruleEditor.serviceConfig.customName')"
              variant="outlined" hide-details clearable autofocus @keyup.enter="saveQuickEditName" />
          </v-card-text>
          <v-card-actions class="px-4 pb-4">
            <v-spacer></v-spacer>
            <v-btn variant="text" @click="quickEditNameDialog = false">{{ tm('buttons.cancel') }}</v-btn>
            <v-btn color="primary" variant="tonal" @click="saveQuickEditName" :loading="saving">
              {{ tm('buttons.save') }}
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>
    </v-container>
  </div>
</template>

<script>
import axios from 'axios'
import { useI18n, useModuleI18n } from '@/i18n/composables'

export default {
  name: 'SessionManagementPage',
  setup() {
    const { t } = useI18n()
    const { tm } = useModuleI18n('features/session-management')

    return {
      t,
      tm
    }
  },
  data() {
    return {
      loading: false,
      saving: false,
      deleting: false,
      loadingUmos: false,
      rulesList: [],
      searchQuery: '',

      // 分页
      currentPage: 1,
      itemsPerPage: 10,
      totalItems: 0,
      searchTimeout: null,

      // 可用选项
      availablePersonas: [],
      availableChatProviders: [],
      availableSttProviders: [],
      availableTtsProviders: [],

      // 添加规则
      addRuleDialog: false,
      availableUmos: [],
      selectedNewUmo: null,

      // 规则编辑
      ruleDialog: false,
      selectedUmo: null,
      editingRules: {},

      // 服务配置
      serviceConfig: {
        session_enabled: true,
        llm_enabled: true,
        tts_enabled: true,
        custom_name: '',
        persona_id: null,
      },

      // Provider 配置
      providerConfig: {
        chat_completion: null,
        speech_to_text: null,
        text_to_speech: null,
      },

      // 删除确认
      deleteDialog: false,
      deleteTarget: null,

      // 批量选择和删除
      selectedItems: [],
      batchDeleteDialog: false,

      // 快速编辑备注名
      quickEditNameDialog: false,
      quickEditNameTarget: null,
      quickEditNameValue: '',

      // 提示信息
      snackbar: false,
      snackbarText: '',
      snackbarColor: 'success',
    }
  },

  computed: {
    headers() {
      return [
        { title: this.tm('table.headers.umoInfo'), key: 'umo_info', sortable: false, minWidth: '300px' },
        { title: this.tm('table.headers.rulesOverview'), key: 'rules_overview', sortable: false, minWidth: '250px' },
        { title: this.tm('table.headers.actions'), key: 'actions', sortable: false, minWidth: '150px' },
      ]
    },

    filteredRulesList() {
      // 搜索已移至服务端，直接返回 rulesList
      return this.rulesList
    },

    personaOptions() {
      return [
        { label: this.tm('persona.none'), value: null },
        ...this.availablePersonas.map(p => ({
          label: p.name,
          value: p.name
        }))
      ]
    },

    chatProviderOptions() {
      return this.availableChatProviders.map(p => ({
        label: `${p.name} (${p.model})`,
        value: p.id
      }))
    },

    sttProviderOptions() {
      return this.availableSttProviders.map(p => ({
        label: `${p.name} (${p.model})`,
        value: p.id
      }))
    },

    ttsProviderOptions() {
      return this.availableTtsProviders.map(p => ({
        label: `${p.name} (${p.model})`,
        value: p.id
      }))
    },
  },

  watch: {
    searchQuery: {
      handler() {
        // 使用 debounce 延迟搜索
        if (this.searchTimeout) {
          clearTimeout(this.searchTimeout)
        }
        this.searchTimeout = setTimeout(() => {
          this.onSearchChange()
        }, 300)
      }
    }
  },

  mounted() {
    this.loadData()
  },

  beforeUnmount() {
    if (this.searchTimeout) {
      clearTimeout(this.searchTimeout)
    }
  },

  methods: {
    async loadData() {
      this.loading = true
      try {
        const response = await axios.get('/api/session/list-rule', {
          params: {
            page: this.currentPage,
            page_size: this.itemsPerPage,
            search: this.searchQuery || ''
          }
        })
        if (response.data.status === 'ok') {
          const data = response.data.data
          this.rulesList = data.rules
          this.totalItems = data.total
          this.availablePersonas = data.available_personas
          this.availableChatProviders = data.available_chat_providers
          this.availableSttProviders = data.available_stt_providers
          this.availableTtsProviders = data.available_tts_providers
        } else {
          this.showError(response.data.message || this.tm('messages.loadError'))
        }
      } catch (error) {
        this.showError(error.response?.data?.message || this.tm('messages.loadError'))
      }
      this.loading = false
    },

    onTableOptionsUpdate(options) {
      // 当分页参数变化时重新加载数据
      this.currentPage = options.page
      this.itemsPerPage = options.itemsPerPage
      this.loadData()
    },

    onSearchChange() {
      // 搜索时重置到第一页
      this.currentPage = 1
      this.loadData()
    },

    async loadUmos() {
      this.loadingUmos = true
      try {
        const response = await axios.get('/api/session/active-umos')
        if (response.data.status === 'ok') {
          // 过滤掉已有规则的 umo
          const existingUmos = new Set(this.rulesList.map(r => r.umo))
          this.availableUmos = response.data.data.umos.filter(umo => !existingUmos.has(umo))
        }
      } catch (error) {
        this.showError(error.response?.data?.message || this.tm('messages.loadError'))
      }
      this.loadingUmos = false
    },

    async refreshData() {
      await this.loadData()
      this.showSuccess(this.tm('messages.refreshSuccess'))
    },

    hasProviderConfig(rules) {
      return rules && (
        rules['provider_perf_chat_completion'] ||
        rules['provider_perf_speech_to_text'] ||
        rules['provider_perf_text_to_speech']
      )
    },

    async openAddRuleDialog() {
      this.addRuleDialog = true
      this.selectedNewUmo = null
      await this.loadUmos()
    },

    createNewRule() {
      if (!this.selectedNewUmo) return

      // 创建一个新的规则项并打开编辑器
      const newItem = {
        umo: this.selectedNewUmo,
        rules: {},
      }
      // 解析 umo 格式
      const parts = this.selectedNewUmo.split(':')
      if (parts.length >= 3) {
        newItem.platform = parts[0]
        newItem.message_type = parts[1]
        newItem.session_id = parts[2]
      }

      this.addRuleDialog = false
      this.openRuleEditor(newItem)
    },

    openRuleEditor(item) {
      this.selectedUmo = item
      this.editingRules = item.rules || {}

      // 初始化服务配置
      const svcConfig = this.editingRules.session_service_config || {}
      this.serviceConfig = {
        session_enabled: svcConfig.session_enabled !== false,
        llm_enabled: svcConfig.llm_enabled !== false,
        tts_enabled: svcConfig.tts_enabled !== false,
        custom_name: svcConfig.custom_name || '',
        persona_id: svcConfig.persona_id || null,
      }

      // 初始化 Provider 配置
      this.providerConfig = {
        chat_completion: this.editingRules['provider_perf_chat_completion'] || null,
        speech_to_text: this.editingRules['provider_perf_speech_to_text'] || null,
        text_to_speech: this.editingRules['provider_perf_text_to_speech'] || null,
      }

      this.ruleDialog = true
    },

    closeRuleEditor() {
      this.ruleDialog = false
      this.selectedUmo = null
      this.editingRules = {}
    },

    async saveServiceConfig() {
      if (!this.selectedUmo) return

      this.saving = true
      try {
        const config = { ...this.serviceConfig }
        // 清理空值
        if (!config.custom_name) delete config.custom_name
        if (config.persona_id === null) delete config.persona_id

        const response = await axios.post('/api/session/update-rule', {
          umo: this.selectedUmo.umo,
          rule_key: 'session_service_config',
          rule_value: config
        })

        if (response.data.status === 'ok') {
          this.showSuccess(this.tm('messages.saveSuccess'))
          this.editingRules.session_service_config = config

          // 更新或添加到列表
          let item = this.rulesList.find(u => u.umo === this.selectedUmo.umo)
          if (item) {
            item.rules = { ...item.rules, session_service_config: config }
          } else {
            // 新规则，添加到列表
            this.rulesList.push({
              umo: this.selectedUmo.umo,
              platform: this.selectedUmo.platform,
              message_type: this.selectedUmo.message_type,
              session_id: this.selectedUmo.session_id,
              rules: { session_service_config: config }
            })
          }
        } else {
          this.showError(response.data.message || this.tm('messages.saveError'))
        }
      } catch (error) {
        this.showError(error.response?.data?.message || this.tm('messages.saveError'))
      }
      this.saving = false
    },

    async clearServiceConfig() {
      if (!this.selectedUmo) return

      this.saving = true
      try {
        const response = await axios.post('/api/session/delete-rule', {
          umo: this.selectedUmo.umo,
          rule_key: 'session_service_config'
        })

        if (response.data.status === 'ok') {
          this.showSuccess(this.tm('messages.clearSuccess'))
          delete this.editingRules.session_service_config
          this.serviceConfig = {
            session_enabled: true,
            llm_enabled: true,
            tts_enabled: true,
            custom_name: '',
            persona_id: null,
          }
          // 更新列表中的数据
          const item = this.rulesList.find(u => u.umo === this.selectedUmo.umo)
          if (item) {
            delete item.rules.session_service_config
            // 如果没有任何规则了，从列表中移除
            if (Object.keys(item.rules).length === 0) {
              const index = this.rulesList.findIndex(u => u.umo === this.selectedUmo.umo)
              if (index > -1) this.rulesList.splice(index, 1)
            }
          }
        } else {
          this.showError(response.data.message || this.tm('messages.clearError'))
        }
      } catch (error) {
        this.showError(error.response?.data?.message || this.tm('messages.clearError'))
      }
      this.saving = false
    },

    async saveProviderConfig() {
      if (!this.selectedUmo) return

      this.saving = true
      try {
        const tasks = []
        const providerTypes = ['chat_completion', 'speech_to_text', 'text_to_speech']

        for (const type of providerTypes) {
          const value = this.providerConfig[type]
          if (value) {
            tasks.push(
              axios.post('/api/session/update-rule', {
                umo: this.selectedUmo.umo,
                rule_key: `provider_perf_${type}`,
                rule_value: value
              })
            )
          }
        }

        if (tasks.length > 0) {
          await Promise.all(tasks)
          this.showSuccess(this.tm('messages.saveSuccess'))

          // 更新或添加到列表
          let item = this.rulesList.find(u => u.umo === this.selectedUmo.umo)
          if (!item) {
            item = {
              umo: this.selectedUmo.umo,
              platform: this.selectedUmo.platform,
              message_type: this.selectedUmo.message_type,
              session_id: this.selectedUmo.session_id,
              rules: {}
            }
            this.rulesList.push(item)
          }
          for (const type of providerTypes) {
            if (this.providerConfig[type]) {
              item.rules[`provider_perf_${type}`] = this.providerConfig[type]
              this.editingRules[`provider_perf_${type}`] = this.providerConfig[type]
            }
          }
        } else {
          this.showSuccess(this.tm('messages.noChanges'))
        }
      } catch (error) {
        this.showError(error.response?.data?.message || this.tm('messages.saveError'))
      }
      this.saving = false
    },

    async clearProviderConfig() {
      if (!this.selectedUmo) return

      this.saving = true
      try {
        const providerTypes = ['chat_completion', 'speech_to_text', 'text_to_speech']
        const tasks = providerTypes.map(type =>
          axios.post('/api/session/delete-rule', {
            umo: this.selectedUmo.umo,
            rule_key: `provider_perf_${type}`
          })
        )

        await Promise.all(tasks)
        this.showSuccess(this.tm('messages.clearSuccess'))

        // 更新本地数据
        this.providerConfig = {
          chat_completion: null,
          speech_to_text: null,
          text_to_speech: null,
        }
        const item = this.rulesList.find(u => u.umo === this.selectedUmo.umo)
        if (item) {
          for (const type of providerTypes) {
            delete item.rules[`provider_perf_${type}`]
            delete this.editingRules[`provider_perf_${type}`]
          }
          // 如果没有任何规则了，从列表中移除
          if (Object.keys(item.rules).length === 0) {
            const index = this.rulesList.findIndex(u => u.umo === this.selectedUmo.umo)
            if (index > -1) this.rulesList.splice(index, 1)
          }
        }
      } catch (error) {
        this.showError(error.response?.data?.message || this.tm('messages.clearError'))
      }
      this.saving = false
    },

    confirmDeleteRules(item) {
      this.deleteTarget = item
      this.deleteDialog = true
    },

    async deleteAllRules() {
      if (!this.deleteTarget) return

      this.deleting = true
      try {
        const response = await axios.post('/api/session/delete-rule', {
          umo: this.deleteTarget.umo
        })

        if (response.data.status === 'ok') {
          this.showSuccess(this.tm('messages.deleteSuccess'))
          // 从列表中移除
          const index = this.rulesList.findIndex(u => u.umo === this.deleteTarget.umo)
          if (index > -1) {
            this.rulesList.splice(index, 1)
          }
          this.deleteDialog = false
          this.deleteTarget = null
          // 重新加载数据以更新 totalItems
          await this.loadData()
        } else {
          this.showError(response.data.message || this.tm('messages.deleteError'))
        }
      } catch (error) {
        this.showError(error.response?.data?.message || this.tm('messages.deleteError'))
      }
      this.deleting = false
    },

    confirmBatchDelete() {
      if (this.selectedItems.length === 0) return
      this.batchDeleteDialog = true
    },

    async batchDeleteRules() {
      if (this.selectedItems.length === 0) return

      this.deleting = true
      try {
        const umos = this.selectedItems.map(item => item.umo)
        const response = await axios.post('/api/session/batch-delete-rule', {
          umos: umos
        })

        if (response.data.status === 'ok') {
          const data = response.data.data
          this.showSuccess(data.message || this.tm('messages.batchDeleteSuccess'))
          this.batchDeleteDialog = false
          this.selectedItems = []
          // 重新加载数据
          await this.loadData()
        } else {
          this.showError(response.data.message || this.tm('messages.batchDeleteError'))
        }
      } catch (error) {
        this.showError(error.response?.data?.message || this.tm('messages.batchDeleteError'))
      }
      this.deleting = false
    },

    getPlatformColor(platform) {
      const colors = {
        'aiocqhttp': 'blue',
        'wechatpadpro': 'green',
        'qq_official': 'purple',
        'telegram': 'light-blue',
        'discord': 'indigo',
        'webchat': 'orange',
        'default': 'grey'
      }
      return colors[platform] || colors.default
    },

    showSuccess(message) {
      this.snackbarText = message
      this.snackbarColor = 'success'
      this.snackbar = true
    },

    showError(message) {
      this.snackbarText = message
      this.snackbarColor = 'error'
      this.snackbar = true
    },

    openQuickEditName(item) {
      this.quickEditNameTarget = item
      this.quickEditNameValue = item.rules?.session_service_config?.custom_name || ''
      this.quickEditNameDialog = true
    },

    async saveQuickEditName() {
      if (!this.quickEditNameTarget) return

      this.saving = true
      try {
        // 获取现有的 session_service_config 或创建新的
        const existingConfig = this.quickEditNameTarget.rules?.session_service_config || {}
        const config = {
          session_enabled: existingConfig.session_enabled !== false,
          llm_enabled: existingConfig.llm_enabled !== false,
          tts_enabled: existingConfig.tts_enabled !== false,
          ...existingConfig,
        }

        // 更新 custom_name
        if (this.quickEditNameValue) {
          config.custom_name = this.quickEditNameValue
        } else {
          delete config.custom_name
        }

        const response = await axios.post('/api/session/update-rule', {
          umo: this.quickEditNameTarget.umo,
          rule_key: 'session_service_config',
          rule_value: config
        })

        if (response.data.status === 'ok') {
          this.showSuccess(this.tm('messages.saveSuccess'))

          // 更新或添加到列表
          let item = this.rulesList.find(u => u.umo === this.quickEditNameTarget.umo)
          if (item) {
            if (!item.rules) item.rules = {}
            item.rules.session_service_config = config
          } else {
            // 新规则，添加到列表
            const parts = this.quickEditNameTarget.umo.split(':')
            this.rulesList.push({
              umo: this.quickEditNameTarget.umo,
              platform: parts[0] || '',
              message_type: parts[1] || '',
              session_id: parts[2] || '',
              rules: { session_service_config: config }
            })
          }

          this.quickEditNameDialog = false
          this.quickEditNameTarget = null
          this.quickEditNameValue = ''
        } else {
          this.showError(response.data.message || this.tm('messages.saveError'))
        }
      } catch (error) {
        this.showError(error.response?.data?.message || this.tm('messages.saveError'))
      }
      this.saving = false
    },
  },
}
</script>

<style scoped>
.v-data-table :deep(.v-data-table__td) {
  padding: 8px 16px !important;
  vertical-align: middle !important;
}

code {
  background-color: rgba(0, 0, 0, 0.05);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 12px;
}
</style>
