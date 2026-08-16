<template>
  <div class="session-management-page">
    <v-container fluid class="pa-0">
      <v-card flat>
        <v-card-title class="d-flex align-center py-3 px-4">
          <span class="text-h4">{{ tm('customRules.title') }}</span>
          <v-btn
            icon="mdi-information-outline"
            size="small"
            variant="text"
            :aria-label="tm('customRules.title')"
            href="https://docs.astrbot.app/use/custom-rules.html"
            target="_blank"
          ></v-btn>
          <v-chip size="small" class="ml-1"
            >{{ totalItems }} {{ tm('customRules.rulesCount') }}</v-chip
          >
          <v-row class="me-4 ms-4" density="comfortable">
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
          <v-btn
            v-if="selectedItems.length > 0"
            color="error"
            prepend-icon="mdi-delete"
            variant="tonal"
            class="mr-2"
            size="small"
            @click="confirmBatchDelete"
          >
            {{ tm('buttons.batchDelete') }} ({{ selectedItems.length }})
          </v-btn>
          <v-btn
            color="success"
            prepend-icon="mdi-plus"
            variant="tonal"
            class="mr-2"
            size="small"
            @click="openAddRuleDialog"
          >
            {{ tm('buttons.addRule') }}
          </v-btn>
          <v-btn
            color="primary"
            prepend-icon="mdi-refresh"
            variant="tonal"
            :loading="loading"
            size="small"
            @click="refreshData"
          >
            {{ tm('buttons.refresh') }}
          </v-btn>
        </v-card-title>

        <v-divider></v-divider>

        <v-card-text class="pa-0">
          <v-data-table-server
            v-model:items-per-page="itemsPerPage"
            v-model:page="currentPage"
            v-model="selectedItems"
            :headers="headers"
            :items="filteredRulesList"
            :loading="loading"
            :items-length="totalItems"
            class="elevation-0 session-rules-table"
            show-select
            item-value="umo"
            return-object
            @update:options="onTableOptionsUpdate"
          >
            <!-- UMO 信息 -->
            <template #item.umo_info="{ item }">
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
            <template #item.rules_overview="{ item }">
              <div class="d-flex flex-wrap ga-1">
                <v-chip
                  v-if="item.rules.session_service_config"
                  size="x-small"
                  color="primary"
                  variant="outlined"
                >
                  {{ tm('customRules.serviceConfig') }}
                </v-chip>
                <v-chip
                  v-if="item.rules.session_plugin_config"
                  size="x-small"
                  color="secondary"
                  variant="outlined"
                >
                  {{ tm('customRules.pluginConfig') }}
                </v-chip>
                <v-chip
                  v-if="item.rules.kb_config"
                  size="x-small"
                  color="info"
                  variant="outlined"
                >
                  {{ tm('customRules.kbConfig') }}
                </v-chip>
                <v-chip
                  v-if="hasProviderConfig(item.rules)"
                  size="x-small"
                  color="warning"
                  variant="outlined"
                >
                  {{ tm('customRules.providerConfig') }}
                </v-chip>
              </div>
            </template>

            <!-- 操作按钮 -->
            <template #item.actions="{ item }">
              <v-btn
                size="small"
                variant="tonal"
                color="primary"
                class="mr-1"
                :aria-label="tm('buttons.editRule')"
                @click="openRuleEditor(item)"
              >
                <v-icon>mdi-pencil</v-icon>
                <v-tooltip activator="parent" location="top">{{
                  tm('buttons.editRule')
                }}</v-tooltip>
              </v-btn>
              <v-btn
                size="small"
                variant="tonal"
                color="error"
                :aria-label="tm('buttons.deleteAllRules')"
                @click="confirmDeleteRules(item)"
              >
                <v-icon>mdi-delete</v-icon>
                <v-tooltip activator="parent" location="top">{{
                  tm('buttons.deleteAllRules')
                }}</v-tooltip>
              </v-btn>
            </template>

            <!-- 空状态 -->
            <template #no-data>
              <div class="text-center py-8">
                <v-icon size="64" color="on-surface-variant"
                  >mdi-file-document-edit-outline</v-icon
                >
                <div class="text-h6 mt-4">
                  {{ tm('customRules.noRules') }}
                </div>
                <div class="text-body-2 text-medium-emphasis">
                  {{ tm('customRules.noRulesDesc') }}
                </div>
                <v-btn
                  color="primary"
                  variant="tonal"
                  class="mt-4"
                  @click="openAddRuleDialog"
                >
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
          <v-row density="comfortable">
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
          <v-row class="mt-3" density="comfortable">
            <v-col cols="12" class="d-flex justify-end">
              <v-btn
                color="primary"
                variant="tonal"
                size="large"
                :disabled="!canApplyBatch"
                :loading="batchUpdating"
                prepend-icon="mdi-check-all"
                @click="applyBatchChanges"
              >
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
          <v-chip
            size="small"
            class="ml-2"
            color="secondary"
            variant="outlined"
          >
            {{ tm('groups.count', { count: groups.length }) }}
          </v-chip>
          <v-spacer></v-spacer>
          <v-btn
            v-if="selectedItems.length > 0 && groups.length > 0"
            color="info"
            variant="tonal"
            size="small"
            class="mr-2"
          >
            <v-icon start>mdi-folder-plus</v-icon>
            {{ tm('groups.addToGroup') }}
            <v-menu activator="parent">
              <v-list density="compact">
                <v-list-item
                  v-for="g in groups"
                  :key="g.id"
                  @click="addSelectedToGroup(g.id)"
                >
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
          <v-btn
            color="success"
            variant="tonal"
            size="small"
            prepend-icon="mdi-folder-plus"
            @click="openCreateGroupDialog"
          >
            {{ tm('groups.create') }}
          </v-btn>
        </v-card-title>
        <v-card-text v-if="groups.length > 0">
          <v-row density="comfortable">
            <v-col
              v-for="group in groups"
              :key="group.id"
              cols="12"
              sm="6"
              md="4"
              lg="3"
            >
              <v-card variant="outlined" class="pa-3">
                <div class="d-flex align-center justify-space-between">
                  <div>
                    <div class="font-weight-bold">{{ group.name }}</div>
                    <div class="text-caption text-medium-emphasis">
                      {{
                        tm('groups.sessionsCount', { count: group.umo_count })
                      }}
                    </div>
                  </div>
                  <div>
                    <v-btn
                      icon
                      size="small"
                      variant="text"
                      :aria-label="tm('buttons.edit')"
                      @click="openEditGroupDialog(group)"
                    >
                      <v-icon size="small">mdi-pencil</v-icon>
                    </v-btn>
                    <v-btn
                      icon
                      size="small"
                      variant="text"
                      color="error"
                      :aria-label="tm('buttons.delete')"
                      @click="deleteGroup(group)"
                    >
                      <v-icon size="small">mdi-delete</v-icon>
                    </v-btn>
                  </div>
                </div>
              </v-card>
            </v-col>
          </v-row>
        </v-card-text>
        <v-card-text v-else class="text-center text-medium-emphasis py-6">
          {{ tm('groups.empty') }}
        </v-card-text>
      </v-card>

      <!-- 分组编辑对话框 -->
      <v-dialog
        v-model="groupDialog"
        max-width="800"
        scrollable
        @after-enter="loadAvailableUmos"
      >
        <v-card class="app-dialog session-group-dialog__card">
          <v-card-title class="py-3 px-4">
            {{
              groupDialogMode === 'create'
                ? tm('groups.create')
                : tm('groups.edit')
            }}
          </v-card-title>
          <v-card-text class="session-group-dialog__content">
            <v-text-field
              v-model="editingGroup.name"
              :label="tm('groups.name')"
              variant="outlined"
              hide-details
              class="mb-4"
            ></v-text-field>
            <v-row density="comfortable">
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
                  <v-list-item
                    v-for="umo in filteredUnselectedUmos"
                    :key="umo"
                    class="transfer-item"
                    @click="addToGroup(umo)"
                  >
                    <template #prepend>
                      <v-icon size="small" color="on-surface-variant"
                        >mdi-plus</v-icon
                      >
                    </template>
                    <v-list-item-title>
                      <UmoDisplay
                        v-bind="getAvailableUmoDisplayProps(umo)"
                        compact
                        :show-info="false"
                        :show-platform="false"
                      />
                    </v-list-item-title>
                    <template #append>
                      <v-chip
                        v-if="getAvailableUmoInfo(umo).platform"
                        size="x-small"
                        :color="
                          getPlatformColor(getAvailableUmoInfo(umo).platform)
                        "
                        class="umo-list-platform"
                      >
                        {{ getAvailableUmoInfo(umo).platform }}
                      </v-chip>
                    </template>
                  </v-list-item>
                  <v-list-item
                    v-if="filteredUnselectedUmos.length === 0 && !loadingUmos"
                  >
                    <v-list-item-title
                      class="text-caption text-medium-emphasis text-center"
                      >{{ tm('groups.noMatch') }}</v-list-item-title
                    >
                  </v-list-item>
                  <v-list-item v-if="loadingUmos">
                    <v-list-item-title class="text-center"
                      ><v-progress-circular
                        indeterminate
                        size="20"
                      ></v-progress-circular
                    ></v-list-item-title>
                  </v-list-item>
                </v-list>
              </v-col>
              <!-- 中间：操作按钮 -->
              <v-col
                cols="2"
                class="d-flex flex-column align-center justify-center"
              >
                <v-btn
                  icon
                  size="small"
                  variant="tonal"
                  color="primary"
                  class="mb-2"
                  :disabled="unselectedUmos.length === 0"
                  :aria-label="tm('groups.addToGroup')"
                  @click="addAllToGroup"
                >
                  <v-icon>mdi-chevron-double-right</v-icon>
                </v-btn>
                <v-btn
                  icon
                  size="small"
                  variant="tonal"
                  color="error"
                  :disabled="editingGroup.umos.length === 0"
                  :aria-label="tm('buttons.clear')"
                  @click="removeAllFromGroup"
                >
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
                  <v-list-item
                    v-for="umo in filteredSelectedUmos"
                    :key="umo"
                    class="transfer-item"
                    @click="removeFromGroup(umo)"
                  >
                    <template #prepend>
                      <v-icon size="small" color="error">mdi-minus</v-icon>
                    </template>
                    <v-list-item-title>
                      <UmoDisplay
                        v-bind="getAvailableUmoDisplayProps(umo)"
                        compact
                        :show-info="false"
                        :show-platform="false"
                      />
                    </v-list-item-title>
                    <template #append>
                      <v-chip
                        v-if="getAvailableUmoInfo(umo).platform"
                        size="x-small"
                        :color="
                          getPlatformColor(getAvailableUmoInfo(umo).platform)
                        "
                        class="umo-list-platform"
                      >
                        {{ getAvailableUmoInfo(umo).platform }}
                      </v-chip>
                    </template>
                  </v-list-item>
                  <v-list-item v-if="editingGroup.umos.length === 0">
                    <v-list-item-title
                      class="text-caption text-medium-emphasis text-center"
                      >{{ tm('groups.noMembers') }}</v-list-item-title
                    >
                  </v-list-item>
                </v-list>
              </v-col>
            </v-row>
          </v-card-text>
          <v-card-actions class="px-4 pb-4 session-group-dialog__actions">
            <v-spacer></v-spacer>
            <v-btn variant="text" @click="groupDialog = false">{{
              tm('buttons.cancel')
            }}</v-btn>
            <v-btn color="primary" variant="tonal" @click="saveGroup">{{
              tm('buttons.save')
            }}</v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>

      <!-- 添加规则对话框 - 选择 UMO -->
      <v-dialog v-model="addRuleDialog" max-width="600">
        <v-card class="app-dialog">
          <v-card-title class="d-flex align-center py-3 px-4">
            <span>{{ tm('addRule.title') }}</span>
            <v-spacer></v-spacer>
            <v-btn
              icon
              variant="text"
              :aria-label="tm('buttons.cancel')"
              @click="addRuleDialog = false"
            >
              <v-icon>mdi-close</v-icon>
            </v-btn>
          </v-card-title>

          <v-card-text class="pa-4">
            <v-alert type="info" variant="tonal" class="mb-4">
              {{ tm('addRule.description') }}
            </v-alert>

            <v-autocomplete
              v-model="selectedNewUmo"
              :items="availableUmos"
              :loading="loadingUmos"
              :label="tm('addRule.selectUmo')"
              variant="outlined"
              clearable
              :no-data-text="tm('addRule.noUmos')"
            >
              <template #item="{ props, item }">
                <v-list-item v-bind="props">
                  <template #title>
                    <UmoDisplay
                      v-bind="getAvailableUmoDisplayProps(item)"
                      compact
                      :show-info="false"
                      :show-platform="false"
                    />
                  </template>
                  <template #append>
                    <v-chip
                      v-if="getAvailableUmoInfo(item).platform"
                      size="x-small"
                      :color="
                        getPlatformColor(getAvailableUmoInfo(item).platform)
                      "
                      class="umo-list-platform"
                    >
                      {{ getAvailableUmoInfo(item).platform }}
                    </v-chip>
                  </template>
                </v-list-item>
              </template>
              <template #selection="{ item }">
                <v-chip
                  v-if="item && getUmoSelectionText(item)"
                  size="small"
                  variant="tonal"
                  color="primary"
                  class="umo-selection-chip"
                >
                  {{ getUmoSelectionText(item) }}
                </v-chip>
              </template>
            </v-autocomplete>
          </v-card-text>

          <v-card-actions class="px-4 pb-4">
            <v-spacer></v-spacer>
            <v-btn variant="text" @click="addRuleDialog = false">{{
              tm('buttons.cancel')
            }}</v-btn>
            <v-btn
              color="primary"
              variant="tonal"
              :disabled="!selectedNewUmo"
              @click="createNewRule"
            >
              {{ tm('buttons.next') }}
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>

      <!-- 规则编辑对话框 -->
      <v-dialog v-model="ruleDialog" max-width="550" scrollable>
        <v-card v-if="selectedUmo" class="d-flex flex-column" height="600">
          <v-card-title class="py-3 px-6 d-flex align-center border-b">
            <span>{{ tm('ruleEditor.title') }}</span>
            <v-chip
              size="x-small"
              class="ml-2 font-weight-regular"
              variant="outlined"
            >
              {{ selectedUmo.umo }}
            </v-chip>
            <v-spacer></v-spacer>
            <v-btn
              icon="mdi-close"
              variant="text"
              @click="closeRuleEditor"
            ></v-btn>
          </v-card-title>

          <v-card-text class="pa-0 overflow-y-auto">
            <div class="px-6 py-4">
              <!-- Service Config Section -->
              <div class="d-flex align-center mb-4">
                <h3 class="font-weight-bold mb-0">
                  {{ tm('ruleEditor.serviceConfig.title') }}
                </h3>
              </div>

              <v-row density="comfortable">
                <v-col cols="12">
                  <v-checkbox
                    v-model="serviceConfig.session_enabled"
                    :label="tm('ruleEditor.serviceConfig.sessionEnabled')"
                    color="success"
                    hide-details
                    class="mb-2"
                  />
                </v-col>
                <v-col cols="12" md="6">
                  <v-checkbox
                    v-model="serviceConfig.llm_enabled"
                    :label="tm('ruleEditor.serviceConfig.llmEnabled')"
                    color="primary"
                    hide-details
                  />
                </v-col>
                <v-col cols="12" md="6">
                  <v-checkbox
                    v-model="serviceConfig.tts_enabled"
                    :label="tm('ruleEditor.serviceConfig.ttsEnabled')"
                    color="secondary"
                    hide-details
                  />
                </v-col>
                <v-col cols="12" class="mt-2">
                  <v-text-field
                    v-model="serviceConfig.custom_name"
                    :label="tm('ruleEditor.serviceConfig.customName')"
                    variant="outlined"
                    hide-details
                    clearable
                  />
                </v-col>
              </v-row>

              <div class="d-flex justify-end mt-4">
                <v-btn
                  color="primary"
                  variant="tonal"
                  size="small"
                  :loading="saving"
                  prepend-icon="mdi-content-save"
                  @click="saveServiceConfig"
                >
                  {{ tm('buttons.save') }}
                </v-btn>
              </div>

              <!-- Provider Config Section -->
              <div class="d-flex align-center mb-4 mt-4">
                <h3 class="font-weight-bold mb-0">
                  {{ tm('ruleEditor.providerConfig.title') }}
                </h3>
              </div>

              <v-row density="comfortable">
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
                <v-btn
                  color="primary"
                  variant="tonal"
                  size="small"
                  :loading="saving"
                  prepend-icon="mdi-content-save"
                  @click="saveProviderConfig"
                >
                  {{ tm('buttons.save') }}
                </v-btn>
              </div>

              <!-- Persona Config Section -->
              <div class="d-flex align-center mb-4 mt-4">
                <h3 class="font-weight-bold mb-0">
                  {{ tm('ruleEditor.personaConfig.title') }}
                </h3>
              </div>

              <v-row density="comfortable">
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
                  <v-alert
                    type="info"
                    variant="tonal"
                    class="mt-2"
                    icon="mdi-information-outline"
                  >
                    {{ tm('ruleEditor.personaConfig.hint') }}
                  </v-alert>
                </v-col>
              </v-row>

              <div class="d-flex justify-end mt-4">
                <v-btn
                  color="primary"
                  variant="tonal"
                  size="small"
                  :loading="saving"
                  prepend-icon="mdi-content-save"
                  @click="saveServiceConfig"
                >
                  {{ tm('buttons.save') }}
                </v-btn>
              </div>

              <!-- Plugin Config Section -->
              <div class="d-flex align-center mb-4 mt-4">
                <h3 class="font-weight-bold mb-0">
                  {{ tm('ruleEditor.pluginConfig.title') }}
                </h3>
              </div>

              <v-row density="comfortable">
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
                  <v-alert
                    type="info"
                    variant="tonal"
                    class="mt-2"
                    icon="mdi-information-outline"
                  >
                    {{ tm('ruleEditor.pluginConfig.hint') }}
                  </v-alert>
                </v-col>
              </v-row>

              <div class="d-flex justify-end mt-4">
                <v-btn
                  color="primary"
                  variant="tonal"
                  size="small"
                  :loading="saving"
                  prepend-icon="mdi-content-save"
                  @click="savePluginConfig"
                >
                  {{ tm('buttons.save') }}
                </v-btn>
              </div>

              <!-- KB Config Section -->
              <div class="d-flex align-center mb-4 mt-4">
                <h3 class="font-weight-bold mb-0">
                  {{ tm('ruleEditor.kbConfig.title') }}
                </h3>
              </div>

              <v-row density="comfortable">
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
                  <v-text-field
                    v-model.number="kbConfig.top_k"
                    :label="tm('ruleEditor.kbConfig.topK')"
                    variant="outlined"
                    hide-details
                    type="number"
                    min="1"
                    max="20"
                    class="mt-3"
                  />
                </v-col>
                <v-col cols="12" md="6">
                  <v-checkbox
                    v-model="kbConfig.enable_rerank"
                    :label="tm('ruleEditor.kbConfig.enableRerank')"
                    color="primary"
                    hide-details
                    class="mt-3"
                  />
                </v-col>
              </v-row>

              <div class="d-flex justify-end mt-4">
                <v-btn
                  color="primary"
                  variant="tonal"
                  size="small"
                  :loading="saving"
                  prepend-icon="mdi-content-save"
                  @click="saveKbConfig"
                >
                  {{ tm('buttons.save') }}
                </v-btn>
              </div>
            </div>
          </v-card-text>
        </v-card>
      </v-dialog>

      <!-- 确认删除对话框 -->
      <v-dialog v-model="deleteDialog" max-width="400">
        <v-card class="app-dialog">
          <v-card-title class="text-h6">{{
            tm('deleteConfirm.title')
          }}</v-card-title>
          <v-card-text>
            {{ tm('deleteConfirm.message') }}
            <br /><br />
            <code>{{ deleteTarget?.umo }}</code>
          </v-card-text>
          <v-card-actions>
            <v-spacer></v-spacer>
            <v-btn variant="text" @click="deleteDialog = false">{{
              tm('buttons.cancel')
            }}</v-btn>
            <v-btn
              color="error"
              variant="tonal"
              :loading="deleting"
              @click="deleteAllRules"
              >{{ tm('buttons.delete') }}</v-btn
            >
          </v-card-actions>
        </v-card>
      </v-dialog>

      <!-- 批量删除确认对话框 -->
      <v-dialog v-model="batchDeleteDialog" max-width="500">
        <v-card>
          <v-card-title class="text-h6">{{
            tm('batchDeleteConfirm.title')
          }}</v-card-title>
          <v-card-text>
            {{
              tm('batchDeleteConfirm.message', { count: selectedItems.length })
            }}
            <div class="session-selection-list mt-3">
              <v-chip
                v-for="item in selectedItems"
                :key="item.umo"
                size="small"
                class="ma-1"
                variant="outlined"
              >
                {{ getUmoDisplayText(item) }}
              </v-chip>
            </div>
          </v-card-text>
          <v-card-actions>
            <v-spacer></v-spacer>
            <v-btn variant="text" @click="batchDeleteDialog = false">{{
              tm('buttons.cancel')
            }}</v-btn>
            <v-btn
              color="error"
              variant="tonal"
              :loading="deleting"
              @click="batchDeleteRules"
            >
              {{ tm('buttons.delete') }}
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>

      <!-- 提示信息 -->
      <v-snackbar
        v-model="snackbar"
        :timeout="3000"
        elevation="4"
        :color="snackbarColor"
        location="top"
      >
        {{ snackbarText }}
      </v-snackbar>

      <!-- 快速编辑备注名对话框 -->
      <v-dialog v-model="quickEditNameDialog" max-width="400">
        <v-card>
          <v-card-title class="py-3 px-4">{{
            tm('quickEditName.title')
          }}</v-card-title>
          <v-card-text class="pa-4">
            <v-text-field
              v-model="quickEditNameValue"
              :label="tm('ruleEditor.serviceConfig.customName')"
              variant="outlined"
              hide-details
              clearable
              autofocus
              @keyup.enter="saveQuickEditName"
            />
          </v-card-text>
          <v-card-actions class="px-4 pb-4">
            <v-spacer></v-spacer>
            <v-btn variant="text" @click="quickEditNameDialog = false">{{
              tm('buttons.cancel')
            }}</v-btn>
            <v-btn
              color="primary"
              variant="tonal"
              :loading="saving"
              @click="saveQuickEditName"
            >
              {{ tm('buttons.save') }}
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-dialog>
    </v-container>
  </div>
