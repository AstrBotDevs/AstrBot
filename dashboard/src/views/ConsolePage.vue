<script setup lang="ts">
import { reactive, ref, watch } from "vue";
import { PackagePlus } from "@lucide/vue";
import ConsoleDisplayer from "@/components/shared/ConsoleDisplayer.vue";
import { useModuleI18n } from "@/i18n/composables";
import { useCustomizerStore } from "@/stores/customizer";
import { updatesApi } from "@/api/v1";
import { useToast } from "@/utils/toast";

const { tm } = useModuleI18n("features/console");
const toast = useToast();
const customizerStore = useCustomizerStore();

const autoScrollEnabled = ref(
  localStorage.getItem("console_auto_scroll") !== "false",
);
const hideUserChatEnabled = ref(
  localStorage.getItem("console_hide_user_chat") === "true",
);
const pipDialog = ref(false);
const pipInstallPayload = reactive({ package: "", mirror: "" });
const loading = ref(false);

watch(autoScrollEnabled, (value) => {
  localStorage.setItem("console_auto_scroll", String(value));
});

watch(hideUserChatEnabled, (value) => {
  localStorage.setItem("console_hide_user_chat", String(value));
});

async function pipInstall() {
  loading.value = true;
  try {
    const response = await updatesApi.installPip(pipInstallPayload);
    if (response.data.status !== "ok") {
      throw new Error(response.data.message || tm("pipInstall.installFailed"));
    }
    toast.success(response.data.message || tm("pipInstall.installSuccess"));
    pipDialog.value = false;
  } catch (error: any) {
    toast.error(
      error?.response?.data?.message ||
        error?.message ||
        tm("pipInstall.requestFailed"),
    );
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
          <v-dialog v-model="pipDialog" width="440">
            <template #activator="{ props }">
              <v-btn
                v-bind="props"
                class="pip-install-button"
                size="small"
                variant="tonal"
              >
                <PackagePlus :size="15" aria-hidden="true" />
                <span>{{ tm("pipInstall.button") }}</span>
              </v-btn>
            </template>
            <v-card>
              <v-card-title class="text-h3 pa-4 pb-0 pl-6">
                {{ tm("pipInstall.dialogTitle") }}
              </v-card-title>
              <v-card-text class="pa-6 pb-2">
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
                  {{ tm("pipInstall.mirrorHint") }}
                </div>
              </v-card-text>
              <v-card-actions class="pa-4 pt-0">
                <v-spacer />
                <v-btn variant="text" @click="pipDialog = false">
                  {{ tm("pipInstall.cancelButton") }}
                </v-btn>
                <v-btn
                  color="primary"
                  variant="tonal"
                  :loading="loading"
                  @click="pipInstall"
                >
                  {{ tm("pipInstall.installButton") }}
                </v-btn>
              </v-card-actions>
            </v-card>
          </v-dialog>
        </div>
      </template>
    </ConsoleDisplayer>
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

@media (max-width: 800px) {
  .console-page {
    height: calc(100dvh - 112px);
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
