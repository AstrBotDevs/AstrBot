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
      <v-dialog v-model="ruleDialog" max-width="650" scrollable>
        <v-card v-if="selectedUmo" class="d-flex flex-column" height="680">
          <v-card-title class="text-h3 pa-4 pb-0 pl-6 d-flex align-center">
            <span>{{ tm('ruleEditor.title') }}</span>
            <v-chip size="x-small" class="ml-2 font-weight-regular" color="primary" variant="tonal">
              {{ tm('ruleEditor.overrideCount', { count: ruleOverrideCount }) }}
            </v-chip>
            <v-spacer></v-spacer>
            <v-btn icon="mdi-close" variant="text" @click="closeRuleEditor"></v-btn>
          </v-card-title>

          <v-card-text class="pa-0 overflow-y-auto">
            <div class="px-6 py-4">
              <div class="rule-editor-session mb-4">
                <UmoDisplay v-bind="getAvailableUmoDisplayProps(selectedUmo.umo)" compact />
              </div>

              <div class="setting-section">
                <div class="setting-section-title">{{ tm('ruleEditor.note.title') }}</div>
                <div class="setting-row">
                  <div class="setting-meta">
                    <div class="setting-label">{{ tm('ruleEditor.serviceConfig.customName') }}</div>
                    <div class="setting-path">{{ tm('ruleEditor.note.source') }}</div>
                  </div>
                  <v-text-field v-model="serviceConfig.custom_name" variant="outlined" density="compact" hide-details clearable class="setting-control" />
                </div>
                <div class="setting-row">
                  <div class="setting-meta">
                    <div class="setting-label">{{ tm('ruleEditor.serviceConfig.sessionEnabled') }}</div>
                    <div class="setting-hint">{{ tm('ruleEditor.serviceConfig.sessionEnabledHint') }}</div>
                  </div>
                  <v-switch v-model="serviceConfig.session_enabled" color="primary" density="compact" hide-details inset class="setting-switch" />
                </div>
              </div>

              <div class="setting-add-row">
                <v-select
                  v-model="selectedOverrideKey"
                  :items="availableOverrideOptions"
                  item-title="label"
                  item-value="value"
                  :label="tm('ruleEditor.addOverride.select')"
                  variant="outlined"
                  density="compact"
                  hide-details
                  :disabled="availableOverrideOptions.length === 0"
                  class="setting-control"
                >
                  <template #item="{ props, item }">
                    <v-list-item v-bind="props">
                      <template #title>{{ item.raw.label }}</template>
                      <template #subtitle>
                        <span v-if="item.raw.hint" class="override-option-hint">{{ item.raw.hint }}</span>
                      </template>
                    </v-list-item>
                  </template>
                  <template #selection="{ item }">
                    <div class="override-selection">
                      <span>{{ item.raw.label }}</span>
                      <span v-if="item.raw.hint" class="override-selection-hint">{{ item.raw.hint }}</span>
                    </div>
                  </template>
                </v-select>
                <v-btn color="primary" variant="tonal" :disabled="!selectedOverrideKey" @click="addOverride">
                  {{ tm('ruleEditor.addOverride.button') }}
                </v-btn>
              </div>

              <div v-if="activeOverrideKeys.length === 0" class="setting-empty-overrides">
                {{ tm('ruleEditor.addOverride.empty') }}
              </div>

              <div v-if="hasAnyOverride(aiOverrideKeys)" class="setting-section">
                <div class="setting-section-title">{{ tm('ruleEditor.groups.ai') }}</div>
                <div v-if="hasOverride('llm_enabled')" class="setting-row">
                  <div class="setting-meta">
                    <div class="setting-label">{{ getOverrideLabel('llm_enabled') }}</div>
                    <div v-if="getOverrideHint('llm_enabled')" class="setting-hint">{{ getOverrideHint('llm_enabled') }}</div>
                  </div>
                  <div class="setting-control-with-action">
                    <ConfigItemRenderer :model-value="getOverrideValue('llm_enabled')" :item-meta="getOverrideItemMeta('llm_enabled')" :config-key="getOverrideConfigPath('llm_enabled')" class="setting-control-fill" @update:model-value="setOverrideValue('llm_enabled', $event)" />
                    <v-btn icon size="small" variant="text" class="setting-remove-btn" @click="removeOverride('llm_enabled')">
                      <v-icon>mdi-close</v-icon>
                      <v-tooltip activator="parent" location="top">{{ tm('ruleEditor.addOverride.remove') }}</v-tooltip>
                    </v-btn>
                  </div>
                </div>
                <div v-if="hasOverride('chat_completion')" class="setting-row">
                  <div class="setting-meta">
                    <div class="setting-label">{{ getOverrideLabel('chat_completion') }}</div>
                    <div v-if="getOverrideHint('chat_completion')" class="setting-hint">{{ getOverrideHint('chat_completion') }}</div>
                  </div>
                  <div class="setting-control-with-action">
                    <ConfigItemRenderer :model-value="getOverrideValue('chat_completion')" :item-meta="getOverrideItemMeta('chat_completion')" :config-key="getOverrideConfigPath('chat_completion')" class="setting-control-fill" @update:model-value="setOverrideValue('chat_completion', $event)" />
                    <v-btn icon size="small" variant="text" class="setting-remove-btn" @click="removeOverride('chat_completion')">
                      <v-icon>mdi-close</v-icon>
                      <v-tooltip activator="parent" location="top">{{ tm('ruleEditor.addOverride.remove') }}</v-tooltip>
                    </v-btn>
                  </div>
                </div>
                <div v-if="hasOverride('tts_enabled')" class="setting-row">
                  <div class="setting-meta">
                    <div class="setting-label">{{ getOverrideLabel('tts_enabled') }}</div>
                    <div v-if="getOverrideHint('tts_enabled')" class="setting-hint">{{ getOverrideHint('tts_enabled') }}</div>
                  </div>
                  <div class="setting-control-with-action">
                    <ConfigItemRenderer :model-value="getOverrideValue('tts_enabled')" :item-meta="getOverrideItemMeta('tts_enabled')" :config-key="getOverrideConfigPath('tts_enabled')" class="setting-control-fill" @update:model-value="setOverrideValue('tts_enabled', $event)" />
                    <v-btn icon size="small" variant="text" class="setting-remove-btn" @click="removeOverride('tts_enabled')">
                      <v-icon>mdi-close</v-icon>
                      <v-tooltip activator="parent" location="top">{{ tm('ruleEditor.addOverride.remove') }}</v-tooltip>
                    </v-btn>
                  </div>
                </div>
                <div v-if="hasOverride('text_to_speech')" class="setting-row">
                  <div class="setting-meta">
                    <div class="setting-label">{{ getOverrideLabel('text_to_speech') }}</div>
                    <div v-if="getOverrideHint('text_to_speech')" class="setting-hint">{{ getOverrideHint('text_to_speech') }}</div>
                  </div>
                  <div class="setting-control-with-action">
                    <ConfigItemRenderer :model-value="getOverrideValue('text_to_speech')" :item-meta="getOverrideItemMeta('text_to_speech')" :config-key="getOverrideConfigPath('text_to_speech')" class="setting-control-fill" @update:model-value="setOverrideValue('text_to_speech', $event)" />
                    <v-btn icon size="small" variant="text" class="setting-remove-btn" @click="removeOverride('text_to_speech')">
                      <v-icon>mdi-close</v-icon>
                      <v-tooltip activator="parent" location="top">{{ tm('ruleEditor.addOverride.remove') }}</v-tooltip>
                    </v-btn>
                  </div>
                </div>
                <div v-if="hasOverride('speech_to_text')" class="setting-row">
                  <div class="setting-meta">
                    <div class="setting-label">{{ getOverrideLabel('speech_to_text') }}</div>
                    <div v-if="getOverrideHint('speech_to_text')" class="setting-hint">{{ getOverrideHint('speech_to_text') }}</div>
                  </div>
                  <div class="setting-control-with-action">
                    <ConfigItemRenderer :model-value="getOverrideValue('speech_to_text')" :item-meta="getOverrideItemMeta('speech_to_text')" :config-key="getOverrideConfigPath('speech_to_text')" class="setting-control-fill" @update:model-value="setOverrideValue('speech_to_text', $event)" />
                    <v-btn icon size="small" variant="text" class="setting-remove-btn" @click="removeOverride('speech_to_text')">
                      <v-icon>mdi-close</v-icon>
                      <v-tooltip activator="parent" location="top">{{ tm('ruleEditor.addOverride.remove') }}</v-tooltip>
                    </v-btn>
                  </div>
                </div>
                <div v-if="hasOverride('persona_id')" class="setting-row">
                  <div class="setting-meta">
                    <div class="setting-label">{{ getOverrideLabel('persona_id') }}</div>
                    <div v-if="getOverrideHint('persona_id')" class="setting-hint">{{ getOverrideHint('persona_id') }}</div>
                  </div>
                  <div class="setting-control-with-action">
                    <ConfigItemRenderer :model-value="getOverrideValue('persona_id')" :item-meta="getOverrideItemMeta('persona_id')" :config-key="getOverrideConfigPath('persona_id')" class="setting-control-fill" @update:model-value="setOverrideValue('persona_id', $event)" />
                    <v-btn icon size="small" variant="text" class="setting-remove-btn" @click="removeOverride('persona_id')">
                      <v-icon>mdi-close</v-icon>
                      <v-tooltip activator="parent" location="top">{{ tm('ruleEditor.addOverride.remove') }}</v-tooltip>
                    </v-btn>
                  </div>
                </div>
                <div v-if="hasOverride('kb_names')" class="setting-row">
                  <div class="setting-meta">
                    <div class="setting-label">{{ getOverrideLabel('kb_names') }}</div>
                    <div v-if="getOverrideHint('kb_names')" class="setting-hint">{{ getOverrideHint('kb_names') }}</div>
                  </div>
                  <div class="setting-control-with-action">
                    <ConfigItemRenderer :model-value="getOverrideValue('kb_names')" :item-meta="getOverrideItemMeta('kb_names')" :config-key="getOverrideConfigPath('kb_names')" class="setting-control-fill" @update:model-value="setOverrideValue('kb_names', $event)" />
                    <v-btn icon size="small" variant="text" class="setting-remove-btn" @click="removeOverride('kb_names')">
                      <v-icon>mdi-close</v-icon>
                      <v-tooltip activator="parent" location="top">{{ tm('ruleEditor.addOverride.remove') }}</v-tooltip>
                    </v-btn>
                  </div>
                </div>
                <div v-if="hasOverride('kb_top_k')" class="setting-row">
                  <div class="setting-meta">
                    <div class="setting-label">{{ getOverrideLabel('kb_top_k') }}</div>
                    <div v-if="getOverrideHint('kb_top_k')" class="setting-hint">{{ getOverrideHint('kb_top_k') }}</div>
                  </div>
                  <div class="setting-control-with-action">
                    <ConfigItemRenderer :model-value="getOverrideValue('kb_top_k')" :item-meta="getOverrideItemMeta('kb_top_k')" :config-key="getOverrideConfigPath('kb_top_k')" class="setting-control-fill setting-control-narrow" @update:model-value="setOverrideValue('kb_top_k', $event)" />
                    <v-btn icon size="small" variant="text" class="setting-remove-btn" @click="removeOverride('kb_top_k')">
                      <v-icon>mdi-close</v-icon>
                      <v-tooltip activator="parent" location="top">{{ tm('ruleEditor.addOverride.remove') }}</v-tooltip>
                    </v-btn>
                  </div>
                </div>
              </div>

              <div v-if="hasAnyOverride(pluginOverrideKeys)" class="setting-section">
                <div class="setting-section-title">{{ tm('ruleEditor.pluginConfig.title') }}</div>
                <div v-if="hasOverride('disabled_plugins')" class="setting-row">
                  <div class="setting-meta">
                    <div class="setting-label">{{ getOverrideLabel('disabled_plugins') }}</div>
                    <div v-if="getOverrideHint('disabled_plugins')" class="setting-hint">{{ getOverrideHint('disabled_plugins') }}</div>
                  </div>
                  <div class="setting-control-with-action">
                    <ConfigItemRenderer :model-value="getOverrideValue('disabled_plugins')" :item-meta="getOverrideItemMeta('disabled_plugins')" :config-key="getOverrideConfigPath('disabled_plugins')" class="setting-control-fill" @update:model-value="setOverrideValue('disabled_plugins', $event)" />
                    <v-btn icon size="small" variant="text" class="setting-remove-btn" @click="removeOverride('disabled_plugins')">
                      <v-icon>mdi-close</v-icon>
                      <v-tooltip activator="parent" location="top">{{ tm('ruleEditor.addOverride.remove') }}</v-tooltip>
                    </v-btn>
                  </div>
                </div>
              </div>

            </div>
          </v-card-text>
          <v-card-actions class="px-6 py-3 border-t">
            <v-spacer></v-spacer>
            <v-btn variant="text" @click="closeRuleEditor">{{ tm('buttons.cancel') }}</v-btn>
            <v-btn color="primary" variant="tonal" @click="saveRuleEditor" :loading="saving">
              {{ tm('buttons.save') }}
            </v-btn>
          </v-card-actions>
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
      <v-snackbar v-model="snackbar" :timeout="3000" elevation="24" :color="snackbarColor" location="top">
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
import { providerApi, sessionApi } from '@/api/v1'
import ConfigItemRenderer from '@/components/shared/ConfigItemRenderer.vue'
import UmoDisplay from '@/components/shared/UmoDisplay.vue'
import { useI18n, useModuleI18n } from '@/i18n/composables'
import { askForConfirmation as askForConfirmationDialog, useConfirmDialog } from '@/utils/confirmDialog'