</template>

<script setup lang="ts">
import {
  computed,
  onBeforeUnmount,
  onMounted,
  reactive,
  ref,
  watch,
} from 'vue';
import { sessionApi, type UmoInfoData } from '@/api/v1';
import type {
  BatchSessionProviderRequest,
  BatchSessionServiceRequest,
  DynamicConfig,
  UmoListRequest,
} from '@/api/generated/openapi-v1';
import UmoDisplay from '@/components/shared/UmoDisplay.vue';
import { useModuleI18n } from '@/i18n/composables';
import { getPlatformColor as resolvePlatformColor } from '@/utils/platformUtils';
import {
  askForConfirmation as askForConfirmationDialog,
  useConfirmDialog,
} from '@/utils/confirmDialog';

const FOLLOW_CONFIG_VALUE = '__astrbot_follow_config__';

type SnackbarColor = 'success' | 'error';
type GroupDialogMode = 'create' | 'edit';
type ProviderRuleType = 'chat_completion' | 'speech_to_text' | 'text_to_speech';
type ApiBatchScope = 'all' | 'group' | 'private' | 'custom_group';

type RuleKey =
  | 'session_service_config'
  | 'session_plugin_config'
  | 'kb_config'
  | `provider_perf_${ProviderRuleType}`;

type BatchScope = 'selected' | ApiBatchScope | `custom_group:${string}`;

