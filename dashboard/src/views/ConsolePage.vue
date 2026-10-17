<script setup lang="ts">
import { reactive, ref, watch } from "vue";
import { Minus, PackagePlus, Plus } from "@lucide/vue";
import ConsoleDisplayer from "@/components/shared/ConsoleDisplayer.vue";
import { useModuleI18n } from "@/i18n/composables";
import { useCustomizerStore } from "@/stores/customizer";
import { updatesApi } from "@/api/v1";
import { useToast } from "@/utils/toast";

const { tm } = useModuleI18n("features/console");
const toast = useToast();
const customizerStore = useCustomizerStore();

const logFontSize = ref(
  Math.min(
    16,
    Math.max(8, Number(localStorage.getItem("console_log_font_size")) || 12),
  ),
);
const hideUserChatEnabled = ref(
  localStorage.getItem("console_hide_user_chat") === "true",
);
const pipDialog = ref(false);
const pipInstallPayload = reactive({ package: "", mirror: "" });
const loading = ref(false);

watch(logFontSize, (value) => {
  localStorage.setItem("console_log_font_size", String(value));
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
      show-search
      :font-size="logFontSize"
      v-model:hide-user-chat="hideUserChatEnabled"
    >
      <template #header-actions>
        <div class="console-header-actions">
          <div
            class="console-font-controls"
            role="group"
            :aria-label="tm('fontSize.label')"
          >
            <v-btn
              icon
              size="x-small"
              variant="text"
              :disabled="logFontSize <= 8"
              :aria-label="tm('fontSize.decrease')"
              :title="tm('fontSize.decrease')"
              @click="logFontSize -= 2"
            >
              <Minus :size="15" aria-hidden="true" />
            </v-btn>
            <output :aria-label="tm('fontSize.label')"
              >{{ logFontSize }}px</output
            >
            <v-btn
              icon
              size="x-small"
              variant="text"
              :disabled="logFontSize >= 16"
              :aria-label="tm('fontSize.increase')"
              :title="tm('fontSize.increase')"
              @click="logFontSize += 2"
            >
              <Plus :size="15" aria-hidden="true" />
            </v-btn>
          </div>
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
  flex: 0 0 auto;
  flex-wrap: nowrap;
  gap: 6px 14px;
}

.console-font-controls {
  align-items: center;
  display: flex;
  gap: 2px;
  white-space: nowrap;
}

.console-font-controls output {
  color: rgba(var(--v-theme-on-surface), 0.62);
  font-size: 0.72rem;
  min-width: 32px;
  text-align: center;
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
}
</style>
