<template>
  <div class="session-management-page">
    <v-container fluid class="pa-0">
      <v-card flat>
        <v-card-title class="d-flex align-center py-3 px-4">
          <span class="text-h4">{{ tm('customRules.title') }}</span>
          <v-btn icon="mdi-information-outline" size="small" variant="text" href="https://docs.astrbot.app/use/custom-rules.html" target="_blank"></v-btn>
          <v-chip size="small" class="ml-1">{{ totalItems }} {{ tm('customRules.rulesCount') }}</v-chip>
          <v-row class="me-4 ms-4" dense>
            <v-text-field
              v-model="searchQuery"
              prepend-inner-icon="mdi-magnify"
              :label="tm('search.placeholder')"
              hide-details
              clearable
              variant="solo-filled"
              flat
              class="me-4"
              density="compact"
            ></v-text-field>
          </v-row>
          <v-btn v-if="selectedItems.length > 0" color="error" prepend-icon="mdi-delete" variant="tonal" @click="confirmBatchDelete" class="mr-2" size="small">
            {{ tm('buttons.batchDelete') }} ({{ selectedItems.length }})
          </v-btn>
          <v-btn color="success" prepend-icon="mdi-plus" variant="tonal" @click="openAddRuleDialog" class="mr-2" size="small">
            {{ tm('buttons.addRule') }}
          </v-btn>
          <v-btn color="primary" prepend-icon="mdi-refresh" variant="tonal" @click="refreshData" :loading="loading" size="small">
            {{ tm('buttons.refresh') }}
          </v-btn>
        </v-card-title>

        <v-divider></v-divider>

        <v-card-text class="pa-0">
          <v-data-table-server
            :headers="headers"
            :items="filteredRulesList"
            :loading="loading"
            :items-length="totalItems"
            v-model:items-per-page="itemsPerPage"
            v-model:page="currentPage"
            @update:options="onTableOptionsUpdate"
            class="elevation-0"
            style="font-size: 12px"
            v-model="selectedItems"
            show-select
            item-value="umo"
            return-object
          >
            <!-- UMO 信息 -->
            <template v-slot:item.umo_info="{ item }">
              <UmoDisplay
                :umo="item.umo"
                :platform="item.platform"
                :message-type="item.message_type"
                :session-id="item.session_id"
                :auto-name="item.auto_name"
                :user-alias="item.user_alias"
                :custom-name="item.rules?.session_service_config?.custom_name"
                editable
                :edit-tooltip="tm('buttons.editCustomName')"
                @edit="openQuickEditName(item)"
              />
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
                <div class="text-h6 mt-4 text-grey-600">
                  {{ tm('customRules.noRules') }}
                </div>
                <div class="text-body-2 text-grey-500">
                  {{ tm('customRules.noRulesDesc') }}
                </div>
                <v-btn color="primary" variant="tonal" class="mt-4" @click="openAddRuleDialog">
                  <v-icon start>mdi-plus</v-icon>
                  {{ tm('buttons.addRule') }}
                </v-btn>
              </div>
            </template>
          </v-data-table-server>
        </v-card-text>
      </v-card>
      <!-- 批量操作面板 -->
      <v-card flat class="mt-4">
        <v-card-title class="d-flex align-center py-3 px-4">
          <span class="text-h6">{{ tm('batchOperations.title') }}</span>
          <v-chip size="small" class="ml-2" color="info" variant="outlined">
            {{ tm('batchOperations.hint') }}
          </v-chip>
        </v-card-title>
        <v-card-text>
          <v-row dense>
            <v-col cols="12" md="6" lg="3">
              <v-select
                v-model="batchScope"
                :items="batchScopeOptions"
                item-title="label"
                item-value="value"
                :label="tm('batchOperations.scope')"
                hide-details
                variant="solo-filled"
                flat
                density="comfortable"
              >
              </v-select>
            </v-col>
            <v-col cols="12" md="6" lg="3">
              <v-select
                v-model="batchLlmStatus"
                :items="statusOptions"
                item-title="label"
                item-value="value"
                :label="tm('batchOperations.llmStatus')"
                hide-details
                clearable
                variant="solo-filled"
                flat
                density="comfortable"
              >
              </v-select>
            </v-col>
            <v-col cols="12" md="6" lg="3">
              <v-select
                v-model="batchTtsStatus"
                :items="statusOptions"
                item-title="label"
                item-value="value"
                :label="tm('batchOperations.ttsStatus')"
                hide-details
                clearable
                variant="solo-filled"
                flat
                density="comfortable"
              >
              </v-select>
            </v-col>
            <v-col cols="12" md="6" lg="3">
              <v-select
                v-model="batchChatProvider"
                :items="batchChatProviderOptions"
                item-title="label"
                item-value="value"
                :label="tm('batchOperations.chatProvider')"
                hide-details
                clearable
                variant="solo-filled"
                flat
                density="comfortable"
              >
              </v-select>
            </v-col>
          </v-row>
          <v-row dense class="mt-3">
            <v-col cols="12" class="d-flex justify-end">
              <v-btn color="primary" variant="tonal" size="large" @click="applyBatchChanges" :disabled="!canApplyBatch" :loading="batchUpdating" prepend-icon="mdi-check-all">
                {{ tm('batchOperations.apply') }}
              </v-btn>
            </v-col>
          </v-row>
        </v-card-text>
      </v-card>

      <!-- 分组管理面板 -->
      <v-card flat class="mt-4">
        <v-card-title class="d-flex align-center py-3 px-4">
          <span class="text-h6">{{ tm('groups.title') }}</span>
          <v-chip size="small" class="ml-2" color="secondary" variant="outlined">
            {{ tm('groups.count', { count: groups.length }) }}
          </v-chip>
          <v-spacer></v-spacer>
          <v-btn v-if="selectedItems.length > 0 && groups.length > 0" color="info" variant="tonal" size="small" class="mr-2">
            <v-icon start>mdi-folder-plus</v-icon>
            {{ tm('groups.addToGroup') }}
            <v-menu activator="parent">
              <v-list density="compact">
                <v-list-item v-for="g in groups" :key="g.id" @click="addSelectedToGroup(g.id)">
                  <v-list-item-title>{{
                    tm('groups.customGroupOption', {
                      name: g.name,
                      count: g.umo_count,
                    })
                  }}</v-list-item-title>
                </v-list-item>
              </v-list>
            </v-menu>
          </v-btn>
          <v-btn color="success" variant="tonal" size="small" @click="openCreateGroupDialog" prepend-icon="mdi-folder-plus">
            {{ tm('groups.create') }}
          </v-btn>
        </v-card-title>
        <v-card-text v-if="groups.length > 0">
          <v-row dense>
            <v-col v-for="group in groups" :key="group.id" cols="12" sm="6" md="4" lg="3">
              <v-card variant="outlined" class="pa-3">
                <div class="d-flex align-center justify-space-between">
                  <div>
                    <div class="font-weight-bold">{{ group.name }}</div>
                    <div class="text-caption text-grey">
                      {{ tm('groups.sessionsCount', { count: group.umo_count }) }}
                    </div>
                  </div>
                  <div>
                    <v-btn icon size="small" variant="text" @click="openEditGroupDialog(group)">
                      <v-icon size="small">mdi-pencil</v-icon>
                    </v-btn>
                    <v-btn icon size="small" variant="text" color="error" @click="deleteGroup(group)">
                      <v-icon size="small">mdi-delete</v-icon>
                    </v-btn>
                  </div>
                </div>
              </v-card>
            </v-col>
          </v-row>
        </v-card-text>
        <v-card-text v-else class="text-center text-grey py-6">
          {{ tm('groups.empty') }}
        </v-card-text>
      </v-card>

      <!-- 分组编辑对话框 -->
      <v-dialog v-model="groupDialog" max-width="800" @after-enter="loadAvailableUmos">
        <v-card>
          <v-card-title class="text-h3 pa-4 pb-0 pl-6">
            {{ groupDialogMode === 'create' ? tm('groups.create') : tm('groups.edit') }}
          </v-card-title>
          <v-card-text>
            <v-text-field v-model="editingGroup.name" :label="tm('groups.name')" variant="outlined" hide-details class="mb-4"></v-text-field>
            <v-row dense>
              <!-- 左侧：可选会话 -->
              <v-col cols="5">
                <div class="text-subtitle-2 mb-2">
                  {{
                    tm('groups.availableSessions', {
                      count: unselectedUmos.length,
                    })
                  }}
                </div>
                <v-text-field
                  v-model="groupMemberSearch"
                  :placeholder="tm('groups.searchPlaceholder')"
                  variant="outlined"
                  density="compact"
                  hide-details
                  class="mb-2"
                  clearable
                  prepend-inner-icon="mdi-magnify"
                ></v-text-field>
                <v-list density="compact" class="transfer-list">
                  <v-list-item v-for="umo in filteredUnselectedUmos" :key="umo" @click="addToGroup(umo)" class="transfer-item">
                    <template v-slot:prepend>
                      <v-icon size="small" color="grey">mdi-plus</v-icon>
                    </template>
                    <v-list-item-title>
                      <UmoDisplay v-bind="getAvailableUmoDisplayProps(umo)" compact :show-info="false" :show-platform="false" />
                    </v-list-item-title>
                    <template v-slot:append>
                      <v-chip v-if="getAvailableUmoInfo(umo).platform" size="x-small" :color="getPlatformColor(getAvailableUmoInfo(umo).platform)" class="umo-list-platform">
                        {{ getAvailableUmoInfo(umo).platform }}
                      </v-chip>
                    </template>
                  </v-list-item>
                  <v-list-item v-if="filteredUnselectedUmos.length === 0 && !loadingUmos">
                    <v-list-item-title class="text-caption text-grey text-center">{{ tm('groups.noMatch') }}</v-list-item-title>
                  </v-list-item>
                  <v-list-item v-if="loadingUmos">
                    <v-list-item-title class="text-center"><v-progress-circular indeterminate size="20"></v-progress-circular></v-list-item-title>
                  </v-list-item>
                </v-list>
              </v-col>
              <!-- 中间：操作按钮 -->
              <v-col cols="2" class="d-flex flex-column align-center justify-center">
                <v-btn icon size="small" variant="tonal" color="primary" class="mb-2" @click="addAllToGroup" :disabled="unselectedUmos.length === 0">
                  <v-icon>mdi-chevron-double-right</v-icon>
                </v-btn>
                <v-btn icon size="small" variant="tonal" color="error" @click="removeAllFromGroup" :disabled="editingGroup.umos.length === 0">
                  <v-icon>mdi-chevron-double-left</v-icon>
                </v-btn>
              </v-col>
              <!-- 右侧：已选会话 -->
              <v-col cols="5">
                <div class="text-subtitle-2 mb-2">
                  {{
                    tm('groups.selectedSessions', {
                      count: editingGroup.umos.length,
                    })
                  }}
                </div>
                <v-text-field
                  v-model="groupSelectedSearch"
                  :placeholder="tm('groups.searchPlaceholder')"
                  variant="outlined"
                  density="compact"
                  hide-details
                  class="mb-2"
                  clearable
                  prepend-inner-icon="mdi-magnify"
                ></v-text-field>
                <v-list density="compact" class="transfer-list">
                  <v-list-item v-for="umo in filteredSelectedUmos" :key="umo" @click="removeFromGroup(umo)" class="transfer-item">
                    <template v-slot:prepend>
                      <v-icon size="small" color="error">mdi-minus</v-icon>
                    </template>
                    <v-list-item-title>
                      <UmoDisplay v-bind="getAvailableUmoDisplayProps(umo)" compact :show-info="false" :show-platform="false" />
                    </v-list-item-title>
                    <template v-slot:append>
                      <v-chip v-if="getAvailableUmoInfo(umo).platform" size="x-small" :color="getPlatformColor(getAvailableUmoInfo(umo).platform)" class="umo-list-platform">
                        {{ getAvailableUmoInfo(umo).platform }}
                      </v-chip>
                    </template>
                  </v-list-item>
                  <v-list-item v-if="editingGroup.umos.length === 0">
                    <v-list-item-title class="text-caption text-grey text-center">{{ tm('groups.noMembers') }}</v-list-item-title>
                  </v-list-item>
                </v-list>
              </v-col>
            </v-row>
          </v-card-text>
          <v-card-actions class="px-4 pb-4">
            <v-spacer></v-spacer>
            <v-btn variant="text" @click="groupDialog = false">{{ tm('buttons.cancel') }}</v-btn>
            <v-btn color="primary" variant="tonal" @click="saveGroup">{{ tm('buttons.save') }}</v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>

      <!-- 添加规则对话框 - 选择 UMO -->
      <v-dialog v-model="addRuleDialog" max-width="600">
        <v-card>
          <v-card-title class="text-h3 pa-4 pb-0 pl-6 d-flex align-center">
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

            <v-autocomplete v-model="selectedNewUmo" :items="availableUmos" :loading="loadingUmos" :label="tm('addRule.selectUmo')" variant="outlined" clearable :no-data-text="tm('addRule.noUmos')">
              <template v-slot:item="{ props, item }">
                <v-list-item v-bind="props">
                  <template v-slot:title>
                    <UmoDisplay v-bind="getAvailableUmoDisplayProps(item.raw)" compact :show-info="false" :show-platform="false" />
                  </template>
                  <template v-slot:append>
                    <v-chip v-if="getAvailableUmoInfo(item.raw).platform" size="x-small" :color="getPlatformColor(getAvailableUmoInfo(item.raw).platform)" class="umo-list-platform">
                      {{ getAvailableUmoInfo(item.raw).platform }}
                    </v-chip>
                  </template>
                </v-list-item>
              </template>
              <template v-slot:selection="{ item }">
                <v-chip v-if="item && getUmoSelectionText(item.raw)" size="small" variant="tonal" color="primary" class="umo-selection-chip">
                  {{ getUmoSelectionText(item.raw) }}
                </v-chip>
              </template>
            </v-autocomplete>
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
      <v-dialog v-model="ruleDialog" max-width="550" scrollable>
        <v-card v-if="selectedUmo" class="d-flex flex-column" height="600">
          <v-card-title class="text-h3 pa-4 pb-0 pl-6 d-flex align-center border-b">
            <span>{{ tm('ruleEditor.title') }}</span>
            <v-chip size="x-small" class="ml-2 font-weight-regular" variant="outlined">
              {{ selectedUmo.umo }}
            </v-chip>
            <v-spacer></v-spacer>
            <v-btn icon="mdi-close" variant="text" @click="closeRuleEditor"></v-btn>
          </v-card-title>

          <v-card-text class="pa-0 overflow-y-auto">
            <div class="px-6 py-4">
              <!-- Service Config Section -->
              <div class="d-flex align-center mb-4">
                <h3 class="font-weight-bold mb-0">
                  {{ tm('ruleEditor.serviceConfig.title') }}
                </h3>
              </div>

              <v-row dense>
                <v-col cols="12">
                  <v-checkbox v-model="serviceConfig.session_enabled" :label="tm('ruleEditor.serviceConfig.sessionEnabled')" color="success" hide-details class="mb-2" />
                </v-col>
                <v-col cols="12" md="6">
                  <v-checkbox v-model="serviceConfig.llm_enabled" :label="tm('ruleEditor.serviceConfig.llmEnabled')" color="primary" hide-details />
                </v-col>
                <v-col cols="12" md="6">
                  <v-checkbox v-model="serviceConfig.tts_enabled" :label="tm('ruleEditor.serviceConfig.ttsEnabled')" color="secondary" hide-details />
                </v-col>
                <v-col cols="12" class="mt-2">
                  <v-text-field v-model="serviceConfig.custom_name" :label="tm('ruleEditor.serviceConfig.customName')" variant="outlined" hide-details clearable />
                </v-col>
              </v-row>

              <div class="d-flex justify-end mt-4">
                <v-btn color="primary" variant="tonal" size="small" @click="saveServiceConfig" :loading="saving" prepend-icon="mdi-content-save">
                  {{ tm('buttons.save') }}
                </v-btn>
              </div>

              <!-- Provider Config Section -->
              <div class="d-flex align-center mb-4 mt-4">
                <h3 class="font-weight-bold mb-0">
                  {{ tm('ruleEditor.providerConfig.title') }}
                </h3>
              </div>

              <v-row dense>
                <v-col cols="12">
                  <v-select
                    v-model="providerConfig.chat_completion"
                    :items="chatProviderOptions"
                    item-title="label"
                    item-value="value"
                    :label="tm('ruleEditor.providerConfig.chatProvider')"
                    variant="outlined"
                    hide-details
                    class="mb-2"
                  />
                </v-col>
                <v-col cols="12">
                  <v-select
                    v-model="providerConfig.speech_to_text"
                    :items="sttProviderOptions"
                    item-title="label"
                    item-value="value"
                    :label="tm('ruleEditor.providerConfig.sttProvider')"
                    variant="outlined"
                    hide-details
                    :disabled="availableSttProviders.length === 0"
                    class="mb-2"
                  />
                </v-col>
                <v-col cols="12">
                  <v-select
                    v-model="providerConfig.text_to_speech"
                    :items="ttsProviderOptions"
                    item-title="label"
                    item-value="value"
                    :label="tm('ruleEditor.providerConfig.ttsProvider')"
                    variant="outlined"
                    hide-details
                    :disabled="availableTtsProviders.length === 0"
                  />
                </v-col>
              </v-row>

              <div class="d-flex justify-end mt-4">
                <v-btn color="primary" variant="tonal" size="small" @click="saveProviderConfig" :loading="saving" prepend-icon="mdi-content-save">
                  {{ tm('buttons.save') }}
                </v-btn>
              </div>

              <!-- Persona Config Section -->
              <div class="d-flex align-center mb-4 mt-4">
                <h3 class="font-weight-bold mb-0">
                  {{ tm('ruleEditor.personaConfig.title') }}
                </h3>
              </div>

              <v-row dense>
                <v-col cols="12">
                  <v-select
                    v-model="serviceConfig.persona_id"
                    :items="personaOptions"
                    item-title="label"
                    item-value="value"
                    :label="tm('ruleEditor.personaConfig.selectPersona')"
                    variant="outlined"
                    hide-details
                    clearable
                  />
                </v-col>
                <v-col cols="12">
                  <v-alert type="info" variant="tonal" class="mt-2" icon="mdi-information-outline">
                    {{ tm('ruleEditor.personaConfig.hint') }}
                  </v-alert>
                </v-col>
              </v-row>

              <div class="d-flex justify-end mt-4">
                <v-btn color="primary" variant="tonal" size="small" @click="saveServiceConfig" :loading="saving" prepend-icon="mdi-content-save">
                  {{ tm('buttons.save') }}
                </v-btn>
              </div>

              <!-- Plugin Config Section -->
              <div class="d-flex align-center mb-4 mt-4">
                <h3 class="font-weight-bold mb-0">
                  {{ tm('ruleEditor.pluginConfig.title') }}
                </h3>
              </div>

              <v-row dense>
                <v-col cols="12">
                  <v-select
                    v-model="pluginConfig.disabled_plugins"
                    :items="pluginOptions"
                    item-title="label"
                    item-value="value"
                    :label="tm('ruleEditor.pluginConfig.disabledPlugins')"
                    variant="outlined"
                    hide-details
                    multiple
                    chips
                    closable-chips
                    clearable
                  />
                </v-col>
                <v-col cols="12">
                  <v-alert type="info" variant="tonal" class="mt-2" icon="mdi-information-outline">
                    {{ tm('ruleEditor.pluginConfig.hint') }}
                  </v-alert>
                </v-col>
              </v-row>

              <div class="d-flex justify-end mt-4">
                <v-btn color="primary" variant="tonal" size="small" @click="savePluginConfig" :loading="saving" prepend-icon="mdi-content-save">
                  {{ tm('buttons.save') }}
                </v-btn>
              </div>

              <!-- KB Config Section -->
              <div class="d-flex align-center mb-4 mt-4">
                <h3 class="font-weight-bold mb-0">
                  {{ tm('ruleEditor.kbConfig.title') }}
                </h3>
              </div>

              <v-row dense>
                <v-col cols="12">
                  <v-select
                    v-model="kbConfig.kb_ids"
                    :items="kbOptions"
                    item-title="label"
                    item-value="value"
                    :disabled="availableKbs.length === 0"
                    :label="tm('ruleEditor.kbConfig.selectKbs')"
                    variant="outlined"
                    hide-details
                    multiple
                    chips
                    closable-chips
                    clearable
                  />
                </v-col>
                <v-col cols="12" md="6">
                  <v-text-field v-model.number="kbConfig.top_k" :label="tm('ruleEditor.kbConfig.topK')" variant="outlined" hide-details type="number" min="1" max="20" class="mt-3" />
                </v-col>
                <v-col cols="12" md="6">
                  <v-checkbox v-model="kbConfig.enable_rerank" :label="tm('ruleEditor.kbConfig.enableRerank')" color="primary" hide-details class="mt-3" />
                </v-col>
              </v-row>

              <div class="d-flex justify-end mt-4">
                <v-btn color="primary" variant="tonal" size="small" @click="saveKbConfig" :loading="saving" prepend-icon="mdi-content-save">
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
          <v-card-title class="text-h3 pa-4 pb-0 pl-6">{{ tm('deleteConfirm.title') }}</v-card-title>
          <v-card-text>
            {{ tm('deleteConfirm.message') }}
            <br /><br />
            <code>{{ deleteTarget?.umo }}</code>
          </v-card-text>
          <v-card-actions>
            <v-spacer></v-spacer>
            <v-btn variant="text" @click="deleteDialog = false">{{ tm('buttons.cancel') }}</v-btn>
            <v-btn color="error" variant="tonal" @click="deleteAllRules" :loading="deleting">{{ tm('buttons.delete') }}</v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>

      <!-- 批量删除确认对话框 -->
      <v-dialog v-model="batchDeleteDialog" max-width="500">
        <v-card>
          <v-card-title class="text-h3 pa-4 pb-0 pl-6">{{ tm('batchDeleteConfirm.title') }}</v-card-title>
          <v-card-text>
            {{ tm('batchDeleteConfirm.message', { count: selectedItems.length }) }}
            <div class="mt-3" style="max-height: 200px; overflow-y: auto">
              <v-chip v-for="item in selectedItems" :key="item.umo" size="small" class="ma-1" variant="outlined">
                {{ getUmoDisplayText(item) }}
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
      <v-snackbar v-model="snackbar" :timeout="3000" elevation="6" :color="snackbarColor" location="top">
        {{ snackbarText }}
      </v-snackbar>

      <!-- 快速编辑备注名对话框 -->
      <v-dialog v-model="quickEditNameDialog" max-width="400">
        <v-card>
          <v-card-title class="text-h3 pa-4 pb-0 pl-6">{{ tm('quickEditName.title') }}</v-card-title>
          <v-card-text class="pa-4">
            <v-text-field v-model="quickEditNameValue" :label="tm('ruleEditor.serviceConfig.customName')" variant="outlined" hide-details clearable autofocus @keyup.enter="saveQuickEditName" />
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
import { sessionApi } from '@/api/v1'
import UmoDisplay from '@/components/shared/UmoDisplay.vue'
import { useI18n, useModuleI18n } from '@/i18n/composables'
import { askForConfirmation as askForConfirmationDialog, useConfirmDialog } from '@/utils/confirmDialog'

