<template>
  <v-dialog
    v-model="showDialog"
    max-width="800px"
    max-height="90%"
    scrollable
    @after-enter="prepareData"
  >
    <v-card
      class="app-dialog platform-dialog__card"
      :title="
        updatingMode
          ? `${tm('dialog.edit')} ${updatingPlatformConfig.id} ${tm(
              'dialog.adapter',
            )}`
          : tm('dialog.addPlatform')
      "
    >
      <v-card-text
        ref="dialogScrollContainer"
        class="pa-4 ml-2 platform-dialog__content"
      >
        <div class="platform-dialog__step">
          <div>
            <v-icon icon="mdi-numeric-1-circle" class="mr-3"></v-icon>
          </div>
          <div class="platform-dialog__step-content">
            <h3>
              {{ tm('createDialog.step1Title') }}
            </h3>
            <small class="text-medium-emphasis">{{
              tm('createDialog.step1Hint')
            }}</small>
            <div>
              <div v-if="!updatingMode">
                <v-select
                  v-model="selectedPlatformType"
                  :items="Object.keys(platformTemplates)"
                  item-title="name"
                  item-value="name"
                  :label="tm('createDialog.platformTypeLabel')"
                  variant="outlined"
                  rounded="md"
                  density="comfortable"
                  hide-details
                  class="mt-6 platform-type-field"
                >
                  <template #item="{ props: itemProps, item }">
                    <v-list-item v-bind="itemProps">
                      <template #prepend>
                        <img
                          :src="getPlatformTemplateIcon(item)"
                          class="platform-template-icon"
                        />
                      </template>
                      <v-tooltip
                        v-if="
                          [
                            'qq_official',
                            'qq_official_webhook',
                            'aiocqhttp',
                            'weixin_oc',
                          ].includes(platformTemplates[item]?.type ?? '')
                        "
                        activator="parent"
                        :text="
                          tm(
                            `createDialog.platformTooltips.${platformTemplates[item]?.type ?? ''}`,
                          )
                        "
                        location="end"
                        max-width="360"
                        open-delay="50"
                      />
                    </v-list-item>
                  </template>
                </v-select>
                <div v-if="selectedPlatformConfig" class="mt-3">
                  <div v-if="isLarkPlatform">
                    <div class="creation-mode-title mt-4 mb-1">
                      {{ tm('registrationAction.mode.title') }}
                    </div>
                    <v-radio-group
                      v-model="larkCreationMode"
                      class="creation-mode-group"
                      hide-details
                    >
                      <v-radio
                        value="scan"
                        :label="tm('registrationAction.mode.scan')"
                      ></v-radio>
                      <v-radio
                        value="manual"
                        :label="tm('registrationAction.mode.larkManual')"
                      ></v-radio>
                    </v-radio-group>

                    <div
                      v-if="larkCreationMode === 'scan'"
                      class="registration-inline mt-3"
                    >
                      <v-text-field
                        :model-value="selectedPlatformConfig.id || ''"
                        :label="tm('registrationAction.platformIdLabel')"
                        :error="Boolean(scanPlatformIdError)"
                        :error-messages="scanPlatformIdError"
                        variant="outlined"
                        density="compact"
                        hide-details="auto"
                        class="registration-platform-id-field"
                        @update:model-value="setScanPlatformId"
                      />
                      <PlatformRegistrationAction
                        :platform-config="selectedPlatformConfig"
                        :active="larkCreationMode === 'scan'"
                        @created="handlePlatformRegistrationCreated"
                        @success="showSuccess"
                        @error="showError"
                      />
                    </div>

                    <div v-else-if="larkCreationMode === 'manual'" class="mt-2">
                      <div class="platform-action-row">
                        <v-btn
                          color="info"
                          variant="tonal"
                          class="mt-2"
                          @click="openTutorial"
                        >
                          <v-icon start>mdi-book-open-variant</v-icon>
                          {{ tm('dialog.viewTutorial') }}
                        </v-btn>
                      </div>
                      <AstrBotConfig
                        :iterable="selectedPlatformConfig"
                        :metadata="platformMetadata"
                        metadata-key="platform"
                      />
                    </div>
                  </div>

                  <div v-else-if="isDingtalkPlatform">
                    <div class="creation-mode-title mt-4 mb-1">
                      {{ tm('registrationAction.mode.title') }}
                    </div>
                    <v-radio-group
                      v-model="dingtalkCreationMode"
                      class="creation-mode-group"
                      hide-details
                    >
                      <v-radio
                        value="scan"
                        :label="tm('registrationAction.mode.scan')"
                      ></v-radio>
                      <v-radio
                        value="manual"
                        :label="tm('registrationAction.mode.manual')"
                      ></v-radio>
                    </v-radio-group>

                    <div
                      v-if="dingtalkCreationMode === 'scan'"
                      class="registration-inline mt-3"
                    >
                      <v-text-field
                        :model-value="selectedPlatformConfig.id || ''"
                        :label="tm('registrationAction.platformIdLabel')"
                        :error="Boolean(scanPlatformIdError)"
                        :error-messages="scanPlatformIdError"
                        variant="outlined"
                        density="compact"
                        hide-details="auto"
                        class="registration-platform-id-field"
                        @update:model-value="setScanPlatformId"
                      />
                      <PlatformRegistrationAction
                        :platform-config="selectedPlatformConfig"
                        :active="dingtalkCreationMode === 'scan'"
                        @created="handlePlatformRegistrationCreated"
                        @success="showSuccess"
                        @error="showError"
                      />
                    </div>

                    <div
                      v-else-if="dingtalkCreationMode === 'manual'"
                      class="mt-2"
                    >
                      <div class="platform-action-row">
                        <v-btn
                          color="info"
                          variant="tonal"
                          class="mt-2"
                          @click="openTutorial"
                        >
                          <v-icon start>mdi-book-open-variant</v-icon>
                          {{ tm('dialog.viewTutorial') }}
                        </v-btn>
                      </div>
                      <AstrBotConfig
                        :iterable="selectedPlatformConfig"
                        :metadata="platformMetadata"
                        metadata-key="platform"
                      />
                    </div>
                  </div>

                  <div v-else-if="isQqOfficialPlatform">
                    <div class="creation-mode-title mt-4 mb-1">
                      {{ tm('registrationAction.mode.title') }}
                    </div>
                    <v-radio-group
                      v-model="qqOfficialCreationMode"
                      class="creation-mode-group"
                      hide-details
                    >
                      <v-radio
                        value="scan"
                        :label="tm('registrationAction.mode.scan')"
                      ></v-radio>
                      <v-radio
                        value="manual"
                        :label="tm('registrationAction.mode.manual')"
                      ></v-radio>
                    </v-radio-group>

                    <div
                      v-if="qqOfficialCreationMode === 'scan'"
                      class="registration-inline mt-3"
                    >
                      <v-text-field
                        :model-value="selectedPlatformConfig.id || ''"
                        :label="tm('registrationAction.platformIdLabel')"
                        :error="Boolean(scanPlatformIdError)"
                        :error-messages="scanPlatformIdError"
                        variant="outlined"
                        density="compact"
                        hide-details="auto"
                        class="registration-platform-id-field"
                        @update:model-value="setScanPlatformId"
                      />
                      <PlatformRegistrationAction
                        :platform-config="selectedPlatformConfig"
                        :active="qqOfficialCreationMode === 'scan'"
                        @created="handlePlatformRegistrationCreated"
                        @success="showSuccess"
                        @error="showError"
                      />
                    </div>

                    <div
                      v-else-if="qqOfficialCreationMode === 'manual'"
                      class="mt-2"
                    >
                      <div class="platform-action-row">
                        <v-btn
                          color="info"
                          variant="tonal"
                          class="mt-2"
                          @click="openTutorial"
                        >
                          <v-icon start>mdi-book-open-variant</v-icon>
                          {{ tm('dialog.viewTutorial') }}
                        </v-btn>
                      </div>
                      <AstrBotConfig
                        :iterable="selectedPlatformConfig"
                        :metadata="platformMetadata"
                        metadata-key="platform"
                      />
                    </div>
                  </div>

                  <div
                    v-else-if="isWeixinOcPlatform"
                    class="registration-inline mt-4"
                  >
                    <v-text-field
                      :model-value="selectedPlatformConfig.id || ''"
                      :label="tm('registrationAction.platformIdLabel')"
                      :error="Boolean(scanPlatformIdError)"
                      :error-messages="scanPlatformIdError"
                      variant="outlined"
                      density="compact"
                      hide-details="auto"
                      class="registration-platform-id-field"
                      @update:model-value="setScanPlatformId"
                    />
                    <PlatformRegistrationAction
                      :platform-config="selectedPlatformConfig"
                      :active="isWeixinOcPlatform"
                      @created="handlePlatformRegistrationCreated"
                      @success="showSuccess"
                      @error="showError"
                    />
                  </div>

                  <div v-else class="mt-2">
                    <div class="platform-action-row">
                      <v-btn
                        color="info"
                        variant="tonal"
                        class="mt-2"
                        @click="openTutorial"
                      >
                        <v-icon start>mdi-book-open-variant</v-icon>
                        {{ tm('dialog.viewTutorial') }}
                      </v-btn>
                    </div>
                    <AstrBotConfig
                      :iterable="selectedPlatformConfig"
                      :metadata="platformMetadata"
                      metadata-key="platform"
                    />
                  </div>
                </div>
              </div>
              <div v-else>
                <v-text-field
                  v-model="updatingPlatformConfig.type"
                  :label="tm('createDialog.platformTypeLabel')"
                  variant="outlined"
                  rounded="md"
                  density="comfortable"
                  hide-details
                  class="mt-6 platform-type-field"
                  disabled
                ></v-text-field>
                <div class="mt-3">
                  <div class="mt-2">
                    <AstrBotConfig
                      :iterable="updatingPlatformConfig"
                      :metadata="platformMetadata"
                      metadata-key="platform"
                    />
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="platform-dialog__step mt-6">
          <div>
            <v-icon icon="mdi-numeric-2-circle" class="mr-3"></v-icon>
          </div>
          <div class="platform-dialog__step-content">
            <div class="d-flex align-center justify-space-between">
              <div>
                <div class="d-flex align-center">
                  <h3>
                    {{ tm('createDialog.configFileTitle') }}
                  </h3>
                  <v-chip
                    v-if="!updatingMode"
                    size="x-small"
                    color="primary"
                    variant="tonal"
                    rounded="sm"
                    class="ml-2"
                    >{{ tm('createDialog.optional') }}</v-chip
                  >
                </div>
                <small class="text-medium-emphasis">{{
                  tm('createDialog.configHint')
                }}</small>
                <small v-if="!updatingMode" class="text-medium-emphasis">{{
                  tm('createDialog.configDefaultHint')
                }}</small>
              </div>
              <div>
                <v-btn
                  variant="plain"
                  icon
                  class="mt-2"
                  @click="toggleConfigSection"
                >
                  <v-icon>{{
                    showConfigSection ? 'mdi-chevron-up' : 'mdi-chevron-down'
                  }}</v-icon>
                </v-btn>
              </div>
            </div>

            <div v-if="showConfigSection">
              <div v-if="!updatingMode">
                <v-radio-group
                  v-model="aBConfigRadioVal"
                  class="mt-2"
                  hide-details
                >
                  <v-radio value="0">
                    <template #label>
                      <span>{{ tm('createDialog.useExistingConfig') }}</span>
                    </template>
                  </v-radio>
                  <div
                    v-if="aBConfigRadioVal === '0'"
                    class="d-flex align-center ml-10 my-2"
                  >
                    <v-select
                      v-model="selectedAbConfId"
                      :items="configInfoList"
                      item-title="name"
                      item-value="id"
                      :label="tm('createDialog.selectConfigLabel')"
                      variant="outlined"
                      rounded="md"
                      density="comfortable"
                      hide-details
                      class="platform-config-select"
                    >
                    </v-select>
                    <v-btn
                      icon
                      variant="text"
                      density="comfortable"
                      class="ml-2"
                      :disabled="!selectedAbConfId"
                      @click="openConfigDrawer(selectedAbConfId)"
                    >
                      <v-icon>mdi-arrow-top-right-thick</v-icon>
                    </v-btn>
                  </div>
                  <v-radio
                    value="1"
                    :label="tm('createDialog.createNewConfig')"
                  >
                  </v-radio>
                  <div
                    v-if="aBConfigRadioVal === '1'"
                    class="d-flex align-center"
                  >
                    <v-text-field
                      v-model="selectedAbConfId"
                      :label="tm('createDialog.newConfigNameLabel')"
                      variant="outlined"
                      rounded="md"
                      density="comfortable"
                      hide-details
                      class="ml-10 my-2 platform-config-select"
                    >
                    </v-text-field>
                  </div>
                </v-radio-group>

                <!-- 新配置文件编辑区域 -->
                <div v-if="aBConfigRadioVal === '1'" class="mt-4">
                  <div
                    v-if="newConfigLoading"
                    class="d-flex justify-center py-4"
                  >
                    <v-progress-circular
                      indeterminate
                      color="primary"
                    ></v-progress-circular>
                  </div>
                  <div
                    v-else-if="newConfigData && newConfigMetadata"
                    class="config-preview-container"
                  >
                    <h4 class="mb-3">
                      {{ tm('createDialog.newConfigTitle') }}
                    </h4>
                    <AstrBotCoreConfigWrapper
                      :metadata="newConfigMetadata"
                      :config-data="newConfigData"
                    />
                  </div>
                  <div v-else class="text-center py-4 text-medium-emphasis">
                    <v-icon>mdi-information-outline</v-icon>
                    <p class="mt-2">
                      {{ tm('createDialog.newConfigLoadFailed') }}
                    </p>
                  </div>
                </div>
              </div>

              <div v-else>
                <div class="mb-3 d-flex align-center justify-space-between">
                  <div>
                    <v-btn
                      v-if="isEditingRoutes"
                      color="primary"
                      variant="tonal"
                      size="small"
                      @click="addNewRoute"
                    >
                      <v-icon start>mdi-plus</v-icon>
                      {{ tm('createDialog.addRouteRule') }}
                    </v-btn>
                  </div>
                  <v-btn
                    :color="isEditingRoutes ? 'on-surface-variant' : 'primary'"
                    variant="tonal"
                    size="small"
                    @click="toggleEditMode"
                  >
                    <v-icon start>{{
                      isEditingRoutes ? 'mdi-eye' : 'mdi-pencil'
                    }}</v-icon>
                    {{
                      isEditingRoutes
                        ? tm('createDialog.viewMode')
                        : tm('createDialog.editMode')
                    }}
                  </v-btn>
                </div>

                <v-data-table
                  :headers="routeTableHeaders"
                  :items="platformRoutes"
                  item-value="umop"
                  :no-data-text="tm('createDialog.noRouteRules')"
                  hide-default-footer
                  :items-per-page="-1"
                  class="mt-2"
                  variant="outlined"
                >
                  <template #item.source="{ item }">
                    <div class="route-source-cell">
                      <div
                        class="d-flex align-center route-source-input-row"
                        :class="{
                          'route-source-input-row--editing': isEditingRoutes,
                        }"
                      >
                        <v-autocomplete
                          v-if="
                            isEditingRoutes &&
                            updatingMode &&
                            getRouteSourceMode(item) === 'known'
                          "
                          v-model="item.sourceUmo"
                          :items="filteredKnownRouteUmoItems"
                          :loading="loadingKnownRouteUmos"
                          variant="outlined"
                          density="compact"
                          hide-details
                          clearable
                          :placeholder="
                            tm('createDialog.routeSource.selectPlaceholder')
                          "
                          :no-data-text="tm('createDialog.routeSource.noData')"
                          class="route-source-autocomplete"
                          @update:model-value="
                            applyKnownRouteSource(item, $event)
                          "
                          @focus="loadKnownRouteUmos"
                        >
                          <template
                            #item="{ props: sourceItemProps, item: sourceItem }"
                          >
                            <v-list-item v-bind="sourceItemProps">
                              <template #title>
                                <UmoDisplay
                                  v-bind="
                                    getKnownRouteUmoDisplayProps(sourceItem)
                                  "
                                  compact
                                  :show-info="false"
                                />
                              </template>
                            </v-list-item>
                          </template>
                          <template #selection="{ item: sourceItem }">
                            <v-chip
                              v-if="
                                sourceItem &&
                                getKnownRouteUmoSelectionText(sourceItem)
                              "
                              size="small"
                              variant="tonal"
                              color="primary"
                              class="umo-selection-chip"
                            >
                              {{ getKnownRouteUmoSelectionText(sourceItem) }}
                            </v-chip>
                          </template>
                        </v-autocomplete>
                        <template v-else>
                          <v-select
                            v-if="isEditingRoutes"
                            v-model="item.messageType"
                            :items="messageTypeOptions"
                            item-title="label"
                            item-value="value"
                            variant="outlined"
                            density="compact"
                            hide-details
                            class="route-message-type-field"
                          >
                          </v-select>
                          <small v-else>{{
                            getMessageTypeLabel(item.messageType)
                          }}</small>
                          <small class="mx-1">:</small>
                          <v-text-field
                            v-if="isEditingRoutes"
                            v-model="item.sessionId"
                            variant="outlined"
                            density="compact"
                            hide-details
                            :placeholder="
                              tm('createDialog.sessionIdPlaceholder')
                            "
                          >
                          </v-text-field>
                          <small v-else>{{
                            item.sessionId === '*'
                              ? tm('createDialog.allSessions')
                              : item.sessionId
                          }}</small>
                        </template>
                      </div>
                      <button
                        v-if="updatingMode && isEditingRoutes"
                        class="route-source-mode-link"
                        type="button"
                        @click="toggleRouteSourceMode(item)"
                      >
                        {{ getRouteSourceModeLinkText(item) }}
                      </button>
                    </div>
                  </template>

                  <template #item.configId="{ item }">
                    <div class="d-flex align-center">
                      <v-select
                        v-if="isEditingRoutes"
                        v-model="item.configId"
                        :items="configInfoList"
                        item-title="name"
                        item-value="id"
                        variant="outlined"
                        density="compact"
                        class="route-config-select"
                        hide-details
                      >
                      </v-select>
                      <div v-else>
                        <small>{{ getConfigName(item.configId) }}</small>
                      </div>
                      <v-btn
                        icon
                        variant="text"
                        density="compact"
                        class="ml-2"
                        :disabled="!item.configId"
                        @click="openConfigDrawer(item.configId)"
                      >
                        <v-icon size="18">mdi-arrow-top-right-thick</v-icon>
                      </v-btn>
                    </div>
                    <small
                      v-if="
                        configInfoList.findIndex(
                          (c) => c.id === item.configId,
                        ) === -1
                      "
                      class="route-config-missing ml-2"
                      >{{ tm('createDialog.configMissing') }}</small
                    >
                  </template>

                  <template #item.actions="{ index }">
                    <div v-if="isEditingRoutes" class="d-flex align-center">
                      <v-btn
                        icon
                        size="x-small"
                        variant="text"
                        :disabled="index === 0"
                        @click="moveRouteUp(index)"
                      >
                        <v-icon>mdi-arrow-up</v-icon>
                      </v-btn>
                      <v-btn
                        icon
                        size="x-small"
                        variant="text"
                        :disabled="index === platformRoutes.length - 1"
                        @click="moveRouteDown(index)"
                      >
                        <v-icon>mdi-arrow-down</v-icon>
                      </v-btn>
                      <v-btn
                        icon
                        size="x-small"
                        variant="text"
                        color="error"
                        @click="deleteRoute(index)"
                      >
                        <v-icon>mdi-delete</v-icon>
                      </v-btn>
                    </div>
                    <span v-else class="text-medium-emphasis">-</span>
                  </template>
                </v-data-table>
                <small class="ml-2 mt-2 d-block text-medium-emphasis">{{
                  tm('createDialog.routeHint')
                }}</small>
              </div>
            </div>
          </div>
        </div>
      </v-card-text>

      <v-card-actions class="platform-dialog__actions">
        <v-spacer></v-spacer>
        <v-btn text @click="closeDialog">{{ tm('dialog.cancel') }}</v-btn>
        <v-btn
          v-if="!updatingMode"
          :disabled="!canSave"
          color="primary"
          :loading="loading"
          @click="newPlatform"
          >{{ tm('dialog.save') }}</v-btn
        >
        <v-btn
          v-else
          :disabled="!selectedAbConfId"
          color="primary"
          :loading="loading"
          @click="newPlatform"
          >{{ tm('dialog.save') }}</v-btn
        >
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- ID冲突确认对话框 -->
  <v-dialog v-model="showIdConflictDialog" max-width="450" persistent>
    <v-card class="app-dialog">
      <v-card-title class="text-h6 bg-warning d-flex align-center">
        <v-icon start class="me-2">mdi-alert-circle-outline</v-icon>
        {{ tm('dialog.idConflict.title') }}
      </v-card-title>
      <v-card-text class="py-4 text-body-1 text-medium-emphasis">
        {{ tm('dialog.idConflict.message', { id: conflictId }) }}
      </v-card-text>
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn variant="text" @click="handleIdConflictConfirm(false)">{{
          tm('dialog.idConflict.confirm')
        }}</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- 安全警告对话框 -->
  <v-dialog v-model="showOneBotEmptyTokenWarnDialog" max-width="600" persistent>
    <v-card class="app-dialog">
      <v-card-title>
        {{ tm('dialog.securityWarning.title') }}
      </v-card-title>
      <v-card-text class="py-4">
        <p>{{ tm(oneBotTokenWarningMessageKey) }}</p>
        <span
          ><a :href="oneBotTokenWarningTutorialLink" target="_blank">{{
            tm('dialog.securityWarning.learnMore')
          }}</a></span
        >
      </v-card-text>
      <v-card-actions class="px-4 pb-4">
        <v-spacer></v-spacer>
        <v-btn
          color="error"
          @click="handleOneBotEmptyTokenWarningDismiss(true)"
        >
          {{ tm('createDialog.warningContinue') }}
        </v-btn>
        <v-btn
          color="primary"
          @click="handleOneBotEmptyTokenWarningDismiss(false)"
        >
          {{ tm('createDialog.warningEditAgain') }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <v-overlay
    v-model="showConfigDrawer"
    class="config-drawer-overlay"
    location="right"
    transition="slide-x-reverse-transition"
    :scrim="true"
    @click:outside="closeConfigDrawer"
  >
    <v-card class="app-dialog config-drawer-card">
      <div class="config-drawer-header">
        <div>
          <span class="text-h6">{{
            tm('createDialog.configDrawerTitle')
          }}</span>
          <div
            v-if="configDrawerTargetId"
            class="text-caption text-medium-emphasis"
          >
            {{ tm('createDialog.configDrawerIdLabel') }}:
            {{ configDrawerTargetId }}
          </div>
        </div>
        <v-btn icon variant="text" @click="closeConfigDrawer">
          <v-icon>mdi-close</v-icon>
        </v-btn>
      </div>
      <v-divider></v-divider>
      <div class="config-drawer-content">
        <ConfigPage
          v-if="showConfigDrawer"
          :initial-config-id="configDrawerTargetId || 'default'"
        />
      </div>
    </v-card>
  </v-overlay>
</template>

<script setup lang="ts">
import {
  botApi,
  configProfileApi,
  configRouteApi,
  fileApi,
  sessionApi,
} from '@/api/v1';
import { computed, nextTick, reactive, ref, toRefs, watch } from 'vue';
import { useModuleI18n } from '@/i18n/composables';
import {
  getPlatformIcon as getBasePlatformIcon,
  getTutorialLink,
} from '@/utils/platformUtils';
import { resolveErrorMessage } from '@/utils/errorUtils';
import AstrBotConfig from '@/components/shared/AstrBotConfig.vue';
import AstrBotCoreConfigWrapper from '@/components/config/AstrBotCoreConfigWrapper.vue';
import ConfigPage from '@/views/ConfigPage.vue';
import PlatformRegistrationAction from '@/components/platform/PlatformRegistrationAction.vue';
import UmoDisplay from '@/components/shared/UmoDisplay.vue';
import {
  runBotMutationWithStepUp,
  type RequestDashboardStepUp,
} from '@/utils/botStepUp';
import { runConfigMutationWithStepUp } from '@/utils/configStepUp';
import { stepUpHeaders } from '@/utils/stepUp';

defineOptions({
  name: 'AddNewPlatform',
});

type RecordValue = Record<string, unknown>;
type CreationMode = '' | 'scan' | 'manual';
type ConfigMode = '0' | '1';
type RouteSourceMode = 'manual' | 'known';

interface PlatformConfigItem extends RecordValue {
  id?: string;
  type?: string;
  app_id?: string;
  app_secret?: string;
  client_id?: string;
  client_secret?: string;
  appid?: string;
  secret?: string;
  weixin_oc_token?: string;
  ws_reverse_token?: string;
  logo_token?: string;
}

interface PlatformMetadataState extends RecordValue {
  platform_group?: {
    metadata?: RecordValue & {
      platform?: {
        config_template?: Record<string, PlatformConfigItem>;
      };
    };
  };
}

interface PlatformConfigState extends RecordValue {
  platform?: unknown[];
}

interface ConfigInfo extends RecordValue {
  id: string;
  name: string;
}

interface PlatformRoute {
  umop: string | null;
  originalUmop: string | null;
  sourceMode: RouteSourceMode;
  sourceUmo: string;
  messageType: string;
  sessionId: string;
  configId: string;
}

interface ParsedUmop {
  platform: string;
  messageType: string;
  sessionId: string;
}

interface KnownRouteUmoInfo extends RecordValue {
  umo: string;
  platform?: string;
  message_type?: string;
  session_id?: string;
  auto_name?: string;
  user_alias?: string;
  display_name?: string;
}

interface RegistrationCreatedPayload extends RecordValue {
  platform_id_suffix?: string;
  bot_name?: string;
}

interface ToastPayload {
  message: string;
  type: 'success' | 'error';
}

interface ComponentState {
  selectedPlatformType: string | null;
  selectedPlatformConfig: PlatformConfigItem | null;
  larkCreationMode: CreationMode;
  dingtalkCreationMode: CreationMode;
  qqOfficialCreationMode: CreationMode;
  aBConfigRadioVal: ConfigMode;
  selectedAbConfId: string | null;
  configInfoList: ConfigInfo[];
  newConfigData: RecordValue | null;
  newConfigMetadata: RecordValue | null;
  newConfigLoading: boolean;
  platformRoutes: PlatformRoute[];
  isEditingRoutes: boolean;
  knownRouteUmos: string[];
  knownRouteUmoInfoMap: Record<string, KnownRouteUmoInfo>;
  loadingKnownRouteUmos: boolean;
  showIdConflictDialog: boolean;
  conflictId: string;
  idConflictResolve: ((value: boolean) => void) | null;
  showOneBotEmptyTokenWarnDialog: boolean;
  oneBotTokenWarningPlatformType: string | null;
  oneBotEmptyTokenWarningResolve: ((value: boolean) => void) | null;
  scanPlatformIdCustomized: boolean;
  loading: boolean;
  showConfigSection: boolean;
  showConfigDrawer: boolean;
  configDrawerTargetId: string | null;
  originalUpdatingPlatformId: string | null;
}

interface Props {
  show?: boolean;
  metadata?: PlatformMetadataState;
  configData?: PlatformConfigState;
  updatingMode?: boolean;
  updatingPlatformConfig?: PlatformConfigItem;
  requestStepUp?: RequestDashboardStepUp;
}

type DialogScrollTarget = HTMLElement | { $el?: HTMLElement | null } | null;

const props = withDefaults(defineProps<Props>(), {
  show: false,
  metadata: () => ({}),
  configData: () => ({}),
  updatingMode: false,
  updatingPlatformConfig: () => ({}),
  requestStepUp: undefined,
});

const emit = defineEmits<{
  'update:show': [value: boolean];
  'show-toast': [payload: ToastPayload];
  'refresh-config': [];
}>();

const { tm } = useModuleI18n('features/platform');
const { metadata, configData, updatingMode, updatingPlatformConfig } =
  toRefs(props);

const state = reactive<ComponentState>({
  selectedPlatformType: null,
  selectedPlatformConfig: null,
  larkCreationMode: '',
  dingtalkCreationMode: '',
  qqOfficialCreationMode: '',
  aBConfigRadioVal: '0',
  selectedAbConfId: 'default',
  configInfoList: [],
  newConfigData: null,
  newConfigMetadata: null,
  newConfigLoading: false,
  platformRoutes: [],
  isEditingRoutes: false,
  knownRouteUmos: [],
  knownRouteUmoInfoMap: {},
  loadingKnownRouteUmos: false,
  showIdConflictDialog: false,
  conflictId: '',
  idConflictResolve: null,
  showOneBotEmptyTokenWarnDialog: false,
  oneBotTokenWarningPlatformType: null,
  oneBotEmptyTokenWarningResolve: null,
  scanPlatformIdCustomized: false,
  loading: false,
  showConfigSection: false,
  showConfigDrawer: false,
  configDrawerTargetId: null,
  originalUpdatingPlatformId: null,
});

const {
  selectedPlatformType,
  selectedPlatformConfig,
  larkCreationMode,
  dingtalkCreationMode,
  qqOfficialCreationMode,
  aBConfigRadioVal,
  selectedAbConfId,
  configInfoList,
  newConfigData,
  newConfigMetadata,
  newConfigLoading,
  platformRoutes,
  isEditingRoutes,
  loadingKnownRouteUmos,
  showIdConflictDialog,
  conflictId,
  showOneBotEmptyTokenWarnDialog,
  loading,
  showConfigSection,
  showConfigDrawer,
  configDrawerTargetId,
} = toRefs(state);

const dialogScrollContainer = ref<DialogScrollTarget>(null);
const ONEBOT_TOKEN_WARNING_PLATFORM_TYPES = new Set(['aiocqhttp', 'napcat']);

const showDialog = computed({
  get: () => props.show,
  set: (value: boolean) => void emit('update:show', value),
});

const platformTemplates = computed<Record<string, PlatformConfigItem>>(() =>
  normalizePlatformTemplates(
    metadata.value.platform_group?.metadata?.platform?.config_template,
  ),
);

const platformMetadata = computed<RecordValue>(
  () => metadata.value.platform_group?.metadata ?? {},
);

const canSave = computed(() => {
  if (
    !state.selectedPlatformType ||
    !isPlatformIdValid(state.selectedPlatformConfig?.id)
  ) {
    return false;
  }

  if (isLarkPlatform.value) {
    if (!state.larkCreationMode) {
      return false;
    }
    if (
      state.larkCreationMode === 'scan' &&
      (!state.selectedPlatformConfig?.app_id ||
        !state.selectedPlatformConfig?.app_secret)
    ) {
      return false;
    }
  }

  if (isDingtalkPlatform.value) {
    if (!state.dingtalkCreationMode) {
      return false;
    }
    if (
      state.dingtalkCreationMode === 'scan' &&
      (!state.selectedPlatformConfig?.client_id ||
        !state.selectedPlatformConfig?.client_secret)
    ) {
      return false;
    }
  }

  if (isQqOfficialPlatform.value) {
    if (!state.qqOfficialCreationMode) {
      return false;
    }
    if (
      state.qqOfficialCreationMode === 'scan' &&
      (!state.selectedPlatformConfig?.appid ||
        !state.selectedPlatformConfig?.secret)
    ) {
      return false;
    }
  }

  if (
    isWeixinOcPlatform.value &&
    !state.selectedPlatformConfig?.weixin_oc_token
  ) {
    return false;
  }

  if (state.aBConfigRadioVal === '0') {
    return Boolean(state.selectedAbConfId);
  }

  if (state.aBConfigRadioVal === '1') {
    return Boolean(state.selectedAbConfId && state.newConfigData);
  }

  return false;
});

const oneBotTokenWarningTutorialLink = computed(() =>
  getTutorialLink(state.oneBotTokenWarningPlatformType ?? 'aiocqhttp'),
);
const oneBotTokenWarningMessageKey = computed(() =>
  state.oneBotTokenWarningPlatformType === 'napcat'
    ? 'dialog.securityWarning.napcatTokenMissing'
    : 'dialog.securityWarning.aiocqhttpTokenMissing',
);

const routeTableHeaders = computed(() => [
  {
    title: tm('createDialog.routeTableHeaders.source'),
    key: 'source',
    sortable: false,
    width: '60%',
  },
  {
    title: tm('createDialog.routeTableHeaders.config'),
    key: 'configId',
    sortable: false,
    width: '20%',
  },
  {
    title: tm('createDialog.routeTableHeaders.actions'),
    key: 'actions',
    sortable: false,
    align: 'center' as const,
    width: '20%',
  },
]);

const messageTypeOptions = computed(() => [
  { label: tm('createDialog.messageTypeOptions.all'), value: '*' },
  {
    label: tm('createDialog.messageTypeOptions.group'),
    value: 'GroupMessage',
  },
  {
    label: tm('createDialog.messageTypeOptions.friend'),
    value: 'FriendMessage',
  },
]);

const routePlatformId = computed(() => {
  if (updatingMode.value) {
    return (
      getString(updatingPlatformConfig.value.id) ??
      state.originalUpdatingPlatformId ??
      ''
    );
  }
  return getString(state.selectedPlatformConfig?.id) ?? '';
});

const filteredKnownRouteUmoItems = computed(() => {
  const platformId = routePlatformId.value;
  return state.knownRouteUmos.filter(
    (umo) => parseUmop(umo)?.platform === platformId,
  );
});

const isLarkPlatform = computed(
  () => getString(state.selectedPlatformConfig?.type) === 'lark',
);
const isWeixinOcPlatform = computed(
  () => getString(state.selectedPlatformConfig?.type) === 'weixin_oc',
);
const isDingtalkPlatform = computed(
  () => getString(state.selectedPlatformConfig?.type) === 'dingtalk',
);
const isQqOfficialPlatform = computed(() =>
  ['qq_official', 'qq_official_webhook'].includes(
    getString(state.selectedPlatformConfig?.type) ?? '',
  ),
);
const scanPlatformIdError = computed(() => {
  const platformId = String(state.selectedPlatformConfig?.id || '');
  if (!platformId) {
    return tm('registrationAction.platformIdRequired');
  }
  if (!isPlatformIdValid(platformId)) {
    return tm('registrationAction.platformIdInvalid');
  }
  return '';
});

watch(selectedPlatformType, (newType) => {
  if (newType && platformTemplates.value[newType]) {
    state.selectedPlatformConfig = deepClone(platformTemplates.value[newType]);
  } else {
    state.selectedPlatformConfig = null;
  }
  state.larkCreationMode = '';
  state.dingtalkCreationMode = '';
  state.qqOfficialCreationMode = '';
  state.scanPlatformIdCustomized = false;
});

watch(aBConfigRadioVal, (newValue) => {
  if (newValue === '1') {
    state.selectedAbConfId = null;
    void getDefaultConfigTemplate();
    return;
  }

  state.newConfigData = null;
  state.newConfigMetadata = null;
  if (!state.selectedAbConfId) {
    state.selectedAbConfId = 'default';
  }
});

watch(showIdConflictDialog, (newValue) => {
  if (!newValue && state.idConflictResolve) {
    state.idConflictResolve(false);
    state.idConflictResolve = null;
  }
});

watch(showOneBotEmptyTokenWarnDialog, (newValue) => {
  if (!newValue && state.oneBotEmptyTokenWarningResolve) {
    state.oneBotEmptyTokenWarningResolve(true);
    state.oneBotEmptyTokenWarningResolve = null;
  }
});

watch(
  updatingPlatformConfig,
  (newConfig) => {
    const platformId = getString(newConfig?.id);
    if (updatingMode.value && platformId) {
      state.originalUpdatingPlatformId = platformId;
      void getPlatformConfigs(platformId);
    }
  },
  { immediate: true },
);

watch(showConfigSection, async (newValue) => {
  if (newValue) {
    await nextTick();
    scrollDialogToBottom();
  }
});

watch(
  updatingMode,
  (newValue) => {
    if (newValue) {
      state.showConfigSection = true;
      state.isEditingRoutes = false;
    }
  },
  { immediate: true },
);

function asRecord(value: unknown): RecordValue | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return null;
  }
  return value as RecordValue;
}