interface ProviderOption {
  id: string;
  name: string;
  model?: string;
}

interface PersonaOption {
  name: string;
}

interface PluginOption {
  name: string;
  display_name?: string;
}

interface KnowledgeBaseOption {
  kb_id: string;
  kb_name: string;
  emoji?: string | null;
}

interface SessionServiceConfig {
  session_enabled?: boolean;
  llm_enabled?: boolean;
  tts_enabled?: boolean;
  custom_name?: string;
  persona_id?: string | null;
  [key: string]: unknown;
}

interface SessionPluginConfig {
  enabled_plugins?: string[];
  disabled_plugins?: string[];
  [key: string]: unknown;
}

interface SessionKbConfig {
  kb_ids?: string[];
  top_k?: number;
  enable_rerank?: boolean;
  [key: string]: unknown;
}

interface SessionRuleSet {
  session_service_config?: SessionServiceConfig;
  session_plugin_config?: SessionPluginConfig;
  kb_config?: SessionKbConfig;
  provider_perf_chat_completion?: string;
  provider_perf_speech_to_text?: string;
  provider_perf_text_to_speech?: string;
  [key: string]: unknown;
}

interface SessionRuleItem extends UmoInfoData {
  umo: string;
  rules: SessionRuleSet;
}

interface GroupItem {
  id: string;
  name: string;
  umos: string[];
  umo_count: number;
}

interface GroupEditorState {
  id: string | null;
  name: string;
  umos: string[];
}

interface SelectOption<T> {
  label: string;
  value: T;
  disabled?: boolean;
}

interface TableOptionsLike {
  page?: number;
  itemsPerPage?: number;
}

