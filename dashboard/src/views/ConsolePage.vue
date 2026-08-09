<script setup lang="ts">
import ConsoleDisplayer from '@/components/shared/ConsoleDisplayer.vue';
import { useModuleI18n } from '@/i18n/composables';
import { updatesApi } from '@/api/v1';
import { resolveErrorMessage } from '@/utils/errorUtils';
import { useToast } from '@/utils/toast';
import { ref, watch } from 'vue';

const { tm } = useModuleI18n('features/console');
const toast = useToast();
const autoScrollEnabled = ref(
  localStorage.getItem('console_auto_scroll') !== 'false',
);
const hideUserChatEnabled = ref(
  localStorage.getItem('console_hide_user_chat') !== 'false',
);
const pipDialog = ref(false);
const loading = ref(false);
const pipInstallPayload = ref({
  package: '',
  mirror: '',
});

watch(autoScrollEnabled, (value) => {
  localStorage.setItem('console_auto_scroll', String(value));
});

watch(hideUserChatEnabled, (value) => {
  localStorage.setItem('console_hide_user_chat', String(value));
});

async function pipInstall(): Promise<void> {
  loading.value = true;
  try {
    const res = await updatesApi.installPip(pipInstallPayload.value);
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
  <div class="console-page">
    <div class="console-header">
      <div>
        <h1 class="text-h2 mb-1">{{ tm('title') }}</h1>
        <p class="text-body-2 text-medium-emphasis mb-0">
          {{ tm('debugHint.text') }}
        </p>
      </div>
      <div class="d-flex align-center">
        <v-switch
          v-model="hideUserChatEnabled"
          :label="
            hideUserChatEnabled
              ? tm('hideUserChat.enabled')
              : tm('hideUserChat.disabled')
          "
          hide-details
          density="compact"
          inset
          color="primary"
          style="margin-right: 16px"
        ></v-switch>
        <v-switch
          v-model="autoScrollEnabled"
          :label="
            autoScrollEnabled
              ? tm('autoScroll.enabled')
              : tm('autoScroll.disabled')
          "
          hide-details
          density="compact"
          inset
          color="primary"
          style="margin-right: 16px"
        ></v-switch>
        <v-dialog v-model="pipDialog" width="400" scrollable>
          <template #activator="{ props: activatorProps }">
            <v-btn variant="plain" v-bind="activatorProps">{{
              tm('pipInstall.button')
            }}</v-btn>
          </template>
          <v-card class="console-pip-dialog">
            <v-card-title>
              <span class="text-h5">{{ tm('pipInstall.dialogTitle') }}</span>
            </v-card-title>
            <v-divider />
            <v-card-text class="console-pip-dialog__content">
              <v-text-field
                v-model="pipInstallPayload.package"
                :label="tm('pipInstall.packageLabel')"
                variant="outlined"
              ></v-text-field>
              <v-text-field
                v-model="pipInstallPayload.mirror"
                :label="tm('pipInstall.mirrorLabel')"
                variant="outlined"
              ></v-text-field>
              <small>{{ tm('pipInstall.mirrorHint') }}</small>
            </v-card-text>
            <v-divider />
            <v-card-actions class="console-pip-dialog__actions">
              <v-spacer></v-spacer>
              <v-btn
                color="blue-darken-1"
                variant="text"
                :loading="loading"
                @click="pipInstall"
              >
                {{ tm('pipInstall.installButton') }}
              </v-btn>
            </v-card-actions>
          </v-card>
        </v-dialog>
      </div>
    </div>
    <ConsoleDisplayer
      class="console-display"
      :auto-scroll="autoScrollEnabled"
      :hide-user-chat="hideUserChatEnabled"
    />
  </div>
</template>

<style scoped>
.console-page {
  display: flex;
  flex-direction: column;
  height: calc(100dvh - 67px);
  margin: 0 auto;
  max-width: 1400px;
  min-height: 0;
  padding: 24px;
  width: 100%;
}

.console-header {
  align-items: flex-start;
  display: flex;
  flex-shrink: 0;
  justify-content: space-between;
  margin-bottom: 24px;
}

.console-display {
  flex: 1;
  min-height: 0;
  width: 100%;
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

@keyframes fadeIn {
  from {
    opacity: 0;
  }

  to {
    opacity: 1;
  }
}

.fade-in {
  animation: fadeIn 0.2s ease-in-out;
}

@media (max-width: 768px) {
  .console-page {
    padding: 16px;
  }

  .console-header {
    flex-direction: column;
    gap: 12px;
  }
}
</style>