function getString(value: unknown): string | null {
  return typeof value === 'string' ? value : null;
}

function deepClone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function normalizePlatformConfig(value: unknown): PlatformConfigItem {
  const record = asRecord(value);
  return record ? { ...record } : {};
}

function normalizePlatformTemplates(
  value: unknown,
): Record<string, PlatformConfigItem> {
  const record = asRecord(value);
  if (!record) {
    return {};
  }

  const templates: Record<string, PlatformConfigItem> = {};
  for (const [key, templateValue] of Object.entries(record)) {
    templates[key] = normalizePlatformConfig(templateValue);
  }
  return templates;
}

function normalizePlatformConfigList(value: unknown): PlatformConfigItem[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.map((item) => normalizePlatformConfig(item));
}

function normalizeConfigInfoList(value: unknown): ConfigInfo[] {
  if (!Array.isArray(value)) {
    return [];
  }

  const infoList: ConfigInfo[] = [];
  for (const item of value) {
    const record = asRecord(item);
    const id = getString(record?.id);
    const name = getString(record?.name);
    if (record && id && name) {
      infoList.push({ ...record, id, name });
    }
  }
  return infoList;
}

function normalizeRoutingTable(value: unknown): Record<string, string> {
  const record = asRecord(value);
  if (!record) {
    return {};
  }

  const routing: Record<string, string> = {};
  for (const [umop, configId] of Object.entries(record)) {
    const normalizedConfigId = getString(configId);
    if (normalizedConfigId) {
      routing[umop] = normalizedConfigId;
    }
  }
  return routing;
}

function normalizeStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((item): item is string => typeof item === 'string');
}

function normalizeKnownRouteUmoInfos(value: unknown): KnownRouteUmoInfo[] {
  if (!Array.isArray(value)) {
    return [];
  }

  const infos: KnownRouteUmoInfo[] = [];
  for (const item of value) {
    const record = asRecord(item);
    const umo = getString(record?.umo);
    if (!record || !umo) {
      continue;
    }
    infos.push({
      ...record,
      umo,
      platform: getString(record.platform) ?? undefined,
      message_type: getString(record.message_type) ?? undefined,
      session_id: getString(record.session_id) ?? undefined,
      auto_name: getString(record.auto_name) ?? undefined,
      user_alias: getString(record.user_alias) ?? undefined,
      display_name: getString(record.display_name) ?? undefined,
    });
  }
  return infos;
}

function getPlatformIcon(platformType: string | undefined): string | undefined {
  const normalizedType = getString(platformType);
  if (!normalizedType) {
    return undefined;
  }

  const template = platformTemplates.value[normalizedType];
  const logoToken = getString(template?.logo_token);
  if (logoToken) {
    return fileApi.tokenUrl(logoToken);
  }
  return getBasePlatformIcon(normalizedType);
}

function getPlatformTemplateIcon(templateKey: string): string | undefined {
  const template = platformTemplates.value[templateKey];
  return getPlatformIcon(getString(template?.type) ?? templateKey);
}