interface UmoDisplayInfo {
  umo: string;
  platform: string;
  message_type: string;
  session_id: string;
  auto_name: string;
  user_alias: string;
  display_name: string;
  rules?: SessionRuleSet;
}

interface DebouncedCallback {
  (): void;
  cancel: () => void;
}

const { tm } = useModuleI18n('features/session-management');
const confirmDialog = useConfirmDialog();

const loading = ref(false);
const saving = ref(false);
const deleting = ref(false);
const loadingUmos = ref(false);
const rulesList = ref<SessionRuleItem[]>([]);
const searchQuery = ref('');

const currentPage = ref(1);
const itemsPerPage = ref(10);
const totalItems = ref(0);

const availablePersonas = ref<PersonaOption[]>([]);
const availableChatProviders = ref<ProviderOption[]>([]);
const availableSttProviders = ref<ProviderOption[]>([]);
const availableTtsProviders = ref<ProviderOption[]>([]);
const availablePlugins = ref<PluginOption[]>([]);
const availableKbs = ref<KnowledgeBaseOption[]>([]);

const addRuleDialog = ref(false);
const availableUmos = ref<string[]>([]);
const availableUmoInfoMap = ref<Record<string, UmoDisplayInfo>>({});
const selectedNewUmo = ref<string | null>(null);

const ruleDialog = ref(false);
const selectedUmo = ref<SessionRuleItem | null>(null);
const editingRules = ref<SessionRuleSet>({});

const serviceConfig = reactive<
  Required<
    Pick<
      SessionServiceConfig,
      'session_enabled' | 'llm_enabled' | 'tts_enabled'
    >
  > & {
    custom_name: string;
    persona_id: string | null;
  }
>({
  session_enabled: true,
  llm_enabled: true,
  tts_enabled: true,
  custom_name: '',
  persona_id: null,
});

const providerConfig = reactive<Record<ProviderRuleType, string>>({
  chat_completion: FOLLOW_CONFIG_VALUE,
  speech_to_text: FOLLOW_CONFIG_VALUE,
  text_to_speech: FOLLOW_CONFIG_VALUE,
});

const pluginConfig = reactive<
  Required<Pick<SessionPluginConfig, 'enabled_plugins' | 'disabled_plugins'>>
>({
  enabled_plugins: [],
  disabled_plugins: [],
});

const kbConfig = reactive<
  Required<Pick<SessionKbConfig, 'kb_ids' | 'top_k' | 'enable_rerank'>>
>({
  kb_ids: [],
  top_k: 5,
  enable_rerank: true,
});

const deleteDialog = ref(false);
const deleteTarget = ref<SessionRuleItem | null>(null);

const selectedItems = ref<SessionRuleItem[]>([]);
const batchDeleteDialog = ref(false);

const quickEditNameDialog = ref(false);
const quickEditNameTarget = ref<SessionRuleItem | null>(null);
const quickEditNameValue = ref('');

const batchScope = ref<BatchScope>('selected');
const batchLlmStatus = ref<boolean | null>(null);
const batchTtsStatus = ref<boolean | null>(null);
const batchChatProvider = ref<string | null>(null);
const batchTtsProvider = ref<string | null>(null);
const batchUpdating = ref(false);

const groups = ref<GroupItem[]>([]);
const groupsLoading = ref(false);
const groupDialog = ref(false);
const groupDialogMode = ref<GroupDialogMode>('create');
const editingGroup = reactive<GroupEditorState>({
  id: null,
  name: '',
  umos: [],
});
const groupMemberSearch = ref('');
const groupSelectedSearch = ref('');

const snackbar = ref(false);
const snackbarText = ref('');
const snackbarColor = ref<SnackbarColor>('success');

const headers = computed(() => [
  {
    title: tm('table.headers.umoInfo'),
    key: 'umo_info',
    sortable: false,
    minWidth: '300px',
  },
  {
    title: tm('table.headers.rulesOverview'),
    key: 'rules_overview',
    sortable: false,
    minWidth: '250px',
  },
  {
    title: tm('table.headers.actions'),
    key: 'actions',
    sortable: false,
    minWidth: '150px',
  },
]);

const filteredRulesList = computed(() => rulesList.value);

const personaOptions = computed<SelectOption<string | null>[]>(() => [
  { label: tm('persona.none'), value: null },
  ...availablePersonas.value.map((persona) => ({
    label: persona.name,
    value: persona.name,
  })),
]);

const chatProviderOptions = computed<SelectOption<string>[]>(() => [
  { label: tm('provider.followConfig'), value: FOLLOW_CONFIG_VALUE },
  ...availableChatProviders.value.map((provider) => ({
    label: `${provider.name} (${provider.model || ''})`,
    value: provider.id,
  })),
]);

const sttProviderOptions = computed<SelectOption<string>[]>(() => [
  { label: tm('provider.followConfig'), value: FOLLOW_CONFIG_VALUE },
  ...availableSttProviders.value.map((provider) => ({
    label: `${provider.name} (${provider.model || ''})`,
    value: provider.id,
  })),
]);

const ttsProviderOptions = computed<SelectOption<string>[]>(() => [
  { label: tm('provider.followConfig'), value: FOLLOW_CONFIG_VALUE },
  ...availableTtsProviders.value.map((provider) => ({
    label: `${provider.name} (${provider.model || ''})`,
    value: provider.id,
  })),
]);

const batchChatProviderOptions = computed(() => chatProviderOptions.value);

const pluginOptions = computed<SelectOption<string>[]>(() =>
  availablePlugins.value.map((plugin) => ({
    label: plugin.display_name || plugin.name,
    value: plugin.name,
  })),
);

const kbOptions = computed<SelectOption<string>[]>(() =>
  availableKbs.value.map((kb) => ({
    label: `${kb.emoji || '📚'} ${kb.kb_name}`,
    value: kb.kb_id,
  })),
);

const batchScopeOptions = computed<SelectOption<string>[]>(() => {
  const options: SelectOption<string>[] = [
    { label: tm('batchOperations.scopeSelected'), value: 'selected' },
    { label: tm('batchOperations.scopeAll'), value: 'all' },
    { label: tm('batchOperations.scopeGroup'), value: 'group' },
    { label: tm('batchOperations.scopePrivate'), value: 'private' },
  ];

  if (groups.value.length > 0) {
    options.push({
      label: tm('groups.customGroupDivider'),
      value: '_divider',
      disabled: true,
    });
    groups.value.forEach((group) => {
      options.push({
        label: tm('groups.customGroupOption', {
          name: group.name,
          count: group.umo_count,
        }),
        value: `custom_group:${group.id}`,
      });
    });
  }

  return options;
});

const statusOptions = computed<SelectOption<boolean>[]>(() => [
  { label: tm('status.enabled'), value: true },
  { label: tm('status.disabled'), value: false },
]);

const canApplyBatch = computed(() => {
  const hasChanges =
    batchLlmStatus.value !== null ||
    batchTtsStatus.value !== null ||
    batchChatProvider.value !== null ||
    batchTtsProvider.value !== null;

  if (batchScope.value === 'selected') {
    return hasChanges && selectedItems.value.length > 0;
  }

  return hasChanges;
});

const unselectedUmos = computed(() => {
  const selected = new Set(editingGroup.umos);
  return availableUmos.value.filter((umo) => !selected.has(umo));
});

const filteredUnselectedUmos = computed(() => {
  if (!groupMemberSearch.value) {
    return unselectedUmos.value;
  }

  const search = groupMemberSearch.value.toLowerCase();
  return unselectedUmos.value.filter((umo) =>
    umo.toLowerCase().includes(search),
  );
});

const filteredSelectedUmos = computed(() => {
  if (!groupSelectedSearch.value) {
    return editingGroup.umos;
  }

  const search = groupSelectedSearch.value.toLowerCase();
  return editingGroup.umos.filter((umo) => umo.toLowerCase().includes(search));
});

const debouncedSearch = createDebouncedCallback(() => {
  currentPage.value = 1;
  void loadData();
}, 300);

watch(searchQuery, () => {
  debouncedSearch();
});

onMounted(() => {
  void loadData();
  void loadGroups();
});

onBeforeUnmount(() => {
  debouncedSearch.cancel();
});

function createDebouncedCallback(
  callback: () => void,
  delayMs: number,
): DebouncedCallback {
  let timer: ReturnType<typeof setTimeout> | null = null;

  const debounced = (() => {
    if (timer) {
      clearTimeout(timer);
    }

    timer = setTimeout(() => {
      timer = null;
      callback();
    }, delayMs);
  }) as DebouncedCallback;

  debounced.cancel = () => {
    if (!timer) {
      return;
    }

    clearTimeout(timer);
    timer = null;
  };

  return debounced;
}

