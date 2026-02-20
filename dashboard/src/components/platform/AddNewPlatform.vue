<template>
  <v-dialog v-model="showDialog" max-width="800px" max-height="90%" @after-enter="prepareData">
    <v-card
      :title="updatingMode ? `${tm('dialog.edit')} ${updatingPlatformConfig.id} ${tm('dialog.adapter')}` : tm('dialog.addPlatform')">
  <v-card-text ref="dialogScrollContainer" class="pa-4 ml-2" style="overflow-y: auto;">
        <div class="d-flex align-start" style="width: 100%;">
          <div>
            <v-icon icon="mdi-numeric-1-circle" class="mr-3"></v-icon>
          </div>
          <div style="flex: 1;">
            <h3>
              {{ tm('createDialog.step1Title') }}
            </h3>
            <small style="color: grey;">{{ tm('createDialog.step1Hint') }}</small>
            <div>

              <div v-if="!updatingMode">
                <v-select v-model="selectedPlatformType" :items="Object.keys(platformTemplates)" item-title="name"
                  item-value="name" :label="tm('createDialog.platformTypeLabel')" variant="outlined" rounded="md" dense hide-details class="mt-6"
                  style="max-width: 30%; min-width: 300px;">

                  <template v-slot:item="{ props: itemProps, item }">
                    <v-list-item v-bind="itemProps">
                      <template v-slot:prepend>
                        <img :src="getPlatformIcon(platformTemplates[item.raw].type)"
                          style="width: 32px; height: 32px; object-fit: contain; margin-right: 16px;" />
                      </template>
                    </v-list-item>
                  </template>

                </v-select>
                <div class="mt-3" v-if="selectedPlatformConfig">
                  <v-btn color="info" variant="tonal" @click="openTutorial" class="mt-2">
                    <v-icon start>mdi-book-open-variant</v-icon>
                    {{ tm('dialog.viewTutorial') }}
                  </v-btn>
                  <div class="mt-2">
                    <AstrBotConfig :iterable="selectedPlatformConfig" :metadata="metadata['platform_group']?.metadata"
                      metadataKey="platform" />
                  </div>
                </div>
              </div>
              <div v-else>
                <v-text-field :label="tm('createDialog.platformTypeLabel')" variant="outlined" rounded="md" dense hide-details class="mt-6"
                  style="max-width: 30%; min-width: 300px;" v-model="updatingPlatformConfig.type"
                  disabled></v-text-field>
                <div class="mt-3">
                  <div class="mt-2">
                    <AstrBotConfig :iterable="updatingPlatformConfig" :metadata="metadata['platform_group']?.metadata"
                      metadataKey="platform" />
                  </div>
                </div>
              </div>

            </div>
          </div>
        </div>

      </v-card-text>

      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn text @click="closeDialog">{{ tm('dialog.cancel') }}</v-btn>
        <v-btn :disabled="!canSave" color="primary" v-if="!updatingMode" @click="newPlatform" :loading="loading">{{
          tm('dialog.save') }}</v-btn>
        <v-btn :disabled="!canSave" color="primary" v-else @click="newPlatform" :loading="loading">{{
          tm('dialog.save') }}</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- ID冲突确认对话框 -->
  <v-dialog v-model="showIdConflictDialog" max-width="450" persistent>
    <v-card>
      <v-card-title class="text-h6 bg-warning d-flex align-center">
        <v-icon start class="me-2">mdi-alert-circle-outline</v-icon>
        {{ tm('dialog.idConflict.title') }}
      </v-card-title>
      <v-card-text class="py-4 text-body-1 text-medium-emphasis">
        {{ tm('dialog.idConflict.message', { id: conflictId }) }}
      </v-card-text>
      <v-card-actions>
        <v-spacer></v-spacer>
        <v-btn color="grey" variant="text" @click="handleIdConflictConfirm(false)">{{ tm('dialog.idConflict.confirm')
        }}</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <!-- 安全警告对话框 -->
  <v-dialog v-model="showOneBotEmptyTokenWarnDialog" max-width="600" persistent>
    <v-card>
      <v-card-title>
        {{ tm('dialog.securityWarning.title') }}
      </v-card-title>
      <v-card-text class="py-4">
        <p>{{ tm('dialog.securityWarning.aiocqhttpTokenMissing') }}</p>
        <span><a
            href="https://docs.astrbot.app/deploy/platform/aiocqhttp/napcat.html#%E9%99%84%E5%BD%95-%E5%A2%9E%E5%BC%BA%E8%BF%9E%E6%8E%A5%E5%AE%89%E5%85%A8%E6%80%A7"
            target="_blank">{{ tm('dialog.securityWarning.learnMore') }}</a></span>
      </v-card-text>
      <v-card-actions class="px-4 pb-4">
        <v-spacer></v-spacer>
        <v-btn color="error" @click="handleOneBotEmptyTokenWarningDismiss(true)">
          {{ tm('createDialog.warningContinue') }}
        </v-btn>
        <v-btn color="primary" @click="handleOneBotEmptyTokenWarningDismiss(false)">
          {{ tm('createDialog.warningEditAgain') }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

</template>


<script>
import axios from 'axios';
import { useModuleI18n } from '@/i18n/composables';
import { getPlatformIcon, getTutorialLink, getPlatformDescription } from '@/utils/platformUtils';
import AstrBotConfig from '@/components/shared/AstrBotConfig.vue';

export default {
  name: 'AddNewPlatform',
  components: { AstrBotConfig },
  emits: ['update:show', 'show-toast', 'refresh-config'],
  props: {
    show: {
      type: Boolean,
      default: false
    },
    metadata: {
      type: Object,
      default: () => ({})
    },
    config_data: {
      type: Object,
      default: () => ({})
    },
    updatingMode: {
      type: Boolean,
      default: false
    },
    updatingPlatformConfig: {
      type: Object,
      default: null
    }
  },
  data() {
    return {
      selectedPlatformType: null,
      selectedPlatformConfig: null,
      showIdConflictDialog: false,
      conflictId: '',
      idConflictResolve: null,
      showOneBotEmptyTokenWarnDialog: false,
      oneBotEmptyTokenWarningResolve: null,
      loading: false,
      originalUpdatingPlatformId: null
    };
  },
  setup() {
    const { tm } = useModuleI18n('features/platform');
    return { tm };
  },
  computed: {
    showDialog: {
      get() {
        return this.show;
      },
      set(value) {
        this.$emit('update:show', value);
      }
    },
    platformTemplates() {
      return this.metadata['platform_group']?.metadata?.platform?.config_template || {};
    },
    canSave() {
      if (this.updatingMode) {
        return this.isPlatformIdValid(this.updatingPlatformConfig?.id);
      }
      if (!this.selectedPlatformType) {
        return false;
      }
      return this.isPlatformIdValid(this.selectedPlatformConfig?.id);
    }
  },
  watch: {
    selectedPlatformType(newType) {
      if (newType && this.platformTemplates[newType]) {
        this.selectedPlatformConfig = JSON.parse(JSON.stringify(this.platformTemplates[newType]));
      } else {
        this.selectedPlatformConfig = null;
      }
    },
    showIdConflictDialog(newValue) {
      if (!newValue && this.idConflictResolve) {
        this.idConflictResolve(false);
        this.idConflictResolve = null;
      }
    },
    showOneBotEmptyTokenWarnDialog(newValue) {
      if (!newValue && this.oneBotEmptyTokenWarningResolve) {
        this.oneBotEmptyTokenWarningResolve(true);
        this.oneBotEmptyTokenWarningResolve = null;
      }
    },
    updatingPlatformConfig: {
      handler(newConfig) {
        if (this.updatingMode && newConfig && newConfig.id) {
          this.originalUpdatingPlatformId = newConfig.id;
        }
      },
      immediate: true
    }
  },
  methods: {
    getPlatformIcon(platformType) {
      // Check for plugin-provided logo_token first
      const template = this.platformTemplates?.[platformType];
      if (template && template.logo_token) {
        return `/api/file/${template.logo_token}`;
      }
      return getPlatformIcon(platformType);
    },
    getPlatformDescription,
    resetForm() {
      this.selectedPlatformType = null;
      this.selectedPlatformConfig = null;
      this.originalUpdatingPlatformId = null;
    },
    closeDialog() {
      this.resetForm();
      this.showDialog = false;
    },
    openTutorial() {
      const tutorialUrl = getTutorialLink(this.selectedPlatformConfig.type);
      window.open(tutorialUrl, '_blank');
    },
    prepareData() {
      if (this.updatingMode && this.updatingPlatformConfig?.id) {
        this.originalUpdatingPlatformId = this.updatingPlatformConfig.id;
      }
    },
    newPlatform() {
      this.loading = true;
      if (this.updatingMode) {
        if (this.updatingPlatformConfig.type === 'aiocqhttp') {
          const token = this.updatingPlatformConfig.ws_reverse_token;
          if (!token || token.trim() === '') {
            this.showOneBotEmptyTokenWarning().then((continueWithWarning) => {
              if (continueWithWarning) {
                this.updatePlatform();
              } else {
                this.loading = false;
              }
            });
            return;
          }
        }
        this.updatePlatform();
      } else {
        this.savePlatform();
      }
    },
    async updatePlatform() {
      const id = this.originalUpdatingPlatformId || this.updatingPlatformConfig.id;
      if (!id) {
        this.loading = false;
        this.showError(this.tm('messages.updateMissingPlatformId'));
        return;
      }
      if (!this.isPlatformIdValid(id)) {
        this.loading = false;
        this.showError(this.tm('dialog.invalidPlatformId'));
        return;
      }
      try {
        const resp = await axios.post('/api/config/platform/update', {
          id: id,
          config: this.updatingPlatformConfig
        });
        if (resp.data.status === 'error') {
          throw new Error(resp.data.message || this.tm('messages.platformUpdateFailed'));
        }
        this.loading = false;
        this.showDialog = false;
        this.resetForm();
        this.$emit('refresh-config');
        this.showSuccess(this.tm('messages.updateSuccess'));
      } catch (err) {
        this.loading = false;
        this.showError(err.response?.data?.message || err.message);
      }
    },
    async savePlatform() {
      if (!this.isPlatformIdValid(this.selectedPlatformConfig?.id)) {
        this.loading = false;
        this.showError(this.tm('dialog.invalidPlatformId'));
        return;
      }
      const existingPlatform = this.config_data.platform?.find(p => p.id === this.selectedPlatformConfig.id);
      if (existingPlatform || this.selectedPlatformConfig.id === 'webchat') {
        const confirmed = await this.confirmIdConflict(this.selectedPlatformConfig.id);
        if (!confirmed) {
          this.loading = false;
          return;
        }
      }
      if (this.selectedPlatformConfig.type === 'aiocqhttp') {
        const token = this.selectedPlatformConfig.ws_reverse_token;
        if (!token || token.trim() === '') {
          const continueWithWarning = await this.showOneBotEmptyTokenWarning();
          if (!continueWithWarning) {
            return;
          }
        }
      }
      try {
        const res = await axios.post('/api/config/platform/new', this.selectedPlatformConfig);
        this.loading = false;
        this.showDialog = false;
        this.resetForm();
        this.$emit('refresh-config');
        this.showSuccess(res.data.message || this.tm('messages.addSuccessWithConfig'));
      } catch (err) {
        this.loading = false;
        this.showError(err.response?.data?.message || err.message);
      }
    },
    confirmIdConflict(id) {
      this.conflictId = id;
      this.showIdConflictDialog = true;
      return new Promise((resolve) => {
        this.idConflictResolve = resolve;
      });
    },
    handleIdConflictConfirm(confirmed) {
      if (this.idConflictResolve) {
        this.idConflictResolve(confirmed);
      }
      this.showIdConflictDialog = false;
    },
    showOneBotEmptyTokenWarning() {
      this.showOneBotEmptyTokenWarnDialog = true;
      return new Promise((resolve) => {
        this.oneBotEmptyTokenWarningResolve = resolve;
      });
    },
    handleOneBotEmptyTokenWarningDismiss(continueWithWarning) {
      this.showOneBotEmptyTokenWarnDialog = false;
      if (this.oneBotEmptyTokenWarningResolve) {
        this.oneBotEmptyTokenWarningResolve(continueWithWarning);
        this.oneBotEmptyTokenWarningResolve = null;
      }
      if (!continueWithWarning) {
        this.loading = false;
      }
    },
    showSuccess(message) {
      this.$emit('show-toast', { message: message, type: 'success' });
    },
    showError(message) {
      this.$emit('show-toast', { message: message, type: 'error' });
    },
    isPlatformIdValid(id) {
      if (!id) {
        return false;
      }
      return !/[!:]/.test(id);
    }
  }
};
</script>

<style>
.v-select__selection-text {
  font-size: 12px;
}
</style>