function resetForm() {
  state.selectedPlatformType = null;
  state.selectedPlatformConfig = null;
  state.larkCreationMode = '';
  state.dingtalkCreationMode = '';
  state.qqOfficialCreationMode = '';
  state.scanPlatformIdCustomized = false;
  state.aBConfigRadioVal = '0';
  state.selectedAbConfId = 'default';
  state.newConfigData = null;
  state.newConfigMetadata = null;
  state.newConfigLoading = false;
  state.showConfigSection = false;
  state.isEditingRoutes = false;
  state.knownRouteUmos = [];
  state.knownRouteUmoInfoMap = {};
  state.loadingKnownRouteUmos = false;
  state.showConfigDrawer = false;
  state.configDrawerTargetId = null;
  state.originalUpdatingPlatformId = null;
}

function closeDialog() {
  resetForm();
  showDialog.value = false;
}

async function getConfigInfoList() {
  const res = await configProfileApi.list();
  state.configInfoList = normalizeConfigInfoList(res.data.data.info_list);
}

async function getDefaultConfigTemplate() {
  state.newConfigLoading = true;
  try {
    const response = await configProfileApi.schema();
    state.newConfigData = asRecord(response.data.data.config);
    state.newConfigMetadata = asRecord(response.data.data.metadata);
  } catch (error) {
    console.error('获取默认配置模板失败:', error);
    state.newConfigData = null;
    state.newConfigMetadata = null;
  } finally {
    state.newConfigLoading = false;
  }
}