function normalizeString(value: unknown): string {
  return typeof value === 'string' ? value : '';
}

function normalizeStringArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === 'string')
    : [];
}

function normalizeBoolean(value: unknown, fallback: boolean): boolean {
  return typeof value === 'boolean' ? value : fallback;
}

function normalizeNumber(value: unknown, fallback: number): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback;
}

function normalizeProviderOption(raw: unknown): ProviderOption | null {
  if (!raw || typeof raw !== 'object') {
    return null;
  }

  const source = raw as Record<string, unknown>;
  const id = normalizeString(source.id);
  const name = normalizeString(source.name);
  if (!id || !name) {
    return null;
  }

  return {
    id,
    name,
    model: normalizeString(source.model) || undefined,
  };
}

function normalizePersonaOption(raw: unknown): PersonaOption | null {
  if (!raw || typeof raw !== 'object') {
    return null;
  }

  const source = raw as Record<string, unknown>;
  const name = normalizeString(source.name);
  return name ? { name } : null;
}

function normalizePluginOption(raw: unknown): PluginOption | null {
  if (!raw || typeof raw !== 'object') {
    return null;
  }

  const source = raw as Record<string, unknown>;
  const name = normalizeString(source.name);
  if (!name) {
    return null;
  }

  return {
    name,
    display_name: normalizeString(source.display_name) || undefined,
  };
}

function normalizeKnowledgeBaseOption(
  raw: unknown,
): KnowledgeBaseOption | null {
  if (!raw || typeof raw !== 'object') {
    return null;
  }

  const source = raw as Record<string, unknown>;
  const kbId = normalizeString(source.kb_id);
  const kbName = normalizeString(source.kb_name);
  if (!kbId || !kbName) {
    return null;
  }

  return {
    kb_id: kbId,
    kb_name: kbName,
    emoji: normalizeString(source.emoji) || null,
  };
}

function normalizeSessionServiceConfig(raw: unknown): SessionServiceConfig {
  if (!raw || typeof raw !== 'object') {
    return {};
  }

  const source = raw as Record<string, unknown>;
  return {
    ...source,
    session_enabled: normalizeBoolean(source.session_enabled, true),
    llm_enabled: normalizeBoolean(source.llm_enabled, true),
    tts_enabled: normalizeBoolean(source.tts_enabled, true),
    custom_name: normalizeString(source.custom_name) || undefined,
    persona_id: normalizeString(source.persona_id) || null,
  };
}

function normalizeSessionPluginConfig(raw: unknown): SessionPluginConfig {
  if (!raw || typeof raw !== 'object') {
    return {};
  }

  const source = raw as Record<string, unknown>;
  return {
    ...source,
    enabled_plugins: normalizeStringArray(source.enabled_plugins),
    disabled_plugins: normalizeStringArray(source.disabled_plugins),
  };
}

function normalizeSessionKbConfig(raw: unknown): SessionKbConfig {
  if (!raw || typeof raw !== 'object') {
    return {};
  }

  const source = raw as Record<string, unknown>;
  return {
    ...source,
    kb_ids: normalizeStringArray(source.kb_ids),
    top_k: normalizeNumber(source.top_k, 5),
    enable_rerank: normalizeBoolean(source.enable_rerank, true),
  };
}

function toRuleValue(
  value: string | SessionServiceConfig | SessionPluginConfig | SessionKbConfig,
): DynamicConfig {
  return value as unknown as DynamicConfig;
}

function normalizeRuleSet(raw: unknown): SessionRuleSet {
  if (!raw || typeof raw !== 'object') {
    return {};
  }

  const source = raw as Record<string, unknown>;
  return {
    ...source,
    session_service_config: normalizeSessionServiceConfig(
      source.session_service_config,
    ),
    session_plugin_config: normalizeSessionPluginConfig(
      source.session_plugin_config,
    ),
    kb_config: normalizeSessionKbConfig(source.kb_config),
    provider_perf_chat_completion:
      normalizeString(source.provider_perf_chat_completion) || undefined,
    provider_perf_speech_to_text:
      normalizeString(source.provider_perf_speech_to_text) || undefined,
    provider_perf_text_to_speech:
      normalizeString(source.provider_perf_text_to_speech) || undefined,
  };
}

function parseUmoInfo(umo: string): UmoDisplayInfo {
  const parts = umo.split(':');
  return {
    umo,
    platform: parts[0] || '',
    message_type: parts[1] || '',
    session_id: parts.slice(2).join(':') || umo,
    auto_name: '',
    user_alias: '',
    display_name: umo,
  };
}

function normalizeUmoInfo(
  raw: unknown,
  fallbackUmo = '',
): UmoDisplayInfo | null {
  if (!raw || typeof raw !== 'object') {
    return fallbackUmo ? parseUmoInfo(fallbackUmo) : null;
  }

  const source = raw as Record<string, unknown>;
  const umo = normalizeString(source.umo) || fallbackUmo;
  if (!umo) {
    return null;
  }

  return {
    umo,
    platform: normalizeString(source.platform),
    message_type: normalizeString(source.message_type),
    session_id:
      normalizeString(source.session_id) || parseUmoInfo(umo).session_id,
    auto_name: normalizeString(source.auto_name),
    user_alias: normalizeString(source.user_alias),
    display_name: normalizeString(source.display_name) || umo,
    rules:
      source.rules && typeof source.rules === 'object'
        ? normalizeRuleSet(source.rules)
        : undefined,
  };
}

function normalizeRuleItem(raw: unknown): SessionRuleItem | null {
  const info = normalizeUmoInfo(raw);
  if (!info) {
    return null;
  }

  const source = raw as Record<string, unknown>;
  return {
    ...info,
    rules: normalizeRuleSet(source.rules),
  };
}

function normalizeGroup(raw: unknown): GroupItem | null {
  if (!raw || typeof raw !== 'object') {
    return null;
  }

  const source = raw as Record<string, unknown>;
  const id = normalizeString(source.id);
  const name = normalizeString(source.name);
  if (!id || !name) {
    return null;
  }

  return {
    id,
    name,
    umos: normalizeStringArray(source.umos),
    umo_count: normalizeNumber(source.umo_count, 0),
  };
}

function mergeUmoInfos(infos: unknown) {
  const next = { ...availableUmoInfoMap.value };
  if (!Array.isArray(infos)) {
    availableUmoInfoMap.value = next;
    return;
  }

  infos.forEach((info) => {
    const normalized = normalizeUmoInfo(info);
    if (normalized?.umo) {
      next[normalized.umo] = { ...(next[normalized.umo] || {}), ...normalized };
    }
  });

  availableUmoInfoMap.value = next;
}

function normalizeUmoValue(value: unknown): string {
  if (typeof value === 'string') {
    return value;
  }
  if (value && typeof value === 'object') {
    return normalizeString((value as Record<string, unknown>).umo);
  }
  return '';
}

function getAvailableUmoInfo(value: unknown): UmoDisplayInfo {
  const umo = normalizeUmoValue(value);
  if (!umo) {
    return parseUmoInfo('');
  }

  return availableUmoInfoMap.value[umo] || parseUmoInfo(umo);
}

function getAvailableUmoDisplayProps(value: unknown) {
  const info = getAvailableUmoInfo(value);
  return {
    umo: info.umo,
    platform: info.platform,
    messageType: info.message_type,
    sessionId: info.session_id,
    autoName: info.auto_name,
    userAlias: info.user_alias,
  };
}

function hasProviderConfig(rules: SessionRuleSet | null | undefined): boolean {
  return Boolean(
    rules?.provider_perf_chat_completion ||
    rules?.provider_perf_speech_to_text ||
    rules?.provider_perf_text_to_speech,
  );
}

function getPlatformColor(platform: string): string {
  return resolvePlatformColor(platform);
}

function getProviderRule(
  rules: SessionRuleSet,
  type: ProviderRuleType,
): string | undefined {
  switch (type) {
    case 'chat_completion':
      return rules.provider_perf_chat_completion;
    case 'speech_to_text':
      return rules.provider_perf_speech_to_text;
    case 'text_to_speech':
      return rules.provider_perf_text_to_speech;
  }
}

function setProviderRule(
  rules: SessionRuleSet,
  type: ProviderRuleType,
  value: string,
): void {
  switch (type) {
    case 'chat_completion':
      rules.provider_perf_chat_completion = value;
      return;
    case 'speech_to_text':
      rules.provider_perf_speech_to_text = value;
      return;
    case 'text_to_speech':
      rules.provider_perf_text_to_speech = value;
  }
}

