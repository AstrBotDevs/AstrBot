<script setup lang="ts">
import { reactive, ref, watch } from 'vue';
import { updatesApi } from '@/api/v1';
import ConsoleDisplayer from '@/components/shared/ConsoleDisplayer.vue';
import DashboardStepUpDialog from '@/components/shared/DashboardStepUpDialog.vue';
import { useDashboardStepUp } from '@/composables/useDashboardStepUp';
import { useModuleI18n } from '@/i18n/composables';
import { useCustomizerStore } from '@/stores/customizer';
import { resolveErrorMessage } from '@/utils/errorUtils';
import { stepUpHeaders } from '@/utils/stepUp';
import { useToast } from '@/utils/toast';

const { tm } = useModuleI18n('features/logs');
const toast = useToast();
const customizerStore = useCustomizerStore();
const autoScrollEnabled = ref(
  localStorage.getItem('console_auto_scroll') !== 'false',
);
const hideUserChatEnabled = ref(
  localStorage.getItem('console_hide_user_chat') !== 'false',
);
const pipDialog = ref(false);
const loading = ref(false);
const pipInstallPayload = reactive({ package: '', mirror: '' });
const {
  dialogOpen: stepUpDialogOpen,
  loading: stepUpLoading,
  errorMessage: stepUpErrorMessage,
  requestStepUp,
  submitStepUp,
  cancelStepUp,
} = useDashboardStepUp();

watch(autoScrollEnabled, (value) => {
  localStorage.setItem('console_auto_scroll', String(value));
});

watch(hideUserChatEnabled, (value) => {
  localStorage.setItem('console_hide_user_chat', String(value));
});

async function pipInstall(): Promise<void> {
  try {
    const stepUp = await requestStepUp({
      action: 'system.pip_install',
      resourceType: 'system',
      resourceId: 'pip-install',
    });
    if (!stepUp) return;
    loading.value = true;
    const res = await updatesApi.installPip(pipInstallPayload, {
      headers: stepUpHeaders(stepUp),
    });
    if (res.data.status === 'ok') {
      toast.success(res.data.message || tm('pipInstall.installSuccess'));
      pipDialog.value = false;
      return;
    }
    toast.error(res.data.message || tm('pipInstall.installFailed'));
  } catch (error) {
    toast.error(resolveErrorMessage(error, tm('pipInstall.requestFailed')));
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="console-page" :class="{ 'is-dark': customizerStore.isDark }">
    <ConsoleDisplayer
      class="console-display"
      workspace-mode
      :auto-scroll="autoScrollEnabled"
      :hide-user-chat="hideUserChatEnabled"
    >
      <template #header-actions>
        <div class="console-header-actions">
          <v-switch
            v-model="hideUserChatEnabled"
            :label="tm('hideUserChat.label')"
            :aria-label="tm('hideUserChat.label')"
            hide-details
            density="compact"
            inset
            color="primary"
          />
          <v-switch
            v-model="autoScrollEnabled"
            :label="tm('autoScroll.label')"
            :aria-label="tm('autoScroll.label')"
            hide-details
            density="compact"
            inset
            color="primary"
          />
          <v-btn
            class="pip-install-button"
            size="small"
            variant="tonal"
            @click="pipDialog = true"
          >
            <v-icon size="15" aria-hidden="true"
              >mdi-package-variant-plus</v-icon
            >
            <span>{{ tm('pipInstall.button') }}</span>
          </v-btn>
        </div>
      </template>
    </ConsoleDisplayer>
    <v-dialog v-model="pipDialog" width="440" scrollable>
      <v-card class="app-dialog console-pip-dialog">
        <v-card-title>
          <span class="text-h5">{{ tm('pipInstall.dialogTitle') }}</span>
        </v-card-title>
        <v-divider />
        <v-card-text class="console-pip-dialog__content">
          <v-text-field
            v-model="pipInstallPayload.package"
            :label="tm('pipInstall.packageLabel')"
            density="compact"
            variant="solo-filled"
            flat
          />
          <v-text-field
            v-model="pipInstallPayload.mirror"
            :label="tm('pipInstall.mirrorLabel')"
            density="compact"
            variant="solo-filled"
            flat
            hide-details
          />
          <div class="pip-mirror-hint">
            {{ tm('pipInstall.mirrorHint') }}
          </div>
        </v-card-text>
        <v-divider />
        <v-card-actions class="console-pip-dialog__actions">
          <v-spacer />
          <v-btn variant="text" @click="pipDialog = false">
            {{ tm('pipInstall.cancelButton') }}
          </v-btn>
          <v-btn
            color="primary"
            variant="tonal"
            :loading="loading"
            @click="pipInstall"
          >
            {{ tm('pipInstall.installButton') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
    <DashboardStepUpDialog
      v-model="stepUpDialogOpen"
      :loading="stepUpLoading"
      :error-message="stepUpErrorMessage"
      @confirm="submitStepUp"
      @cancel="cancelStepUp"
    />
  </div>
</template>

<style scoped>
.console-page {
  --console-workspace-card: #f5f6f7;
  height: calc(100dvh - 112px);
  margin: 0 auto;
  max-width: 1560px;
  min-height: 0;
  padding: 0 12px 8px;
  width: 100%;
}

.console-page.is-dark {
  --console-workspace-card: rgba(var(--v-theme-on-surface), 0.06);
}

.console-display {
  height: 100%;
  min-height: 0;
  width: 100%;
}

.console-header-actions {
  align-items: center;
  display: flex;
  flex-wrap: wrap;
  gap: 6px 14px;
}

.console-header-actions :deep(.v-switch .v-selection-control) {
  min-height: 34px;
}

.console-header-actions :deep(.v-label) {
  font-size: 0.75rem;
  opacity: 0.72;
}

.pip-install-button :deep(.v-btn__content) {
  gap: 6px;
}

.pip-mirror-hint {
  color: rgba(var(--v-theme-on-surface), 0.52);
  font-size: 0.72rem;
  line-height: 1.5;
  margin-top: 8px;
}

.console-pip-dialog {
  display: flex;
  flex-direction: column;
  max-height: min(80vh, 420px);
}

.console-pip-dialog__content {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
}

.console-pip-dialog__actions {
  flex: 0 0 auto;
}

@media (max-width: 800px) {
  .console-page {
    padding: 0 4px 6px;
  }

  .console-header-actions {
    width: 100%;
  }
}

@media (max-width: 520px) {
  .console-header-actions {
    display: grid;
    gap: 4px 10px;
    grid-template-columns: 1fr 1fr;
  }

  .pip-install-button {
    grid-column: 1 / -1;
  }
}
</style>