function openTutorial() {
  const platformType = getString(state.selectedPlatformConfig?.type);
  if (!platformType) {
    return;
  }
  window.open(getTutorialLink(platformType), '_blank');
}

function openConfigDrawer(configId: string | null | undefined) {
  const targetId = configId || 'default';
  if (
    configId &&
    state.configInfoList.findIndex((config) => config.id === configId) === -1
  ) {
    showError(tm('messages.configNotFoundOpenConfig'));
  }
  state.configDrawerTargetId = targetId;
  state.showConfigDrawer = true;
}

function closeConfigDrawer() {
  state.showConfigDrawer = false;
}

async function newPlatform() {
  state.loading = true;
  if (updatingMode.value) {
    const platformType = getString(updatingPlatformConfig.value.type);
    const token = getOneBotSecurityToken(updatingPlatformConfig.value)?.trim();
    if (
      platformType &&
      ONEBOT_TOKEN_WARNING_PLATFORM_TYPES.has(platformType) &&
      !token
    ) {
      const continueWithWarning =
        await showOneBotEmptyTokenWarning(platformType);
      if (!continueWithWarning) {
        state.loading = false;
        return;
      }
    }
    await updatePlatform();
    return;
  }

  await savePlatform();
}

async function updatePlatform() {
  const platformId =
    state.originalUpdatingPlatformId ??
    getString(updatingPlatformConfig.value.id);
  if (!platformId) {
    state.loading = false;
    showError(tm('messages.updateMissingPlatformId'));
    return;
  }

  if (!isPlatformIdValid(platformId)) {
    state.loading = false;
    showError(tm('dialog.invalidPlatformId'));
    return;
  }

  try {
    const resp = await runBotMutationWithStepUp(
      (stepUp) =>
        stepUp
          ? botApi.update(platformId, updatingPlatformConfig.value, stepUp)
          : botApi.update(platformId, updatingPlatformConfig.value),
      platformId,
      props.requestStepUp,
    );
    if (!resp) {
      state.loading = false;
      return;
    }
    if (resp.data.status === 'error') {
      throw new Error(resp.data.message || tm('messages.platformUpdateFailed'));
    }

    await saveRoutesInternal();
    state.loading = false;
    showDialog.value = false;
    resetForm();
    emit('refresh-config');
    showSuccess(tm('messages.updateSuccess'));
  } catch (error) {
    state.loading = false;
    showError(resolveErrorMessage(error, tm('messages.platformUpdateFailed')));
  }
}