function clearProviderRule(
  rules: SessionRuleSet,
  type: ProviderRuleType,
): void {
  switch (type) {
    case 'chat_completion':
      delete rules.provider_perf_chat_completion;
      return;
    case 'speech_to_text':
      delete rules.provider_perf_speech_to_text;
      return;
    case 'text_to_speech':
      delete rules.provider_perf_text_to_speech;
  }
}

function buildBatchTargetPayload(
  scope: BatchScope,
  groupId: string | null,
  umos: string[],
): Partial<Pick<UmoListRequest, 'scope' | 'group_id' | 'umos'>> {
  const payload: Partial<Pick<UmoListRequest, 'scope' | 'group_id' | 'umos'>> =
    {};

  if (
    scope === 'all' ||
    scope === 'group' ||
    scope === 'private' ||
    scope === 'custom_group'
  ) {
    payload.scope = scope;
  }
  if (groupId) {
    payload.group_id = groupId;
  }
  if (umos.length > 0) {
    payload.umos = umos;
  }

  return payload;
}

function getUmoDisplayText(value: unknown): string {
  const item =
    typeof value === 'string'
      ? getAvailableUmoInfo(value)
      : (value as UmoDisplayInfo | SessionRuleItem | null);
  if (!item) {
    return '';
  }

  const umo = item.umo || normalizeUmoValue(value);
  const aliasName =
    item.user_alias || item.rules?.session_service_config?.custom_name || '';
  const autoName = item.auto_name || '';

  let displayName = '';
  if (aliasName && autoName && aliasName !== autoName) {
    displayName = `${aliasName}（${autoName}）`;
  } else {
    displayName = aliasName || autoName;
  }

  if (displayName && umo) {
    return `${displayName} (UMO: ${umo})`;
  }

  return displayName || (umo ? `UMO: ${umo}` : item.display_name || '');
}

function getUmoSelectionText(value: unknown): string {
  const item =
    typeof value === 'string'
      ? getAvailableUmoInfo(value)
      : (value as UmoDisplayInfo | SessionRuleItem | null);
  if (!item) {
    return '';
  }

  const umo = item.umo || normalizeUmoValue(value);
  const aliasName =
    item.user_alias || item.rules?.session_service_config?.custom_name || '';
  const autoName = item.auto_name || '';

  if (aliasName && autoName && aliasName !== autoName) {
    return `${aliasName}（${autoName}）`;
  }

  return aliasName || autoName || umo || item.display_name || '';
}

function buildUmoItem(
  umo: string,
  rules: SessionRuleSet = {},
): SessionRuleItem {
  const info = getAvailableUmoInfo(umo);
  return {
    ...info,
    umo,
    rules,
  };
}

function findRuleItem(umo: string): SessionRuleItem | undefined {
  return rulesList.value.find((item) => item.umo === umo);
}

function ensureRuleItem(umo: string): SessionRuleItem {
  const existing = findRuleItem(umo);
  if (existing) {
    return existing;
  }

  const next = buildUmoItem(umo);
  rulesList.value.push(next);
  return next;
}

function resetGroupEditor() {
  editingGroup.id = null;
  editingGroup.name = '';
  editingGroup.umos = [];
  groupMemberSearch.value = '';
  groupSelectedSearch.value = '';
}

async function loadData() {
  loading.value = true;
  try {
    const response = await sessionApi.listRules({
      page: currentPage.value,
      page_size: itemsPerPage.value,
      search: searchQuery.value || '',
    });

    if (response.data.status !== 'ok') {
      showError(response.data.message || tm('messages.loadError'));
      return;
    }

    const data = response.data.data;
    const normalizedRules = Array.isArray(data.rules)
      ? data.rules
          .map((item) => normalizeRuleItem(item))
          .filter((item): item is SessionRuleItem => item !== null)
      : [];

    rulesList.value = normalizedRules;
    mergeUmoInfos(data.rules);
    totalItems.value = normalizeNumber(data.total, 0);
    availablePersonas.value = Array.isArray(data.available_personas)
      ? data.available_personas
          .map((item) => normalizePersonaOption(item))
          .filter((item): item is PersonaOption => item !== null)
      : [];
    availableChatProviders.value = Array.isArray(data.available_chat_providers)
      ? data.available_chat_providers
          .map((item) => normalizeProviderOption(item))
          .filter((item): item is ProviderOption => item !== null)
      : [];
    availableSttProviders.value = Array.isArray(data.available_stt_providers)
      ? data.available_stt_providers
          .map((item) => normalizeProviderOption(item))
          .filter((item): item is ProviderOption => item !== null)
      : [];
    availableTtsProviders.value = Array.isArray(data.available_tts_providers)
      ? data.available_tts_providers
          .map((item) => normalizeProviderOption(item))
          .filter((item): item is ProviderOption => item !== null)
      : [];
    availablePlugins.value = Array.isArray(data.available_plugins)
      ? data.available_plugins
          .map((item) => normalizePluginOption(item))
          .filter((item): item is PluginOption => item !== null)
      : [];
    availableKbs.value = Array.isArray(data.available_kbs)
      ? data.available_kbs
          .map((item) => normalizeKnowledgeBaseOption(item))
          .filter((item): item is KnowledgeBaseOption => item !== null)
      : [];
  } catch {
    showError(tm('messages.loadError'));
  } finally {
    loading.value = false;
  }
}

function onTableOptionsUpdate(options: TableOptionsLike) {
  if (typeof options.page === 'number') {
    currentPage.value = options.page;
  }
  if (typeof options.itemsPerPage === 'number') {
    itemsPerPage.value = options.itemsPerPage;
  }
  void loadData();
}

async function loadUmos() {
  loadingUmos.value = true;
  try {
    const response = await sessionApi.activeUmos();
    if (response.data.status !== 'ok') {
      return;
    }

    mergeUmoInfos(response.data.data.umo_infos);
    const existingUmos = new Set(rulesList.value.map((item) => item.umo));
    const allUmos = normalizeStringArray(response.data.data.umos);
    availableUmos.value = allUmos.filter((umo) => !existingUmos.has(umo));
  } catch {
    showError(tm('messages.loadError'));
  } finally {
    loadingUmos.value = false;
  }
}

async function refreshData() {
  await loadData();
  showSuccess(tm('messages.refreshSuccess'));
}

async function openAddRuleDialog() {
  addRuleDialog.value = true;
  selectedNewUmo.value = null;
  await loadUmos();
}

function createNewRule() {
  if (!selectedNewUmo.value) {
    return;
  }

  const newItem = buildUmoItem(selectedNewUmo.value);
  addRuleDialog.value = false;
  openRuleEditor(newItem);
}

function openRuleEditor(item: SessionRuleItem) {
  selectedUmo.value = item;
  editingRules.value = item.rules || {};

  const svcConfig = editingRules.value.session_service_config || {};
  serviceConfig.session_enabled = svcConfig.session_enabled !== false;
  serviceConfig.llm_enabled = svcConfig.llm_enabled !== false;
  serviceConfig.tts_enabled = svcConfig.tts_enabled !== false;
  serviceConfig.custom_name = svcConfig.custom_name || '';
  serviceConfig.persona_id = svcConfig.persona_id || null;

  providerConfig.chat_completion =
    editingRules.value.provider_perf_chat_completion || FOLLOW_CONFIG_VALUE;
  providerConfig.speech_to_text =
    editingRules.value.provider_perf_speech_to_text || FOLLOW_CONFIG_VALUE;
  providerConfig.text_to_speech =
    editingRules.value.provider_perf_text_to_speech || FOLLOW_CONFIG_VALUE;

  const pluginRules = editingRules.value.session_plugin_config || {};
  pluginConfig.enabled_plugins = pluginRules.enabled_plugins || [];
  pluginConfig.disabled_plugins = pluginRules.disabled_plugins || [];

  const kbRules = editingRules.value.kb_config || {};
  kbConfig.kb_ids = kbRules.kb_ids || [];
  kbConfig.top_k = kbRules.top_k ?? 5;
  kbConfig.enable_rerank = kbRules.enable_rerank !== false;

  ruleDialog.value = true;
}

function closeRuleEditor() {
  ruleDialog.value = false;
  selectedUmo.value = null;
  editingRules.value = {};
}