const FOLLOW_CONFIG_VALUE = '__astrbot_follow_config__'

export default {
  name: 'SessionManagementPage',
  components: {
    UmoDisplay,
  },
  setup() {
    const { t } = useI18n()
    const { tm } = useModuleI18n('features/session-management')
    const confirmDialog = useConfirmDialog()

    return {
      t,
      tm,
      confirmDialog,
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
      availablePlugins: [],
      availableKbs: [],

      // 添加规则
      addRuleDialog: false,
      availableUmos: [],
      availableUmoInfoMap: {},
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
        chat_completion: FOLLOW_CONFIG_VALUE,
        speech_to_text: FOLLOW_CONFIG_VALUE,
        text_to_speech: FOLLOW_CONFIG_VALUE,
      },

      // 插件配置
      pluginConfig: {
        enabled_plugins: [],
        disabled_plugins: [],
      },

      // 知识库配置
      kbConfig: {
        kb_ids: [],
        top_k: 5,
        enable_rerank: true,
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
      // 批量操作
      batchScope: 'selected',
      batchGroupId: null,
      batchLlmStatus: null,
      batchTtsStatus: null,
      batchChatProvider: null,
      batchTtsProvider: null,
      batchUpdating: false,

      // 分组管理
      groups: [],
      groupsLoading: false,
      groupDialog: false,
      groupDialogMode: 'create',
      editingGroup: {
        id: null,
        name: '',
        umos: [],
      },
      groupMemberDialog: false,
      groupMemberTarget: null,
      groupMemberSearch: '',
      groupSelectedSearch: '',

      // 提示信息
      snackbar: false,
      snackbarText: '',
      snackbarColor: 'success',
    }
  },

  computed: {
    headers() {
      return [
        {
          title: this.tm('table.headers.umoInfo'),
          key: 'umo_info',
          sortable: false,
          minWidth: '300px',
        },
        {
          title: this.tm('table.headers.rulesOverview'),
          key: 'rules_overview',
          sortable: false,
          minWidth: '250px',
        },
        {
          title: this.tm('table.headers.actions'),
          key: 'actions',
          sortable: false,
          minWidth: '150px',
        },
      ]
    },

    filteredRulesList() {
      // 搜索已移至服务端，直接返回 rulesList
      return this.rulesList
    },

    personaOptions() {
      return [
        { label: this.tm('persona.none'), value: null },
        ...this.availablePersonas.map((p) => ({
          label: p.name,
          value: p.name,
        })),
      ]
    },

    chatProviderOptions() {
      return [
        { label: this.tm('provider.followConfig'), value: FOLLOW_CONFIG_VALUE },
        ...this.availableChatProviders.map((p) => ({
          label: `${p.name} (${p.model})`,
          value: p.id,
        })),
      ]
    },

    sttProviderOptions() {
      return [
        { label: this.tm('provider.followConfig'), value: FOLLOW_CONFIG_VALUE },
        ...this.availableSttProviders.map((p) => ({
          label: `${p.name} (${p.model})`,
          value: p.id,
        })),
      ]
    },

    ttsProviderOptions() {
      return [
        { label: this.tm('provider.followConfig'), value: FOLLOW_CONFIG_VALUE },
        ...this.availableTtsProviders.map((p) => ({
          label: `${p.name} (${p.model})`,
          value: p.id,
        })),
      ]
    },

    batchChatProviderOptions() {
      return [
        { label: this.tm('provider.followConfig'), value: FOLLOW_CONFIG_VALUE },
        ...this.availableChatProviders.map((p) => ({
          label: `${p.name} (${p.model})`,
          value: p.id,
        })),
      ]
    },

    batchTtsProviderOptions() {
      return [
        { label: this.tm('provider.followConfig'), value: FOLLOW_CONFIG_VALUE },
        ...this.availableTtsProviders.map((p) => ({
          label: `${p.name} (${p.model})`,
          value: p.id,
        })),
      ]
    },

    pluginOptions() {
      return this.availablePlugins.map((p) => ({
        label: p.display_name || p.name,
        value: p.name,
      }))
    },

    kbOptions() {
      return this.availableKbs.map((kb) => ({
        label: `${kb.emoji || '📚'} ${kb.kb_name}`,
        value: kb.kb_id,
      }))
    },
    batchScopeOptions() {
      const options = [
        { label: this.tm('batchOperations.scopeSelected'), value: 'selected' },
        { label: this.tm('batchOperations.scopeAll'), value: 'all' },
        { label: this.tm('batchOperations.scopeGroup'), value: 'group' },
        { label: this.tm('batchOperations.scopePrivate'), value: 'private' },
      ]
      // 添加自定义分组选项
      if (this.groups.length > 0) {
        options.push({
          label: this.tm('groups.customGroupDivider'),
          value: '_divider',
          disabled: true,
        })
        this.groups.forEach((g) => {
          options.push({
            label: this.tm('groups.customGroupOption', {
              name: g.name,
              count: g.umo_count,
            }),
            value: `custom_group:${g.id}`,
          })
        })
      }
      return options
    },

    groupOptions() {
      return this.groups.map((g) => ({
        label: this.tm('groups.groupOption', {
          name: g.name,
          count: g.umo_count,
        }),
        value: g.id,
      }))
    },

    statusOptions() {
      return [
        { label: this.tm('status.enabled'), value: true },
        { label: this.tm('status.disabled'), value: false },
      ]
    },

    canApplyBatch() {
      const hasChanges = this.batchLlmStatus !== null || this.batchTtsStatus !== null || this.batchChatProvider !== null || this.batchTtsProvider !== null
      if (this.batchScope === 'selected') {
        return hasChanges && this.selectedItems.length > 0
      }
      return hasChanges
    },

    // 穿梭框：未选中的UMO列表
    unselectedUmos() {
      const selected = new Set(this.editingGroup.umos || [])
      return this.availableUmos.filter((u) => !selected.has(u))
    },

    // 穿梭框：过滤后的未选中列表
    filteredUnselectedUmos() {
      if (!this.groupMemberSearch) return this.unselectedUmos
      const search = this.groupMemberSearch.toLowerCase()
      return this.unselectedUmos.filter((u) => u.toLowerCase().includes(search))
    },

    // 穿梭框：过滤后的已选中列表
    filteredSelectedUmos() {
      if (!this.groupSelectedSearch) return this.editingGroup.umos || []
      const search = this.groupSelectedSearch.toLowerCase()
      return (this.editingGroup.umos || []).filter((u) => u.toLowerCase().includes(search))
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
      },
    },
  },

  mounted() {
    this.loadData()
    this.loadGroups()
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
        const response = await sessionApi.listRules({
          page: this.currentPage,
          page_size: this.itemsPerPage,
          search: this.searchQuery || '',
        })
        if (response.data.status === 'ok') {
          const data = response.data.data
          this.rulesList = data.rules
          this.mergeUmoInfos(data.rules)
          this.totalItems = data.total
          this.availablePersonas = data.available_personas
          this.availableChatProviders = data.available_chat_providers
          this.availableSttProviders = data.available_stt_providers
          this.availableTtsProviders = data.available_tts_providers
          this.availablePlugins = data.available_plugins || []
          this.availableKbs = data.available_kbs || []
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
        const response = await sessionApi.activeUmos()
        if (response.data.status === 'ok') {
          this.mergeUmoInfos(response.data.data.umo_infos || [])
          // 过滤掉已有规则的 umo
          const existingUmos = new Set(this.rulesList.map((r) => r.umo))
          this.availableUmos = response.data.data.umos.filter((umo) => !existingUmos.has(umo))
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
      return rules && (rules['provider_perf_chat_completion'] || rules['provider_perf_speech_to_text'] || rules['provider_perf_text_to_speech'])
    },

    parseUmoInfo(umo) {
      const parts = umo.split(':')
      return {
        umo,
        platform: parts[0] || '',
        message_type: parts[1] || '',
        session_id: parts.slice(2).join(':') || umo,
        auto_name: '',
        user_alias: '',
        display_name: umo,
      }
    },

    mergeUmoInfos(infos = []) {
      const next = { ...this.availableUmoInfoMap }
      for (const info of infos) {
        if (info?.umo) {
          next[info.umo] = { ...(next[info.umo] || {}), ...info }
        }
      }
      this.availableUmoInfoMap = next
    },

    getAvailableUmoInfo(umo) {
      return this.availableUmoInfoMap[umo] || this.parseUmoInfo(umo)
    },

    getAvailableUmoDisplayProps(umo) {
      const info = this.getAvailableUmoInfo(umo)
      return {
        umo,
        platform: info.platform,
        messageType: info.message_type,
        sessionId: info.session_id,
        autoName: info.auto_name,
        userAlias: info.user_alias,
      }
    },

    getPlatformColor(platform) {
      const colors = {
        aiocqhttp: 'blue',
        qq_official: 'purple',
        telegram: 'light-blue',
        discord: 'indigo',
        webchat: 'orange',
      }
      return colors[platform] || 'grey'
    },

    getUmoDisplayText(value) {
      const item = typeof value === 'string' ? this.getAvailableUmoInfo(value) : value
      if (!item) return ''
      const umo = item.umo || (typeof value === 'string' ? value : '')
      const aliasName = item.user_alias || item.rules?.session_service_config?.custom_name || ''
      const autoName = item.auto_name || ''
      let displayName = ''
      if (aliasName && autoName && aliasName !== autoName) {
        displayName = `${aliasName}（${autoName}）`
      } else {
        displayName = aliasName || autoName
      }
      if (displayName && umo) {
        return `${displayName} (UMO: ${umo})`
      }
      return displayName || (umo ? `UMO: ${umo}` : item.display_name || '')
    },

    getUmoSelectionText(value) {
      const item = typeof value === 'string' ? this.getAvailableUmoInfo(value) : value
      if (!item) return ''
      const umo = item.umo || (typeof value === 'string' ? value : '')
      const aliasName = item.user_alias || item.rules?.session_service_config?.custom_name || ''
      const autoName = item.auto_name || ''
      if (aliasName && autoName && aliasName !== autoName) {
        return `${aliasName}（${autoName}）`
      }
      return aliasName || autoName || umo || item.display_name || ''
    },

    buildUmoItem(umo, rules = {}) {
      return {
        ...this.getAvailableUmoInfo(umo),
        umo,
        rules,
      }
    },

    async openAddRuleDialog() {
      this.addRuleDialog = true
      this.selectedNewUmo = null
      await this.loadUmos()
    },

    createNewRule() {
      if (!this.selectedNewUmo) return

      // 创建一个新的规则项并打开编辑器
      const newItem = this.buildUmoItem(this.selectedNewUmo)

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
        chat_completion: this.editingRules['provider_perf_chat_completion'] || FOLLOW_CONFIG_VALUE,
        speech_to_text: this.editingRules['provider_perf_speech_to_text'] || FOLLOW_CONFIG_VALUE,
        text_to_speech: this.editingRules['provider_perf_text_to_speech'] || FOLLOW_CONFIG_VALUE,
      }

      // 初始化插件配置
      const pluginCfg = this.editingRules.session_plugin_config || {}
      this.pluginConfig = {
        enabled_plugins: pluginCfg.enabled_plugins || [],
        disabled_plugins: pluginCfg.disabled_plugins || [],
      }

      // 初始化知识库配置
      const kbCfg = this.editingRules.kb_config || {}
      this.kbConfig = {
        kb_ids: kbCfg.kb_ids || [],
        top_k: kbCfg.top_k ?? 5,
        enable_rerank: kbCfg.enable_rerank !== false,
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

        const response = await sessionApi.upsertRule({
          umo: this.selectedUmo.umo,
          rule_key: 'session_service_config',
          rule_value: config,
        })

        if (response.data.status === 'ok') {
          this.showSuccess(this.tm('messages.saveSuccess'))
          this.editingRules.session_service_config = config

          // 更新或添加到列表
          let item = this.rulesList.find((u) => u.umo === this.selectedUmo.umo)
          if (item) {
            item.rules = { ...item.rules, session_service_config: config }
          } else {
            // 新规则，添加到列表
            this.rulesList.push(
              this.buildUmoItem(this.selectedUmo.umo, {
                session_service_config: config,
              }),
            )
          }
        } else {
          this.showError(response.data.message || this.tm('messages.saveError'))
        }
      } catch (error) {
        this.showError(error.response?.data?.message || this.tm('messages.saveError'))
      }
      this.saving = false
    },

    async saveProviderConfig() {
      if (!this.selectedUmo) return

      this.saving = true
      try {
        const updateTasks = []
        const deleteTasks = []
        const providerTypes = ['chat_completion', 'speech_to_text', 'text_to_speech']

        for (const type of providerTypes) {
          const value = this.providerConfig[type]
          if (value && value !== FOLLOW_CONFIG_VALUE) {
            // 有值时更新
            updateTasks.push(
              sessionApi.upsertRule({
                umo: this.selectedUmo.umo,
                rule_key: `provider_perf_${type}`,
                rule_value: value,
              }),
            )
          } else if (this.editingRules[`provider_perf_${type}`]) {
            // 选择了"跟随配置文件" (__astrbot_follow_config__) 且之前有配置，则删除
            deleteTasks.push(
              sessionApi.deleteRules({
                umo: this.selectedUmo.umo,
                rule_key: `provider_perf_${type}`,
              }),
            )
          }
        }

        const allTasks = [...updateTasks, ...deleteTasks]
        if (allTasks.length > 0) {
          await Promise.all(allTasks)
          this.showSuccess(this.tm('messages.saveSuccess'))

          // 更新或添加到列表
          let item = this.rulesList.find((u) => u.umo === this.selectedUmo.umo)
          if (!item) {
            item = this.buildUmoItem(this.selectedUmo.umo)
            this.rulesList.push(item)
          }
          for (const type of providerTypes) {
            const val = this.providerConfig[type]
            if (val && val !== FOLLOW_CONFIG_VALUE) {
              item.rules[`provider_perf_${type}`] = val
              this.editingRules[`provider_perf_${type}`] = val
            } else {
              // 删除本地数据
              delete item.rules[`provider_perf_${type}`]
              delete this.editingRules[`provider_perf_${type}`]
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

    async savePluginConfig() {
      if (!this.selectedUmo) return

      this.saving = true
      try {
        const config = {
          enabled_plugins: this.pluginConfig.enabled_plugins,
          disabled_plugins: this.pluginConfig.disabled_plugins,
        }

        // 如果两个列表都为空，删除配置
        if (config.enabled_plugins.length === 0 && config.disabled_plugins.length === 0) {
          if (this.editingRules.session_plugin_config) {
            await sessionApi.deleteRules({
              umo: this.selectedUmo.umo,
              rule_key: 'session_plugin_config',
            })
            delete this.editingRules.session_plugin_config
            let item = this.rulesList.find((u) => u.umo === this.selectedUmo.umo)
            if (item) delete item.rules.session_plugin_config
          }
          this.showSuccess(this.tm('messages.saveSuccess'))
        } else {
          const response = await sessionApi.upsertRule({
            umo: this.selectedUmo.umo,
            rule_key: 'session_plugin_config',
            rule_value: config,
          })

          if (response.data.status === 'ok') {
            this.showSuccess(this.tm('messages.saveSuccess'))
            this.editingRules.session_plugin_config = config

            let item = this.rulesList.find((u) => u.umo === this.selectedUmo.umo)
            if (item) {
              item.rules.session_plugin_config = config
            } else {
              this.rulesList.push(
                this.buildUmoItem(this.selectedUmo.umo, {
                  session_plugin_config: config,
                }),
              )
            }
          } else {
            this.showError(response.data.message || this.tm('messages.saveError'))
          }
        }
      } catch (error) {
        this.showError(error.response?.data?.message || this.tm('messages.saveError'))
      }
      this.saving = false
    },

    async saveKbConfig() {
      if (!this.selectedUmo) return

      this.saving = true
      try {
        const config = {
          kb_ids: this.kbConfig.kb_ids,
          top_k: this.kbConfig.top_k,
          enable_rerank: this.kbConfig.enable_rerank,
        }

        // 如果 kb_ids 为空，删除配置
        if (config.kb_ids.length === 0) {
          if (this.editingRules.kb_config) {
            await sessionApi.deleteRules({
              umo: this.selectedUmo.umo,
              rule_key: 'kb_config',
            })
            delete this.editingRules.kb_config
            let item = this.rulesList.find((u) => u.umo === this.selectedUmo.umo)
            if (item) delete item.rules.kb_config
          }
          this.showSuccess(this.tm('messages.saveSuccess'))
        } else {
          const response = await sessionApi.upsertRule({
            umo: this.selectedUmo.umo,
            rule_key: 'kb_config',
            rule_value: config,
          })

          if (response.data.status === 'ok') {
            this.showSuccess(this.tm('messages.saveSuccess'))
            this.editingRules.kb_config = config

            let item = this.rulesList.find((u) => u.umo === this.selectedUmo.umo)
            if (item) {
              item.rules.kb_config = config
            } else {
              this.rulesList.push(
                this.buildUmoItem(this.selectedUmo.umo, {
                  kb_config: config,
                }),
              )
            }
          } else {
            this.showError(response.data.message || this.tm('messages.saveError'))
          }
        }
      } catch (error) {
        this.showError(error.response?.data?.message || this.tm('messages.saveError'))
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
        const response = await sessionApi.deleteRules({
          umo: this.deleteTarget.umo,
        })

        if (response.data.status === 'ok') {
          this.showSuccess(this.tm('messages.deleteSuccess'))
          // 从列表中移除
          const index = this.rulesList.findIndex((u) => u.umo === this.deleteTarget.umo)
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
        const umos = this.selectedItems.map((item) => item.umo)
        const response = await sessionApi.deleteRules({
          umos: umos,
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

        const response = await sessionApi.upsertRule({
          umo: this.quickEditNameTarget.umo,
          rule_key: 'session_service_config',
          rule_value: config,
        })

        if (response.data.status === 'ok') {
          this.showSuccess(this.tm('messages.saveSuccess'))

          // 更新或添加到列表
          let item = this.rulesList.find((u) => u.umo === this.quickEditNameTarget.umo)
          if (item) {
            if (!item.rules) item.rules = {}
            item.rules.session_service_config = config
          } else {
            // 新规则，添加到列表
            this.rulesList.push(
              this.buildUmoItem(this.quickEditNameTarget.umo, {
                session_service_config: config,
              }),
            )
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

    async applyBatchChanges() {
      this.batchUpdating = true
      try {
        let scope = this.batchScope
        let groupId = null
        let umos = []

        // 处理自定义分组
        if (scope.startsWith('custom_group:')) {
          groupId = scope.split(':')[1]
          scope = 'custom_group'
        }

        if (scope === 'selected') {
          umos = this.selectedItems.map((item) => item.umo)
          if (umos.length === 0) {
            this.showError(this.tm('messages.selectSessionsFirst'))
            this.batchUpdating = false
            return
          }
        }

        const tasks = []

        if (this.batchLlmStatus !== null || this.batchTtsStatus !== null) {
          const serviceData = { scope, umos, group_id: groupId }
          if (this.batchLlmStatus !== null) {
            serviceData.llm_enabled = this.batchLlmStatus
          }
          if (this.batchTtsStatus !== null) {
            serviceData.tts_enabled = this.batchTtsStatus
          }
          tasks.push(sessionApi.batchUpdateService(serviceData))
        }

        if (this.batchChatProvider !== null) {
          if (this.batchChatProvider === FOLLOW_CONFIG_VALUE) {
            tasks.push(
              sessionApi.deleteRules({
                scope,
                umos,
                group_id: groupId,
                rule_key: 'provider_perf_chat_completion',
              }),
            )
          } else {
            tasks.push(
              sessionApi.batchUpdateProvider({
                scope,
                umos,
                group_id: groupId,
                provider_type: 'chat_completion',
                provider_id: this.batchChatProvider,
              }),
            )
          }
        }

        if (this.batchTtsProvider !== null) {
          if (this.batchTtsProvider === FOLLOW_CONFIG_VALUE) {
            tasks.push(
              sessionApi.deleteRules({
                scope,
                umos,
                group_id: groupId,
                rule_key: 'provider_perf_text_to_speech',
              }),
            )
          } else {
            tasks.push(
              sessionApi.batchUpdateProvider({
                scope,
                umos,
                group_id: groupId,
                provider_type: 'text_to_speech',
                provider_id: this.batchTtsProvider,
              }),
            )
          }
        }

        if (tasks.length === 0) {
          this.showError(this.tm('messages.selectAtLeastOneConfig'))
          this.batchUpdating = false
          return
        }

        const results = await Promise.all(tasks)
        const allOk = results.every((r) => r.data.status === 'ok')

        if (allOk) {
          this.showSuccess(this.tm('messages.batchUpdateSuccess'))
          this.batchLlmStatus = null
          this.batchTtsStatus = null
          this.batchChatProvider = null
          this.batchTtsProvider = null
          await this.loadData()
        } else {
          this.showError(this.tm('messages.partialUpdateFailed'))
        }
      } catch (error) {
        this.showError(error.response?.data?.message || this.tm('messages.batchUpdateError'))
      }
      this.batchUpdating = false
    },

    // ==================== 分组管理方法 ====================

    async loadGroups() {
      this.groupsLoading = true
      try {
        const response = await sessionApi.listGroups()
        if (response.data.status === 'ok') {
          this.groups = response.data.data.groups || []
        }
      } catch (error) {
        console.error('加载分组失败:', error)
      }
      this.groupsLoading = false
    },

    async loadAvailableUmos() {
      if (this.availableUmos.length > 0) return
      this.loadingUmos = true
      try {
        const response = await sessionApi.activeUmos()
        if (response.data.status === 'ok') {
          this.mergeUmoInfos(response.data.data.umo_infos || [])
          this.availableUmos = response.data.data.umos || []
        }
      } catch (error) {
        console.error('加载会话列表失败:', error)
      }
      this.loadingUmos = false
    },

    openCreateGroupDialog() {
      this.groupDialogMode = 'create'
      this.editingGroup = { id: null, name: '', umos: [] }
      this.groupMemberSearch = ''
      this.groupSelectedSearch = ''
      this.groupDialog = true
    },

    openEditGroupDialog(group) {
      this.groupDialogMode = 'edit'
      this.editingGroup = { ...group, umos: [...(group.umos || [])] }
      this.groupMemberSearch = ''
      this.groupSelectedSearch = ''
      this.groupDialog = true
    },

    // 穿梭框操作方法
    addToGroup(umo) {
      if (!this.editingGroup.umos.includes(umo)) {
        this.editingGroup.umos.push(umo)
      }
    },

    removeFromGroup(umo) {
      const idx = this.editingGroup.umos.indexOf(umo)
      if (idx > -1) {
        this.editingGroup.umos.splice(idx, 1)
      }
    },

    addAllToGroup() {
      this.unselectedUmos.forEach((umo) => {
        if (!this.editingGroup.umos.includes(umo)) {
          this.editingGroup.umos.push(umo)
        }
      })
    },

    removeAllFromGroup() {
      this.editingGroup.umos = []
    },

    async saveGroup() {
      if (!this.editingGroup.name.trim()) {
        this.showError(this.tm('messages.groupNameRequired'))
        return
      }

      try {
        let response
        if (this.groupDialogMode === 'create') {
          response = await sessionApi.createGroup({
            name: this.editingGroup.name,
            umos: this.editingGroup.umos,
          })
        } else {
          response = await sessionApi.updateGroup(this.editingGroup.id, {
            name: this.editingGroup.name,
            umos: this.editingGroup.umos,
          })
        }

        if (response.data.status === 'ok') {
          this.showSuccess(response.data.data.message)
          this.groupDialog = false
          await this.loadGroups()
        } else {
          this.showError(response.data.message)
        }
      } catch (error) {
        this.showError(error.response?.data?.message || this.tm('messages.saveGroupError'))
      }
    },

    async deleteGroup(group) {
      const message = this.tm('groups.deleteConfirm', { name: group.name })
      if (!(await askForConfirmationDialog(message, this.confirmDialog))) return

      try {
        const response = await sessionApi.deleteGroup(group.id)
        if (response.data.status === 'ok') {
          this.showSuccess(response.data.data.message)
          await this.loadGroups()
        } else {
          this.showError(response.data.message)
        }
      } catch (error) {
        this.showError(error.response?.data?.message || this.tm('messages.deleteGroupError'))
      }
    },

    openGroupMemberDialog(group) {
      this.groupMemberTarget = { ...group }
      this.groupMemberDialog = true
    },

    async addSelectedToGroup(groupId) {
      if (this.selectedItems.length === 0) {
        this.showError(this.tm('messages.selectSessionsToAddFirst'))
        return
      }

      try {
        const response = await sessionApi.updateGroup(groupId, {
          add_umos: this.selectedItems.map((item) => item.umo),
        })
        if (response.data.status === 'ok') {
          this.showSuccess(
            this.tm('messages.addToGroupSuccess', {
              count: this.selectedItems.length,
            }),
          )
          await this.loadGroups()
        } else {
          this.showError(response.data.message)
        }
      } catch (error) {
        this.showError(error.response?.data?.message || this.tm('messages.addToGroupError'))
      }
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

.transfer-list {
  max-height: 280px;
  overflow-y: auto;
  border: 1px solid rgba(0, 0, 0, 0.12);
  border-radius: 4px;
}

.transfer-item {
  cursor: pointer;
  transition: background-color 0.15s;
  min-height: 44px !important;
  padding-top: 3px !important;
  padding-bottom: 3px !important;
}

.transfer-item:hover {
  background-color: rgba(0, 0, 0, 0.04);
}

.transfer-item :deep(.v-list-item__append) {
  align-self: center;
  margin-inline-start: auto;
  padding-inline-start: 12px;
}

.transfer-item :deep(.v-list-item__prepend) {
  align-self: center;
}

.transfer-item :deep(.v-list-item__content) {
  min-width: 0;
  padding-inline-end: 12px;
}

.transfer-item :deep(.v-list-item-title) {
  line-height: 1.2;
}

.umo-list-platform {
  max-width: 92px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.umo-selection-chip {
  max-width: 100%;
}

.umo-selection-chip :deep(.v-chip__content) {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