const FOLLOW_CONFIG_VALUE = '__astrbot_follow_config__'

export default {
  name: 'SessionManagementPage',
  components: {
    ConfigItemRenderer,
    UmoDisplay,
  },
  setup() {
    const { t } = useI18n()
    const { tm } = useModuleI18n('features/session-management')
    const { tm: tmConfig, getRaw: getConfigRaw } = useModuleI18n('features/config-metadata')
    const confirmDialog = useConfirmDialog()

    return {
      t,
      tm,
      tmConfig,
      getConfigRaw,
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
      availableChatProviders: [],

      // 添加规则
      addRuleDialog: false,
      availableUmos: [],
      availableUmoInfoMap: {},
      selectedNewUmo: null,

      // 规则编辑
      ruleDialog: false,
      selectedUmo: null,
      editingRules: {},
      activeOverrideKeys: [],
      selectedOverrideKey: '',

      // 服务配置
      serviceConfig: {
        session_enabled: true,
        llm_enabled: true,
        tts_enabled: true,
        custom_name: '',
        persona_id: '',
      },

      // Provider 配置
      providerConfig: {
        chat_completion: '',
        speech_to_text: '',
        text_to_speech: '',
      },

      // 插件配置
      pluginConfig: {
        enabled_plugins: [],
        disabled_plugins: [],
      },

      // 知识库配置
      kbConfig: {
        kb_names: [],
        top_k: 5,
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

    batchChatProviderOptions() {
      return [
        { label: this.tm('provider.followConfig'), value: FOLLOW_CONFIG_VALUE },
        ...this.availableChatProviders.map((p) => ({
          label: `${p.name} (${p.model})`,
          value: p.id,
        })),
      ]
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

    aiOverrideKeys() {
      return ['llm_enabled', 'chat_completion', 'tts_enabled', 'text_to_speech', 'speech_to_text', 'persona_id', 'kb_names', 'kb_top_k']
    },

    pluginOverrideKeys() {
      return ['disabled_plugins']
    },

    overrideOptions() {
      const configText = (key) => (this.getConfigRaw(key) ? this.tmConfig(key) : '')
      return [
        {
          label: this.tm('ruleEditor.serviceConfig.llmEnabled'),
          value: 'llm_enabled',
          path: 'provider_settings.enable',
          hint: configText('ai_group.agent_runner.provider_settings.enable.hint'),
          meta: { type: 'bool' },
        },
        {
          label: this.tm('ruleEditor.providerConfig.chatProvider'),
          value: 'chat_completion',
          path: 'provider_settings.default_provider_id',
          hint: configText('ai_group.ai.provider_settings.default_provider_id.hint'),
          meta: { type: 'string', _special: 'select_provider' },
        },
        {
          label: this.tm('ruleEditor.serviceConfig.ttsEnabled'),
          value: 'tts_enabled',
          path: 'provider_tts_settings.enable',
          hint: configText('ai_group.ai.provider_tts_settings.enable.hint'),
          meta: { type: 'bool' },
        },
        {
          label: this.tm('ruleEditor.providerConfig.ttsProvider'),
          value: 'text_to_speech',
          path: 'provider_tts_settings.provider_id',
          hint: configText('ai_group.ai.provider_tts_settings.provider_id.hint'),
          meta: { type: 'string', _special: 'select_provider_tts' },
        },
        {
          label: this.tm('ruleEditor.providerConfig.sttProvider'),
          value: 'speech_to_text',
          path: 'provider_stt_settings.provider_id',
          hint: configText('ai_group.ai.provider_stt_settings.provider_id.hint'),
          meta: { type: 'string', _special: 'select_provider_stt' },
        },
        {
          label: this.tm('ruleEditor.personaConfig.selectPersona'),
          value: 'persona_id',
          path: 'provider_settings.default_personality',
          hint: configText('ai_group.persona.provider_settings.default_personality.hint'),
          meta: { type: 'string', _special: 'select_persona' },
        },
        {
          label: this.tm('ruleEditor.kbConfig.selectKbs'),
          value: 'kb_names',
          path: 'kb_names',
          hint: configText('ai_group.knowledgebase.kb_names.hint'),
          meta: { type: 'list', items: { type: 'string' }, _special: 'select_knowledgebase' },
        },
        {
          label: this.tm('ruleEditor.kbConfig.topK'),
          value: 'kb_top_k',
          path: 'kb_final_top_k',
          hint: configText('ai_group.knowledgebase.kb_final_top_k.hint'),
          meta: { type: 'int', default: 5 },
        },
        {
          label: this.tm('ruleEditor.pluginConfig.disabledPlugins'),
          value: 'disabled_plugins',
          path: 'plugin_disabled_set',
          hint: configText('plugin_group.plugin.plugin_disabled_set.hint'),
          meta: { type: 'bool', _special: 'select_plugin_set' },
        },
      ]
    },

    availableOverrideOptions() {
      return this.overrideOptions.filter((option) => !this.activeOverrideKeys.includes(option.value))
    },

    ruleOverrideCount() {
      const rules = this.editingRules || {}
      const serviceConfig = rules.session_service_config || {}
      let count = 0
      for (const key of ['session_enabled', 'llm_enabled', 'tts_enabled', 'persona_id']) {
        if (Object.prototype.hasOwnProperty.call(serviceConfig, key)) count += 1
      }
      for (const key of ['provider_perf_chat_completion', 'provider_perf_speech_to_text', 'provider_perf_text_to_speech']) {
        if (Object.prototype.hasOwnProperty.call(rules, key)) count += 1
      }
      const pluginConfig = rules.session_plugin_config || {}
      if (Object.prototype.hasOwnProperty.call(pluginConfig, 'disabled_plugins')) count += 1
      const kbConfig = rules.kb_config || {}
      if (Object.prototype.hasOwnProperty.call(kbConfig, 'kb_names') || Object.prototype.hasOwnProperty.call(kbConfig, 'kb_ids')) count += 1
      if (Object.prototype.hasOwnProperty.call(kbConfig, 'top_k')) count += 1
      return count
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
    const routeSearch = this.$route?.query?.search
    if (typeof routeSearch === 'string' && routeSearch.trim()) {
      this.searchQuery = routeSearch.trim()
    }
    this.loadData()
    this.loadGroups()
    this.loadBatchProviders()
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
        const response = await sessionApi.listConfigOverrides({
          page: this.currentPage,
          page_size: this.itemsPerPage,
          search: this.searchQuery || '',
        })
        if (response.data.status === 'ok') {
          const data = response.data.data
          this.rulesList = data.rules
          this.mergeUmoInfos(data.rules)
          this.totalItems = data.total
        } else {
          this.showError(response.data.message || this.tm('messages.loadError'))
        }
      } catch (error) {
        this.showError(error.response?.data?.message || this.tm('messages.loadError'))
      }
      this.loading = false
    },

    async loadBatchProviders() {
      try {
        const response = await providerApi.listByProviderType('chat_completion')
        if (response.data.status === 'ok') {
          this.availableChatProviders = response.data.data || []
        }
      } catch (error) {
        this.availableChatProviders = []
      }
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
      return rules && (
        Object.prototype.hasOwnProperty.call(rules, 'provider_perf_chat_completion')
        || Object.prototype.hasOwnProperty.call(rules, 'provider_perf_speech_to_text')
        || Object.prototype.hasOwnProperty.call(rules, 'provider_perf_text_to_speech')
      )
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

    hasOverride(key) {
      return this.activeOverrideKeys.includes(key)
    },

    hasAnyOverride(keys) {
      return keys.some((key) => this.activeOverrideKeys.includes(key))
    },

    getOverrideDefinition(key) {
      return this.overrideOptions.find((option) => option.value === key) || {}
    },

    getOverrideLabel(key) {
      return this.getOverrideDefinition(key).label || key
    },

    getOverrideHint(key) {
      return this.getOverrideDefinition(key).hint || ''
    },

    getOverrideConfigPath(key) {
      return this.getOverrideDefinition(key).path || key
    },

    getOverrideItemMeta(key) {
      return this.getOverrideDefinition(key).meta || {}
    },

    getOverrideValue(key) {
      if (key === 'llm_enabled') return this.serviceConfig.llm_enabled
      if (key === 'tts_enabled') return this.serviceConfig.tts_enabled
      if (key === 'persona_id') return this.serviceConfig.persona_id
      if (key === 'chat_completion') return this.providerConfig.chat_completion
      if (key === 'speech_to_text') return this.providerConfig.speech_to_text
      if (key === 'text_to_speech') return this.providerConfig.text_to_speech
      if (key === 'disabled_plugins') return this.pluginConfig.disabled_plugins
      if (key === 'kb_names') return this.kbConfig.kb_names
      if (key === 'kb_top_k') return this.kbConfig.top_k
      return null
    },

    setOverrideValue(key, value) {
      if (key === 'llm_enabled') this.serviceConfig.llm_enabled = Boolean(value)
      if (key === 'tts_enabled') this.serviceConfig.tts_enabled = Boolean(value)
      if (key === 'persona_id') this.serviceConfig.persona_id = value || ''
      if (key === 'chat_completion') this.providerConfig.chat_completion = value || ''
      if (key === 'speech_to_text') this.providerConfig.speech_to_text = value || ''
      if (key === 'text_to_speech') this.providerConfig.text_to_speech = value || ''
      if (key === 'disabled_plugins') this.pluginConfig.disabled_plugins = Array.isArray(value) ? value : []
      if (key === 'kb_names') this.kbConfig.kb_names = Array.isArray(value) ? value : []
      if (key === 'kb_top_k') this.kbConfig.top_k = Number(value) || 5
    },

    addOverride() {
      if (!this.selectedOverrideKey || this.activeOverrideKeys.includes(this.selectedOverrideKey)) return
      this.activeOverrideKeys.push(this.selectedOverrideKey)
      this.selectedOverrideKey = ''
    },

    removeOverride(key) {
      this.activeOverrideKeys = this.activeOverrideKeys.filter((overrideKey) => overrideKey !== key)
      if (key === 'llm_enabled') this.serviceConfig.llm_enabled = true
      if (key === 'tts_enabled') this.serviceConfig.tts_enabled = true
      if (key === 'persona_id') this.serviceConfig.persona_id = ''
      if (key === 'chat_completion') this.providerConfig.chat_completion = ''
      if (key === 'speech_to_text') this.providerConfig.speech_to_text = ''
      if (key === 'text_to_speech') this.providerConfig.text_to_speech = ''
      if (key === 'disabled_plugins') this.pluginConfig.disabled_plugins = []
      if (key === 'kb_names') this.kbConfig.kb_names = []
      if (key === 'kb_top_k') this.kbConfig.top_k = 5
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
        persona_id: svcConfig.persona_id || '',
      }

      // 初始化 Provider 配置
      this.providerConfig = {
        chat_completion: this.editingRules['provider_perf_chat_completion'] || '',
        speech_to_text: this.editingRules['provider_perf_speech_to_text'] || '',
        text_to_speech: this.editingRules['provider_perf_text_to_speech'] || '',
      }

      // 初始化插件配置
      const pluginCfg = this.editingRules.session_plugin_config || {}
      this.pluginConfig = {
        enabled_plugins: pluginCfg.enabled_plugins || [],
        disabled_plugins: pluginCfg.disabled_plugins || [],
      }

      // 初始化知识库配置
      const kbCfg = this.editingRules.kb_config || {}
      const kbRefs = kbCfg.kb_names || kbCfg.kb_ids || []
      this.kbConfig = {
        kb_names: [...kbRefs],
        top_k: kbCfg.top_k ?? 5,
      }

      const activeOverrideKeys = []
      if (Object.prototype.hasOwnProperty.call(svcConfig, 'llm_enabled')) activeOverrideKeys.push('llm_enabled')
      if (Object.prototype.hasOwnProperty.call(svcConfig, 'tts_enabled')) activeOverrideKeys.push('tts_enabled')
      if (Object.prototype.hasOwnProperty.call(svcConfig, 'persona_id')) activeOverrideKeys.push('persona_id')
      if (Object.prototype.hasOwnProperty.call(this.editingRules, 'provider_perf_chat_completion')) activeOverrideKeys.push('chat_completion')
      if (Object.prototype.hasOwnProperty.call(this.editingRules, 'provider_perf_speech_to_text')) activeOverrideKeys.push('speech_to_text')
      if (Object.prototype.hasOwnProperty.call(this.editingRules, 'provider_perf_text_to_speech')) activeOverrideKeys.push('text_to_speech')
      if (Object.prototype.hasOwnProperty.call(pluginCfg, 'disabled_plugins')) activeOverrideKeys.push('disabled_plugins')
      if (Object.prototype.hasOwnProperty.call(kbCfg, 'kb_names') || Object.prototype.hasOwnProperty.call(kbCfg, 'kb_ids')) activeOverrideKeys.push('kb_names')
      if (Object.prototype.hasOwnProperty.call(kbCfg, 'top_k')) activeOverrideKeys.push('kb_top_k')
      this.activeOverrideKeys = activeOverrideKeys
      this.selectedOverrideKey = ''

      this.ruleDialog = true
    },

    closeRuleEditor() {
      this.ruleDialog = false
      this.selectedUmo = null
      this.editingRules = {}
      this.activeOverrideKeys = []
      this.selectedOverrideKey = ''
    },

    async saveRuleEditor() {
      if (!this.selectedUmo) return

      this.saving = true
      try {
        const umo = this.selectedUmo.umo
        const tasks = []

        const previousServiceConfig = this.editingRules.session_service_config || {}
        const previousOverridePaths = []
        if (Object.prototype.hasOwnProperty.call(previousServiceConfig, 'llm_enabled')) {
          previousOverridePaths.push('provider_settings.enable')
        }
        if (Object.prototype.hasOwnProperty.call(previousServiceConfig, 'tts_enabled')) {
          previousOverridePaths.push('provider_tts_settings.enable')
        }
        if (Object.prototype.hasOwnProperty.call(previousServiceConfig, 'persona_id')) {
          previousOverridePaths.push('provider_settings.default_personality')
        }
        if (Object.prototype.hasOwnProperty.call(previousServiceConfig, 'session_enabled')) {
          previousOverridePaths.push('platform_settings.id_blacklist')
        }

        const providerPathMap = {
          chat_completion: 'provider_settings.default_provider_id',
          speech_to_text: 'provider_stt_settings.provider_id',
          text_to_speech: 'provider_tts_settings.provider_id',
        }
        for (const type of ['chat_completion', 'speech_to_text', 'text_to_speech']) {
          const ruleKey = `provider_perf_${type}`
          if (Object.prototype.hasOwnProperty.call(this.editingRules, ruleKey)) {
            previousOverridePaths.push(providerPathMap[type])
          }
        }

        const previousPluginConfig = this.editingRules.session_plugin_config || {}
        if (Object.prototype.hasOwnProperty.call(previousPluginConfig, 'disabled_plugins')) {
          previousOverridePaths.push('plugin_disabled_set')
        }

        const previousKbConfig = this.editingRules.kb_config || {}
        if (Object.prototype.hasOwnProperty.call(previousKbConfig, 'kb_names') || Object.prototype.hasOwnProperty.call(previousKbConfig, 'kb_ids')) {
          previousOverridePaths.push('kb_names')
        }
        if (Object.prototype.hasOwnProperty.call(previousKbConfig, 'top_k')) {
          previousOverridePaths.push('kb_final_top_k')
        }

        const pathsToDelete = [...new Set(previousOverridePaths)]
        if (pathsToDelete.length > 0) {
          tasks.push(() =>
            sessionApi.deleteConfigOverride({
              umo,
              paths: pathsToDelete,
            }),
          )
        }

        if (this.serviceConfig.custom_name || previousServiceConfig.custom_name) {
          tasks.push(() =>
            sessionApi.upsertAlias({
              umo,
              custom_name: this.serviceConfig.custom_name || '',
            }),
          )
        }

        const overrideValues = {
          llm_enabled: this.serviceConfig.llm_enabled,
          chat_completion: this.providerConfig.chat_completion || '',
          tts_enabled: this.serviceConfig.tts_enabled,
          text_to_speech: this.providerConfig.text_to_speech || '',
          speech_to_text: this.providerConfig.speech_to_text || '',
          persona_id: this.serviceConfig.persona_id || '',
          kb_names: Array.isArray(this.kbConfig.kb_names) ? this.kbConfig.kb_names : [],
          kb_top_k: Number(this.kbConfig.top_k) || 5,
          disabled_plugins: Array.isArray(this.pluginConfig.disabled_plugins) ? this.pluginConfig.disabled_plugins : [],
        }

        if (this.serviceConfig.session_enabled === false) {
          tasks.push(() =>
            sessionApi.upsertConfigOverride({
              umo,
              path: 'platform_settings.id_blacklist',
              value: [umo],
            }),
          )
        }

        for (const key of this.activeOverrideKeys) {
          const path = this.getOverrideConfigPath(key)
          if (!path) continue
          tasks.push(() =>
            sessionApi.upsertConfigOverride({
              umo,
              path,
              value: overrideValues[key],
            }),
          )
        }

        if (tasks.length === 0) {
          this.showSuccess(this.tm('messages.noChanges'))
          return
        }

        const responses = []
        for (const task of tasks) {
          responses.push(await task())
        }
        const allOk = responses.every((response) => response.data.status === 'ok')
        if (!allOk) {
          this.showError(this.tm('messages.saveError'))
          return
        }

        this.showSuccess(this.tm('messages.saveSuccess'))

        const nextRules = {}
        const nextServiceConfig = {}
        if (this.serviceConfig.custom_name) {
          nextServiceConfig.custom_name = this.serviceConfig.custom_name
        }
        if (this.serviceConfig.session_enabled === false) {
          nextServiceConfig.session_enabled = false
        }
        if (this.hasOverride('llm_enabled')) {
          nextServiceConfig.llm_enabled = this.serviceConfig.llm_enabled
        }
        if (this.hasOverride('tts_enabled')) {
          nextServiceConfig.tts_enabled = this.serviceConfig.tts_enabled
        }
        if (this.hasOverride('persona_id')) {
          nextServiceConfig.persona_id = this.serviceConfig.persona_id || ''
        }
        if (Object.keys(nextServiceConfig).length > 0) {
          nextRules.session_service_config = nextServiceConfig
        }

        for (const type of ['chat_completion', 'speech_to_text', 'text_to_speech']) {
          const value = this.providerConfig[type]
          const ruleKey = `provider_perf_${type}`
          if (this.hasOverride(type)) {
            nextRules[ruleKey] = value || ''
          }
        }
        if (this.hasOverride('disabled_plugins')) {
          nextRules.session_plugin_config = {
            disabled_plugins: Array.isArray(this.pluginConfig.disabled_plugins) ? this.pluginConfig.disabled_plugins : [],
          }
        }

        const nextKbConfig = {}
        if (this.hasOverride('kb_names')) {
          nextKbConfig.kb_names = Array.isArray(this.kbConfig.kb_names) ? this.kbConfig.kb_names : []
        }
        if (this.hasOverride('kb_top_k')) {
          nextKbConfig.top_k = this.kbConfig.top_k
        }
        if (Object.keys(nextKbConfig).length > 0) {
          nextRules.kb_config = nextKbConfig
        }

        let item = this.rulesList.find((rule) => rule.umo === umo)
        if (Object.keys(nextRules).length > 0) {
          if (item) {
            item.rules = nextRules
          } else {
            item = this.buildUmoItem(umo, nextRules)
            this.rulesList.push(item)
            this.totalItems += 1
          }
          this.selectedUmo = item
        } else if (item) {
          const index = this.rulesList.findIndex((rule) => rule.umo === umo)
          if (index > -1) {
            this.rulesList.splice(index, 1)
            this.totalItems = Math.max(0, this.totalItems - 1)
          }
          this.selectedUmo = this.buildUmoItem(umo)
        }
        this.editingRules = nextRules
      } catch (error) {
        this.showError(error.response?.data?.message || this.tm('messages.saveError'))
      } finally {
        this.saving = false
      }
    },

    confirmDeleteRules(item) {
      this.deleteTarget = item
      this.deleteDialog = true
    },

    async deleteAllRules() {
      if (!this.deleteTarget) return

      this.deleting = true
      try {
        const overridePaths = [
          ...this.overrideOptions.map((option) => option.path),
          'platform_settings.id_blacklist',
        ]
        const responses = [
          await sessionApi.deleteConfigOverride({
            umo: this.deleteTarget.umo,
            paths: overridePaths,
          }),
          await sessionApi.upsertAlias({
            umo: this.deleteTarget.umo,
            custom_name: '',
          }),
        ]
        const allOk = responses.every((response) => response.data.status === 'ok')

        if (allOk) {
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
          this.showError(this.tm('messages.deleteError'))
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
        const overridePaths = [
          ...this.overrideOptions.map((option) => option.path),
          'platform_settings.id_blacklist',
        ]
        const responses = [
          await sessionApi.deleteConfigOverride({
            umos,
            paths: overridePaths,
          }),
          await sessionApi.upsertAlias({
            umos,
            custom_name: '',
          }),
        ]
        const allOk = responses.every((response) => response.data.status === 'ok')

        if (allOk) {
          this.showSuccess(this.tm('messages.batchDeleteSuccess'))
          this.batchDeleteDialog = false
          this.selectedItems = []
          // 重新加载数据
          await this.loadData()
        } else {
          this.showError(this.tm('messages.batchDeleteError'))
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
        const existingConfig = this.quickEditNameTarget.rules?.session_service_config || {}
        const config = {
          ...existingConfig,
          custom_name: this.quickEditNameValue || '',
        }

        const response = await sessionApi.upsertAlias({
          umo: this.quickEditNameTarget.umo,
          custom_name: this.quickEditNameValue || '',
        })

        if (response.data.status === 'ok') {
          this.showSuccess(this.tm('messages.saveSuccess'))

          // 更新或添加到列表
          let item = this.rulesList.find((u) => u.umo === this.quickEditNameTarget.umo)
          const nextConfig = { ...config }
          if (!this.quickEditNameValue) delete nextConfig.custom_name
          if (item) {
            if (!item.rules) item.rules = {}
            if (Object.keys(nextConfig).length > 0) {
              item.rules.session_service_config = nextConfig
            } else {
              delete item.rules.session_service_config
            }
            if (Object.keys(item.rules).length === 0) {
              const index = this.rulesList.findIndex((rule) => rule.umo === item.umo)
              if (index > -1) {
                this.rulesList.splice(index, 1)
                this.totalItems = Math.max(0, this.totalItems - 1)
              }
            }
          } else {
            // 新规则，添加到列表
            if (Object.keys(nextConfig).length > 0) {
              this.rulesList.push(
                this.buildUmoItem(this.quickEditNameTarget.umo, {
                  session_service_config: nextConfig,
                }),
              )
            }
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
          scope = null
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
              sessionApi.deleteConfigOverride({
                scope,
                umos,
                group_id: groupId,
                path: 'provider_settings.default_provider_id',
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
              sessionApi.deleteConfigOverride({
                scope,
                umos,
                group_id: groupId,
                path: 'provider_tts_settings.provider_id',
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

.rule-editor-session {
  min-height: 36px;
}

.setting-section {
  padding: 14px 0;
  border-top: 1px solid rgba(0, 0, 0, 0.08);
}

.setting-section:first-child {
  border-top: 0;
  padding-top: 0;
}

.setting-section-title {
  font-size: 13px;
  font-weight: 700;
  margin-bottom: 8px;
}

.setting-add-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
  align-items: center;
  padding: 12px 0 8px;
}

.setting-empty-overrides {
  padding: 4px 0 10px;
  font-size: 12px;
  color: rgba(0, 0, 0, 0.55);
}

.override-selection {
  min-width: 0;
  display: flex;
  flex-direction: column;
  line-height: 1.2;
}

.override-selection-hint,
.override-option-hint {
  font-size: 11px;
  color: rgba(0, 0, 0, 0.55);
  overflow: hidden;
  text-overflow: ellipsis;
}

.setting-row {
  display: grid;
  grid-template-columns: minmax(190px, 250px) minmax(0, 1fr);
  gap: 16px;
  align-items: center;
  min-height: 48px;
  padding: 6px 0;
}

.setting-meta {
  min-width: 0;
}

.setting-label {
  font-size: 13px;
  font-weight: 500;
  line-height: 1.25;
}

.setting-path {
  margin-top: 3px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 11px;
  color: rgba(0, 0, 0, 0.55);
  overflow-wrap: anywhere;
}

.setting-hint {
  margin-top: 3px;
  font-size: 12px;
  line-height: 1.35;
  color: rgba(0, 0, 0, 0.55);
}

.setting-control {
  width: 100%;
}

.setting-control-with-action {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.setting-control-with-action-end {
  justify-content: flex-end;
}

.setting-control-fill {
  flex: 1;
  min-width: 0;
}

.setting-control-narrow {
  max-width: 180px;
  justify-self: end;
}

.setting-remove-btn {
  flex: 0 0 auto;
}

.setting-switch {
  justify-self: end;
}

@media (max-width: 700px) {
  .setting-add-row {
    grid-template-columns: 1fr;
  }

  .setting-row {
    grid-template-columns: 1fr;
    gap: 8px;
    align-items: stretch;
  }

  .setting-switch {
    justify-self: start;
  }

  .setting-control-narrow {
    max-width: none;
  }
}
</style>