async function savePlatform() {
  const platformConfig = state.selectedPlatformConfig;
  const platformId = getString(platformConfig?.id);
  const platformType = getString(platformConfig?.type);
  if (!platformConfig || !platformId || !isPlatformIdValid(platformId)) {
    state.loading = false;
    showError(tm('dialog.invalidPlatformId'));
    return;
  }

  const existingPlatform = normalizePlatformConfigList(
    configData.value.platform,
  ).find((platform) => platform.id === platformId);
  if (existingPlatform || platformId === 'webchat') {
    const confirmed = await confirmIdConflict(platformId);
    if (!confirmed) {
      state.loading = false;
      return;
    }
  }

  if (platformType && ONEBOT_TOKEN_WARNING_PLATFORM_TYPES.has(platformType)) {
    const token = getOneBotSecurityToken(platformConfig)?.trim();
    if (!token) {
      const continueWithWarning =
        await showOneBotEmptyTokenWarning(platformType);
      if (!continueWithWarning) {
        state.loading = false;
        return;
      }
    }
  }

  try {
    const res = await runBotMutationWithStepUp(
      (stepUp) =>
        stepUp
          ? botApi.create(platformConfig, stepUp)
          : botApi.create(platformConfig),
      'collection',
      props.requestStepUp,
    );
    if (!res) {
      state.loading = false;
      return;
    }
    await handleConfigFile();
    state.loading = false;
    showDialog.value = false;
    resetForm();
    emit('refresh-config');
    showSuccess(res.data.message || tm('messages.addSuccessWithConfig'));
  } catch (error) {
    state.loading = false;
    showError(resolveErrorMessage(error, tm('messages.addSuccessWithConfig')));
  }
}

async function handleConfigFile() {
  const platformId = getString(state.selectedPlatformConfig?.id);
  if (!state.selectedAbConfId || !platformId) {
    return;
  }

  let configId: string | null = null;
  if (state.aBConfigRadioVal === '0') {
    configId = state.selectedAbConfId;
  } else if (state.aBConfigRadioVal === '1') {
    configId = await createNewConfigFile(state.selectedAbConfId);
  }

  if (!configId) {
    throw new Error(tm('messages.configIdMissing'));
  }

  await updateRoutingTable(`${platformId}:*:*`, configId);
}

async function updateRoutingTable(umop: string, configId: string) {
  try {
    await configRouteApi.upsert(umop, { config_id: configId });
  } catch (error) {
    console.error('更新路由表失败:', error);
    throw new Error(
      tm('messages.routingUpdateFailed', {
        message: resolveErrorMessage(
          error,
          tm('messages.platformUpdateFailed'),
        ),
      }),
    );
  }
}

async function createNewConfigFile(configName: string) {
  try {
    const configPayload =
      state.aBConfigRadioVal === '1' && state.newConfigData
        ? state.newConfigData
        : undefined;

    const createRes = await runConfigMutationWithStepUp(
      (stepUp) =>
        configProfileApi.create(
          {
            name: configName,
            config: configPayload,
          },
          stepUp ? { headers: stepUpHeaders(stepUp) } : undefined,
        ),
      'default',
      props.requestStepUp,
    );
    if (!createRes) {
      throw new Error(tm('messages.configIdMissing'));
    }

    const newConfigId = getString(createRes.data.data.conf_id);
    if (!newConfigId) {
      throw new Error(tm('messages.configIdMissing'));
    }
    return newConfigId;
  } catch (error) {
    console.error('创建新配置文件失败:', error);
    throw new Error(
      tm('messages.createConfigFailed', {
        message: resolveErrorMessage(
          error,
          tm('messages.platformUpdateFailed'),
        ),
      }),
    );
  }
}

function confirmIdConflict(id: string): Promise<boolean> {
  state.conflictId = id;
  state.showIdConflictDialog = true;
  return new Promise((resolve) => {
    state.idConflictResolve = resolve;
  });
}

function handleIdConflictConfirm(confirmed: boolean) {
  if (state.idConflictResolve) {
    state.idConflictResolve(confirmed);
    state.idConflictResolve = null;
  }
  state.showIdConflictDialog = false;
}