async function saveServiceConfig() {
  if (!selectedUmo.value) {
    return;
  }

  saving.value = true;
  try {
    const config: SessionServiceConfig = {
      session_enabled: serviceConfig.session_enabled,
      llm_enabled: serviceConfig.llm_enabled,
      tts_enabled: serviceConfig.tts_enabled,
    };
    if (serviceConfig.custom_name) {
      config.custom_name = serviceConfig.custom_name;
    }
    if (serviceConfig.persona_id !== null) {
      config.persona_id = serviceConfig.persona_id;
    }

    const response = await sessionApi.upsertRule({
      umo: selectedUmo.value.umo,
      rule_key: 'session_service_config',
      rule_value: config,
    });

    if (response.data.status !== 'ok') {
      showError(response.data.message || tm('messages.saveError'));
      return;
    }

    editingRules.value.session_service_config = config;
    const item = ensureRuleItem(selectedUmo.value.umo);
    item.rules = { ...item.rules, session_service_config: config };
    showSuccess(tm('messages.saveSuccess'));
  } catch {
    showError(tm('messages.saveError'));
  } finally {
    saving.value = false;
  }
}

async function saveProviderConfig() {
  if (!selectedUmo.value) {
    return;
  }

  saving.value = true;
  try {
    const updateTasks: Promise<unknown>[] = [];
    const deleteTasks: Promise<unknown>[] = [];
    const providerTypes: ProviderRuleType[] = [
      'chat_completion',
      'speech_to_text',
      'text_to_speech',
    ];

    providerTypes.forEach((type) => {
      const value = providerConfig[type];
      const ruleKey = `provider_perf_${type}` as RuleKey;

      if (value && value !== FOLLOW_CONFIG_VALUE) {
        updateTasks.push(
          sessionApi.upsertRule({
            umo: selectedUmo.value!.umo,
            rule_key: ruleKey,
            rule_value: toRuleValue(value),
          }),
        );
      } else if (getProviderRule(editingRules.value, type)) {
        deleteTasks.push(
          sessionApi.deleteRules({
            umo: selectedUmo.value!.umo,
            rule_key: ruleKey,
          }),
        );
      }
    });

    const allTasks = [...updateTasks, ...deleteTasks];
    if (allTasks.length === 0) {
      showSuccess(tm('messages.noChanges'));
      return;
    }

    await Promise.all(allTasks);
    const item = ensureRuleItem(selectedUmo.value.umo);
    providerTypes.forEach((type) => {
      const value = providerConfig[type];
      if (value && value !== FOLLOW_CONFIG_VALUE) {
        setProviderRule(item.rules, type, value);
        setProviderRule(editingRules.value, type, value);
      } else {
        clearProviderRule(item.rules, type);
        clearProviderRule(editingRules.value, type);
      }
    });
    showSuccess(tm('messages.saveSuccess'));
  } catch {
    showError(tm('messages.saveError'));
  } finally {
    saving.value = false;
  }
}

async function savePluginConfig() {
  if (!selectedUmo.value) {
    return;
  }

  saving.value = true;
  try {
    const config = {
      enabled_plugins: [...pluginConfig.enabled_plugins],
      disabled_plugins: [...pluginConfig.disabled_plugins],
    };

    if (
      config.enabled_plugins.length === 0 &&
      config.disabled_plugins.length === 0
    ) {
      if (editingRules.value.session_plugin_config) {
        await sessionApi.deleteRules({
          umo: selectedUmo.value.umo,
          rule_key: 'session_plugin_config',
        });
        delete editingRules.value.session_plugin_config;
        const item = findRuleItem(selectedUmo.value.umo);
        if (item) {
          delete item.rules.session_plugin_config;
        }
      }
      showSuccess(tm('messages.saveSuccess'));
      return;
    }

    const response = await sessionApi.upsertRule({
      umo: selectedUmo.value.umo,
      rule_key: 'session_plugin_config',
      rule_value: toRuleValue(config),
    });

    if (response.data.status !== 'ok') {
      showError(response.data.message || tm('messages.saveError'));
      return;
    }

    editingRules.value.session_plugin_config = config;
    const item = ensureRuleItem(selectedUmo.value.umo);
    item.rules.session_plugin_config = config;
    showSuccess(tm('messages.saveSuccess'));
  } catch {
    showError(tm('messages.saveError'));
  } finally {
    saving.value = false;
  }
}

async function saveKbConfig() {
  if (!selectedUmo.value) {
    return;
  }

  saving.value = true;
  try {
    const config = {
      kb_ids: [...kbConfig.kb_ids],
      top_k: kbConfig.top_k,
      enable_rerank: kbConfig.enable_rerank,
    };

    if (config.kb_ids.length === 0) {
      if (editingRules.value.kb_config) {
        await sessionApi.deleteRules({
          umo: selectedUmo.value.umo,
          rule_key: 'kb_config',
        });
        delete editingRules.value.kb_config;
        const item = findRuleItem(selectedUmo.value.umo);
        if (item) {
          delete item.rules.kb_config;
        }
      }
      showSuccess(tm('messages.saveSuccess'));
      return;
    }

    const response = await sessionApi.upsertRule({
      umo: selectedUmo.value.umo,
      rule_key: 'kb_config',
      rule_value: toRuleValue(config),
    });

    if (response.data.status !== 'ok') {
      showError(response.data.message || tm('messages.saveError'));
      return;
    }

    editingRules.value.kb_config = config;
    const item = ensureRuleItem(selectedUmo.value.umo);
    item.rules.kb_config = config;
    showSuccess(tm('messages.saveSuccess'));
  } catch {
    showError(tm('messages.saveError'));
  } finally {
    saving.value = false;
  }
}

function confirmDeleteRules(item: SessionRuleItem) {
  deleteTarget.value = item;
  deleteDialog.value = true;
}

async function deleteAllRules() {
  if (!deleteTarget.value) {
    return;
  }

  deleting.value = true;
  try {
    const response = await sessionApi.deleteRules({
      umo: deleteTarget.value.umo,
    });

    if (response.data.status !== 'ok') {
      showError(response.data.message || tm('messages.deleteError'));
      return;
    }

    const index = rulesList.value.findIndex(
      (item) => item.umo === deleteTarget.value!.umo,
    );
    if (index > -1) {
      rulesList.value.splice(index, 1);
    }

    deleteDialog.value = false;
    deleteTarget.value = null;
    await loadData();
    showSuccess(tm('messages.deleteSuccess'));
  } catch {
    showError(tm('messages.deleteError'));
  } finally {
    deleting.value = false;
  }
}

function confirmBatchDelete() {
  if (selectedItems.value.length === 0) {
    return;
  }
  batchDeleteDialog.value = true;
}

async function batchDeleteRules() {
  if (selectedItems.value.length === 0) {
    return;
  }

  deleting.value = true;
  try {
    const response = await sessionApi.deleteRules({
      umos: selectedItems.value.map((item) => item.umo),
    });

    if (response.data.status !== 'ok') {
      showError(response.data.message || tm('messages.batchDeleteError'));
      return;
    }

    const data = response.data.data;
    const message =
      typeof data.message === 'string'
        ? data.message
        : tm('messages.batchDeleteSuccess');
    batchDeleteDialog.value = false;
    selectedItems.value = [];
    await loadData();
    showSuccess(message);
  } catch {
    showError(tm('messages.batchDeleteError'));
  } finally {
    deleting.value = false;
  }
}

function showSuccess(message: string) {
  snackbarText.value = message;
  snackbarColor.value = 'success';
  snackbar.value = true;
}

function showError(message: string) {
  snackbarText.value = message;
  snackbarColor.value = 'error';
  snackbar.value = true;
}

function openQuickEditName(item: SessionRuleItem) {
  quickEditNameTarget.value = item;
  quickEditNameValue.value =
    item.rules?.session_service_config?.custom_name || '';
  quickEditNameDialog.value = true;
}

async function saveQuickEditName() {
  if (!quickEditNameTarget.value) {
    return;
  }

  saving.value = true;
  try {
    const existingConfig =
      quickEditNameTarget.value.rules?.session_service_config || {};
    const config: SessionServiceConfig = {
      ...existingConfig,
      session_enabled: existingConfig.session_enabled !== false,
      llm_enabled: existingConfig.llm_enabled !== false,
      tts_enabled: existingConfig.tts_enabled !== false,
    };

    if (quickEditNameValue.value) {
      config.custom_name = quickEditNameValue.value;
    } else {
      delete config.custom_name;
    }

    const response = await sessionApi.upsertRule({
      umo: quickEditNameTarget.value.umo,
      rule_key: 'session_service_config',
      rule_value: config,
    });

    if (response.data.status !== 'ok') {
      showError(response.data.message || tm('messages.saveError'));
      return;
    }

    const item = ensureRuleItem(quickEditNameTarget.value.umo);
    item.rules.session_service_config = config;
    quickEditNameDialog.value = false;
    quickEditNameTarget.value = null;
    quickEditNameValue.value = '';
    showSuccess(tm('messages.saveSuccess'));
  } catch {
    showError(tm('messages.saveError'));
  } finally {
    saving.value = false;
  }
}