function showOneBotEmptyTokenWarning(platformType: string): Promise<boolean> {
  state.oneBotTokenWarningPlatformType = platformType;
  state.showOneBotEmptyTokenWarnDialog = true;
  return new Promise((resolve) => {
    state.oneBotEmptyTokenWarningResolve = resolve;
  });
}

function handleOneBotEmptyTokenWarningDismiss(continueWithWarning: boolean) {
  state.showOneBotEmptyTokenWarnDialog = false;
  if (state.oneBotEmptyTokenWarningResolve) {
    state.oneBotEmptyTokenWarningResolve(continueWithWarning);
    state.oneBotEmptyTokenWarningResolve = null;
  }
  state.oneBotTokenWarningPlatformType = null;

  if (!continueWithWarning) {
    state.loading = false;
  }
}

function showSuccess(message: string) {
  emit('show-toast', { message, type: 'success' });
}

function showError(message: string) {
  emit('show-toast', { message, type: 'error' });
}

function setScanPlatformId(value: string | null) {
  if (!state.selectedPlatformConfig) {
    return;
  }
  state.scanPlatformIdCustomized = true;
  state.selectedPlatformConfig.id = String(value || '');
}

function getOneBotSecurityToken(
  platformConfig: Record<string, unknown> | undefined,
): string | undefined {
  if (!platformConfig) {
    return undefined;
  }
  const platformType = getString(platformConfig.type);
  if (platformType === 'napcat') {
    return getString(platformConfig.token) ?? undefined;
  }
  return getString(platformConfig.ws_reverse_token) ?? undefined;
}

function buildRandomPlatformIdSuffix(): string {
  const letters = 'abcdefghijklmnopqrstuvwxyz';
  let suffix = '_';
  for (let i = 0; i < 4; i += 1) {
    suffix += letters[Math.floor(Math.random() * letters.length)];
  }
  return suffix;
}

function sanitizePlatformIdPart(value: unknown): string {
  return String(value ?? '')
    .trim()
    .replace(/\s+/g, '')
    .replace(/[!:]/g, '_');
}

function handlePlatformRegistrationCreated(data: RegistrationCreatedPayload) {
  if (!state.selectedPlatformConfig) {
    return;
  }
  if (state.scanPlatformIdCustomized) {
    return;
  }

  const currentId = String(state.selectedPlatformConfig.id || '').trim();
  const platformType = getString(state.selectedPlatformConfig.type);
  if (!currentId || !platformType) {
    return;
  }

  let suffix = '';
  const explicitSuffix = sanitizePlatformIdPart(data.platform_id_suffix);
  if (explicitSuffix) {
    suffix =
      explicitSuffix.startsWith('_') || explicitSuffix.startsWith('-')
        ? explicitSuffix
        : `_${explicitSuffix}`;
  } else if (data.bot_name) {
    const safeBotName = sanitizePlatformIdPart(data.bot_name);
    if (safeBotName) {
      suffix = `-${safeBotName}`;
    }
  } else if (platformType === 'weixin_oc' || platformType === 'dingtalk') {
    suffix = buildRandomPlatformIdSuffix();
  }

  if (!suffix) {
    return;
  }

  if (
    (platformType === 'weixin_oc' || platformType === 'dingtalk') &&
    /_[a-z]{4}$/.test(currentId)
  ) {
    return;
  }

  state.selectedPlatformConfig.id = currentId.endsWith(suffix)
    ? currentId
    : `${currentId}${suffix}`;
}

function isPlatformIdValid(id: unknown): boolean {
  const normalized = getString(id);
  if (!normalized) {
    return false;
  }
  return !/[!:\s]/.test(normalized);
}

async function getPlatformConfigs(platformId: string) {
  if (!platformId) {
    state.platformRoutes = [];
    return;
  }

  try {
    const routesRes = await configRouteApi.list();
    const routingTable = normalizeRoutingTable(routesRes.data.data.routing);
    const routes: PlatformRoute[] = [];

    for (const [umop, configId] of Object.entries(routingTable)) {
      const parsedUmop = parseUmop(umop);
      if (isParsedUmopMatchPlatform(parsedUmop, platformId)) {
        routes.push({
          umop,
          originalUmop: umop,
          sourceMode: 'manual',
          sourceUmo: parsedUmop?.sessionId === '*' ? '' : umop,
          messageType: parsedUmop?.messageType || '*',
          sessionId: parsedUmop?.sessionId || '*',
          configId,
        });
      }
    }

    state.platformRoutes = routes;
    if (state.platformRoutes.length === 0) {
      state.platformRoutes.push({
        umop: null,
        originalUmop: null,
        sourceMode: 'manual',
        sourceUmo: '',
        messageType: '*',
        sessionId: '*',
        configId: 'default',
      });
    }
  } catch (error) {
    console.error('获取平台路由配置失败:', error);
    state.platformRoutes = [];
  }
}

async function loadKnownRouteUmos() {
  if (state.loadingKnownRouteUmos) {
    return;
  }

  state.loadingKnownRouteUmos = true;
  try {
    const res = await sessionApi.activeUmos();
    if (res.data.status === 'ok') {
      const umos = normalizeStringArray(res.data.data?.umos);
      state.knownRouteUmos = Array.from(
        new Set([...state.knownRouteUmos, ...umos]),
      );
      mergeKnownRouteUmoInfos(
        normalizeKnownRouteUmoInfos(res.data.data?.umo_infos),
      );
    }
  } catch (error) {
    console.error('获取已有消息来源失败:', error);
  } finally {
    state.loadingKnownRouteUmos = false;
  }
}

function mergeKnownRouteUmoInfos(infos: KnownRouteUmoInfo[]) {
  const next = { ...state.knownRouteUmoInfoMap };
  for (const info of infos) {
    next[info.umo] = { ...(next[info.umo] || {}), ...info };
  }
  state.knownRouteUmoInfoMap = next;
}

function getKnownRouteUmoInfo(umo: string): KnownRouteUmoInfo {
  const parsed = parseUmop(umo);
  return (
    state.knownRouteUmoInfoMap[umo] || {
      umo,
      platform: parsed?.platform || '',
      message_type: parsed?.messageType || '',
      session_id: parsed?.sessionId || umo,
      auto_name: '',
      user_alias: '',
      display_name: umo,
    }
  );
}

function getKnownRouteUmoDisplayProps(umo: string) {
  const info = getKnownRouteUmoInfo(umo);
  const parsed = parseUmop(umo);
  return {
    umo,
    platform: info.platform || parsed?.platform || '',
    messageType: info.message_type || parsed?.messageType || '',
    sessionId: info.session_id || parsed?.sessionId || '',
    autoName: info.auto_name || '',
    userAlias: info.user_alias || '',
  };
}

function getKnownRouteUmoSelectionText(umo: string): string {
  if (!umo) {
    return '';
  }

  const info = getKnownRouteUmoInfo(umo);
  const parsed = parseUmop(umo);
  const aliasName = info.user_alias || '';
  const autoName = info.auto_name || '';
  if (aliasName && autoName && aliasName !== autoName) {
    return `${aliasName}（${autoName}）`;
  }
  return (
    aliasName ||
    autoName ||
    (parsed
      ? `${getMessageTypeLabel(parsed.messageType)}:${parsed.sessionId}`
      : umo)
  );
}

function getRouteSourceMode(route: PlatformRoute): RouteSourceMode {
  return route.sourceMode || 'manual';
}

function getRouteSourceModeLinkText(route: PlatformRoute): string {
  return getRouteSourceMode(route) === 'known'
    ? tm('createDialog.routeSource.switchToManual')
    : tm('createDialog.routeSource.switchToKnown');
}

function toggleRouteSourceMode(route: PlatformRoute) {
  const nextMode: RouteSourceMode =
    getRouteSourceMode(route) === 'known' ? 'manual' : 'known';
  route.sourceMode = nextMode;
  if (nextMode === 'known') {
    void loadKnownRouteUmos();
  }
}

function applyKnownRouteSource(route: PlatformRoute, umo: string | null) {
  if (!umo) {
    route.sourceUmo = '';
    return;
  }

  const parsed = parseUmop(umo);
  if (!parsed) {
    return;
  }
  route.sourceUmo = umo;
  route.messageType = parsed.messageType || '*';
  route.sessionId = parsed.sessionId || '*';
}

function addNewRoute() {
  state.platformRoutes.push({
    umop: null,
    originalUmop: null,
    sourceMode: 'manual',
    sourceUmo: '',
    messageType: '*',
    sessionId: '*',
    configId: 'default',
  });
}

function deleteRoute(index: number) {
  state.platformRoutes.splice(index, 1);
}

function moveRouteUp(index: number) {
  if (index > 0) {
    const current = state.platformRoutes[index];
    state.platformRoutes[index] = state.platformRoutes[index - 1];
    state.platformRoutes[index - 1] = current;
    state.platformRoutes = [...state.platformRoutes];
  }
}

function moveRouteDown(index: number) {
  if (index < state.platformRoutes.length - 1) {
    const current = state.platformRoutes[index];
    state.platformRoutes[index] = state.platformRoutes[index + 1];
    state.platformRoutes[index + 1] = current;
    state.platformRoutes = [...state.platformRoutes];
  }
}

async function saveRoutesInternal() {
  const originalPlatformId =
    state.originalUpdatingPlatformId ??
    getString(updatingPlatformConfig.value.id);
  const newPlatformId =
    getString(updatingPlatformConfig.value.id) ?? originalPlatformId;

  if (!originalPlatformId && !newPlatformId) {
    throw new Error(tm('messages.platformIdMissing'));
  }

  try {
    const routesRes = await configRouteApi.list();
    const fullRoutingTable = normalizeRoutingTable(routesRes.data.data.routing);

    for (const umop of Object.keys(fullRoutingTable)) {
      if (
        (originalPlatformId && isUmopMatchPlatform(umop, originalPlatformId)) ||
        (newPlatformId && isUmopMatchPlatform(umop, newPlatformId))
      ) {
        delete fullRoutingTable[umop];
      }
    }

    const platformIdForRoute = newPlatformId || originalPlatformId;
    for (const route of state.platformRoutes) {
      if (!route.configId || !platformIdForRoute) {
        continue;
      }
      const messageType = route.messageType === '*' ? '*' : route.messageType;
      const sessionId = route.sessionId === '*' ? '*' : route.sessionId;
      fullRoutingTable[`${platformIdForRoute}:${messageType}:${sessionId}`] =
        route.configId;
    }

    await configRouteApi.replace({
      routing: fullRoutingTable,
    });
  } catch (error) {
    console.error('保存路由表失败:', error);
    throw new Error(
      tm('messages.routingSaveFailed', {
        message: resolveErrorMessage(
          error,
          tm('messages.platformUpdateFailed'),
        ),
      }),
    );
  }
}

function toggleEditMode() {
  state.isEditingRoutes = !state.isEditingRoutes;
}

function toggleConfigSection() {
  state.showConfigSection = !state.showConfigSection;
}

function getConfigName(configId: string): string {
  const config = state.configInfoList.find((item) => item.id === configId);
  return config ? config.name : configId;
}

function isUmopMatchPlatform(umop: string, platformId: string): boolean {
  return isParsedUmopMatchPlatform(parseUmop(umop), platformId);
}

function isParsedUmopMatchPlatform(
  parsedUmop: ParsedUmop | null,
  platformId: string,
): boolean {
  if (!parsedUmop) {
    return false;
  }
  return (
    parsedUmop.platform === platformId ||
    parsedUmop.platform === '' ||
    parsedUmop.platform === '*'
  );
}

function parseUmop(umop: string | null | undefined): ParsedUmop | null {
  if (!umop) {
    return null;
  }

  const firstSeparatorIndex = umop.indexOf(':');
  if (firstSeparatorIndex === -1) {
    return null;
  }
  const secondSeparatorIndex = umop.indexOf(':', firstSeparatorIndex + 1);
  if (secondSeparatorIndex === -1) {
    return null;
  }

  return {
    platform: umop.slice(0, firstSeparatorIndex),
    messageType: umop.slice(firstSeparatorIndex + 1, secondSeparatorIndex),
    sessionId: umop.slice(secondSeparatorIndex + 1),
  };
}

function getMessageTypeLabel(messageType: string): string {
  const typeMap: Record<string, string> = {
    '*': tm('createDialog.messageTypeLabels.all'),
    '': tm('createDialog.messageTypeLabels.all'),
    GroupMessage: tm('createDialog.messageTypeLabels.group'),
    FriendMessage: tm('createDialog.messageTypeLabels.friend'),
  };
  return typeMap[messageType] || messageType;
}

function prepareData() {
  void getConfigInfoList();
  const platformId = getString(updatingPlatformConfig.value.id);
  if (updatingMode.value && platformId) {
    void getPlatformConfigs(platformId);
  }
}

function scrollDialogToBottom() {
  const container = dialogScrollContainer.value;
  const element =
    container && '$el' in container ? (container.$el ?? null) : container;
  if (!(element instanceof HTMLElement)) {
    return;
  }

  const scrollOptions = {
    top: element.scrollHeight,
    behavior: 'smooth' as const,
  };
  if (typeof element.scrollTo === 'function') {
    element.scrollTo(scrollOptions);
  } else {
    element.scrollTop = element.scrollHeight;
  }
}
</script>

<style scoped>
.platform-dialog__card {
  display: flex;
  flex-direction: column;
  max-height: min(88dvh, 960px);
}

.platform-dialog__content {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding-right: var(--astrbot-space-4);
}

.platform-dialog__actions {
  flex-shrink: 0;
}

.platform-dialog__step {
  display: flex;
  align-items: flex-start;
  width: 100%;
}

.platform-dialog__step-content {
  flex: 1;
}

.platform-type-field {
  min-width: 300px;
  max-width: 30%;
}

.platform-template-icon {
  width: 32px;
  height: 32px;
  margin-right: var(--astrbot-space-4);
  object-fit: contain;
}

.platform-config-select {
  min-width: 200px;
  max-width: 30%;
}

.config-drawer-overlay {
  align-items: stretch;
  justify-content: flex-end;
}

.config-drawer-card {
  width: clamp(320px, 60vw, 820px);
  height: calc(100dvh - 32px);
  display: flex;
  flex-direction: column;
  margin: 16px;
}

.config-drawer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--astrbot-space-4) var(--astrbot-space-6) var(--astrbot-space-3);
}

.config-drawer-content {
  flex: 1;
  overflow-y: auto;
  padding: var(--astrbot-space-4) var(--astrbot-space-4) var(--astrbot-space-6);
}

.platform-action-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.creation-mode-title {
  font-size: 14px;
  font-weight: 600;
  color: rgb(var(--v-theme-on-surface));
}

.route-source-cell {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--astrbot-space-1);
  min-width: 260px;
}

.route-source-input-row {
  min-width: 250px;
}

.route-source-input-row--editing {
  padding-top: var(--astrbot-space-4);
}

.route-source-mode-link {
  padding: 2px 0;
  border: 0;
  background: transparent;
  color: rgb(var(--v-theme-primary));
  cursor: pointer;
  font-size: 12px;
  line-height: 1;
  text-decoration: underline;
}

.route-source-mode-link:hover {
  text-decoration: underline;
}

.umo-selection-chip {
  max-width: 100%;
}

.route-source-autocomplete {
  min-width: 260px;
}

.route-message-type-field {
  max-width: 140px;
}

.route-config-select {
  min-width: 200px;
}

.route-config-missing {
  color: rgb(var(--v-theme-error));
}

.registration-inline {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  justify-content: flex-start;
  width: 320px;
  gap: 8px;
}

.registration-platform-id-field {
  width: 300px;
}

@media (max-width: 600px) {
  .platform-dialog__card {
    max-height: calc(100dvh - 24px);
  }

  .platform-dialog__content {
    padding-right: 16px;
  }
}
</style>