async function applyBatchChanges() {
  batchUpdating.value = true;
  try {
    let scope = batchScope.value;
    let groupId: string | null = null;
    let umos: string[] = [];

    if (scope.startsWith('custom_group:')) {
      groupId = scope.split(':')[1] || null;
      scope = 'custom_group';
    }

    if (scope === 'selected') {
      umos = selectedItems.value.map((item) => item.umo);
      if (umos.length === 0) {
        showError(tm('messages.selectSessionsFirst'));
        return;
      }
    }

    const targetPayload = buildBatchTargetPayload(scope, groupId, umos);
    const tasks: Promise<unknown>[] = [];

    if (batchLlmStatus.value !== null || batchTtsStatus.value !== null) {
      const serviceData: BatchSessionServiceRequest = { ...targetPayload };
      if (batchLlmStatus.value !== null) {
        serviceData.llm_enabled = batchLlmStatus.value;
      }
      if (batchTtsStatus.value !== null) {
        serviceData.tts_enabled = batchTtsStatus.value;
      }
      tasks.push(sessionApi.batchUpdateService(serviceData));
    }

    if (batchChatProvider.value !== null) {
      if (batchChatProvider.value === FOLLOW_CONFIG_VALUE) {
        tasks.push(
          sessionApi.deleteRules({
            ...targetPayload,
            rule_key: 'provider_perf_chat_completion',
          }),
        );
      } else {
        const providerData: BatchSessionProviderRequest = {
          ...targetPayload,
          provider_type: 'chat_completion',
          provider_id: batchChatProvider.value,
        };
        tasks.push(sessionApi.batchUpdateProvider(providerData));
      }
    }

    if (batchTtsProvider.value !== null) {
      if (batchTtsProvider.value === FOLLOW_CONFIG_VALUE) {
        tasks.push(
          sessionApi.deleteRules({
            ...targetPayload,
            rule_key: 'provider_perf_text_to_speech',
          }),
        );
      } else {
        const providerData: BatchSessionProviderRequest = {
          ...targetPayload,
          provider_type: 'text_to_speech',
          provider_id: batchTtsProvider.value,
        };
        tasks.push(sessionApi.batchUpdateProvider(providerData));
      }
    }

    if (tasks.length === 0) {
      showError(tm('messages.selectAtLeastOneConfig'));
      return;
    }

    const results = await Promise.all(tasks);
    const allOk = results.every((result) => {
      if (!result || typeof result !== 'object') {
        return false;
      }

      const responseData = (result as { data?: { status?: string } }).data;
      return responseData?.status === 'ok';
    });

    if (!allOk) {
      showError(tm('messages.partialUpdateFailed'));
      return;
    }

    batchLlmStatus.value = null;
    batchTtsStatus.value = null;
    batchChatProvider.value = null;
    batchTtsProvider.value = null;
    await loadData();
    showSuccess(tm('messages.batchUpdateSuccess'));
  } catch {
    showError(tm('messages.batchUpdateError'));
  } finally {
    batchUpdating.value = false;
  }
}

async function loadGroups() {
  groupsLoading.value = true;
  try {
    const response = await sessionApi.listGroups();
    if (response.data.status !== 'ok') {
      return;
    }

    const rawData = response.data.data;
    const rawGroups: unknown[] =
      rawData &&
      typeof rawData === 'object' &&
      'groups' in rawData &&
      Array.isArray(rawData.groups)
        ? rawData.groups
        : [];

    groups.value = rawGroups
      .map((group) => normalizeGroup(group))
      .filter((group): group is GroupItem => group !== null);
  } catch (error) {
    console.error('加载分组失败:', error);
  } finally {
    groupsLoading.value = false;
  }
}

async function loadAvailableUmos() {
  if (availableUmos.value.length > 0) {
    return;
  }

  loadingUmos.value = true;
  try {
    const response = await sessionApi.activeUmos();
    if (response.data.status !== 'ok') {
      return;
    }

    mergeUmoInfos(response.data.data.umo_infos);
    availableUmos.value = normalizeStringArray(response.data.data.umos);
  } catch (error) {
    console.error('加载会话列表失败:', error);
  } finally {
    loadingUmos.value = false;
  }
}

function openCreateGroupDialog() {
  groupDialogMode.value = 'create';
  resetGroupEditor();
  groupDialog.value = true;
}

function openEditGroupDialog(group: GroupItem) {
  groupDialogMode.value = 'edit';
  editingGroup.id = group.id;
  editingGroup.name = group.name;
  editingGroup.umos = [...group.umos];
  groupMemberSearch.value = '';
  groupSelectedSearch.value = '';
  groupDialog.value = true;
}

function addToGroup(umo: string) {
  if (!editingGroup.umos.includes(umo)) {
    editingGroup.umos.push(umo);
  }
}

function removeFromGroup(umo: string) {
  const index = editingGroup.umos.indexOf(umo);
  if (index > -1) {
    editingGroup.umos.splice(index, 1);
  }
}

function addAllToGroup() {
  unselectedUmos.value.forEach((umo) => {
    if (!editingGroup.umos.includes(umo)) {
      editingGroup.umos.push(umo);
    }
  });
}

function removeAllFromGroup() {
  editingGroup.umos = [];
}

async function saveGroup() {
  if (!editingGroup.name.trim()) {
    showError(tm('messages.groupNameRequired'));
    return;
  }

  try {
    const payload = {
      name: editingGroup.name,
      umos: editingGroup.umos,
    };

    const response =
      groupDialogMode.value === 'create'
        ? await sessionApi.createGroup(payload)
        : await sessionApi.updateGroup(editingGroup.id || '', payload);

    if (response.data.status !== 'ok') {
      showError(response.data.message || tm('messages.saveGroupError'));
      return;
    }

    const data =
      response.data.data && typeof response.data.data === 'object'
        ? (response.data.data as Record<string, unknown>)
        : {};
    const message =
      typeof data.message === 'string'
        ? data.message
        : tm('messages.saveSuccess');

    groupDialog.value = false;
    await loadGroups();
    showSuccess(message);
  } catch {
    showError(tm('messages.saveGroupError'));
  }
}

async function deleteGroup(group: GroupItem) {
  const message = tm('groups.deleteConfirm', { name: group.name });
  if (!(await askForConfirmationDialog(message, confirmDialog))) {
    return;
  }

  try {
    const response = await sessionApi.deleteGroup(group.id);
    if (response.data.status !== 'ok') {
      showError(response.data.message || tm('messages.deleteGroupError'));
      return;
    }

    const data =
      response.data.data && typeof response.data.data === 'object'
        ? (response.data.data as Record<string, unknown>)
        : {};
    const successMessage =
      typeof data.message === 'string'
        ? data.message
        : tm('messages.deleteSuccess');

    await loadGroups();
    showSuccess(successMessage);
  } catch {
    showError(tm('messages.deleteGroupError'));
  }
}

async function addSelectedToGroup(groupId: string) {
  if (selectedItems.value.length === 0) {
    showError(tm('messages.selectSessionsToAddFirst'));
    return;
  }

  try {
    const response = await sessionApi.updateGroup(groupId, {
      add_umos: selectedItems.value.map((item) => item.umo),
    });

    if (response.data.status !== 'ok') {
      showError(response.data.message || tm('messages.addToGroupError'));
      return;
    }

    await loadGroups();
    showSuccess(
      tm('messages.addToGroupSuccess', {
        count: selectedItems.value.length,
      }),
    );
  } catch {
    showError(tm('messages.addToGroupError'));
  }
}
</script>

<style scoped>
.session-rules-table {
  font-size: 12px;
}

code {
  background-color: rgb(var(--v-theme-surface-variant));
  padding: 2px var(--astrbot-space-2);
  border-radius: 4px;
  font-size: 12px;
}

.transfer-list {
  max-height: 280px;
  overflow-y: auto;
  border: 1px solid rgb(var(--v-theme-outline-variant));
  border-radius: 8px;
  overscroll-behavior: contain;
}

.session-group-dialog__card {
  display: flex;
  flex-direction: column;
  max-height: min(88dvh, 900px);
}

.session-group-dialog__content {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
}

.session-group-dialog__actions {
  flex-shrink: 0;
}

.transfer-item {
  cursor: pointer;
  min-height: 44px;
  padding-top: var(--astrbot-space-1);
  padding-bottom: var(--astrbot-space-1);
}

.transfer-item:hover {
  background-color: rgb(var(--v-theme-surface-variant));
}

.umo-list-platform {
  max-width: 92px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.umo-selection-chip {
  max-width: 100%;
}

.session-selection-list {
  max-height: 200px;
  overflow-y: auto;
}
</style>
