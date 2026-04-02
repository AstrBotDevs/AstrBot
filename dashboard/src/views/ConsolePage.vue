<script setup lang="ts">
import ConsoleDisplayer from "@/components/shared/ConsoleDisplayer.vue";
import { useModuleI18n } from "@/i18n/composables";
import axios from "@/utils/request";
import { ref } from "vue";

const { tm } = useModuleI18n("features/console");

const autoScrollEnabled = ref(true);
const isFullscreen = ref(false);
const pipDialog = ref(false);
const pipInstallPayload = ref({ package: "", mirror: "" });
const loading = ref(false);
const status = ref("");
const consoleDisplayer = ref();

function toggleFullscreen() {
  isFullscreen.value = !isFullscreen.value;
}

async function pipInstall() {
  loading.value = true;
  status.value = "";
  try {
    const res = await axios.post(
      "/api/console/pip_install",
      pipInstallPayload.value,
    );
    if (res.data?.status === "ok") {
      status.value = tm("pipInstall.success");
    } else {
      status.value = res.data?.message || tm("pipInstall.failed");
    }
  } catch (err: any) {
    status.value = err?.response?.data?.message || tm("pipInstall.failed");
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="console-page" :class="{ 'is-fullscreen': isFullscreen }">
    <div class="console-topbar">
      <div class="topbar-left">
        <div class="topbar-title">{{ tm("title") }}</div>
        <v-alert
          type="info"
          variant="tonal"
          density="compact"
          class="mt-2"
          style="max-width: 600px"
        >
          {{ tm("debugHint.text") }}
        </v-alert>
      </div>
      <div class="topbar-right">
        <v-btn
          :icon="isFullscreen ? 'mdi-fullscreen-exit' : 'mdi-fullscreen'"
          variant="tonal"
          size="small"
          @click="toggleFullscreen"
        />
        <v-switch
          v-model="autoScrollEnabled"
          :label="
            autoScrollEnabled
              ? tm('autoScroll.enabled')
              : tm('autoScroll.disabled')
          "
          hide-details
          density="compact"
          color="primary"
          style="margin-right: 8px"
        />
        <v-dialog v-model="pipDialog" width="400">
          <template #activator="{ props }">
            <v-btn variant="plain" v-bind="props">
              {{ tm("pipInstall.button") }}
            </v-btn>
          </template>
          <v-card class="console-dialog-card">
            <v-card-title>
              <span class="text-h5">{{ tm("pipInstall.dialogTitle") }}</span>
            </v-card-title>
            <v-card-text>
              <v-text-field
                v-model="pipInstallPayload.package"
                :label="tm('pipInstall.packageLabel')"
                variant="outlined"
              />
              <v-text-field
                v-model="pipInstallPayload.mirror"
                :label="tm('pipInstall.mirrorLabel')"
                variant="outlined"
              />
              <small>{{ tm("pipInstall.mirrorHint") }}</small>
              <div>
                <small>{{ status }}</small>
              </div>
            </v-card-text>
            <v-card-actions>
              <v-spacer />
              <v-btn
                color="blue-darken-1"
                variant="text"
                :loading="loading"
                @click="pipInstall"
              >
                {{ tm("pipInstall.installButton") }}
              </v-btn>
            </v-card-actions>
          </v-card>
        </v-dialog>
      </div>
    </div>
    <div
      class="console-content"
      :style="
        isFullscreen
          ? 'height: calc(100vh - 120px)'
          : 'height: calc(100vh - 220px)'
      "
    >
      <ConsoleDisplayer ref="consoleDisplayer" style="height: 100%" />
    </div>
  </div>
</template>

<script lang="ts">
export default {
  name: "ConsolePage",
  components: { ConsoleDisplayer },
};
</script>

<style scoped>
.console-page {
  --console-page-bg: transparent;
  --console-panel-bg: rgba(var(--v-theme-surface), 0.78);
  --console-card-bg: rgba(var(--v-theme-surface), 0.9);
  --console-primary: rgb(var(--v-theme-primary));
  --console-primary-soft: rgba(var(--v-theme-primary), 0.08);
  --console-border: rgba(var(--v-theme-borderLight), 0.22);
  --console-border-strong: rgba(var(--v-theme-borderLight), 0.4);
  --console-text: rgba(var(--v-theme-on-surface), 0.92);
  --console-muted: rgba(var(--v-theme-on-surface), 0.7);
  --console-shadow: 0 10px 24px rgba(15, 23, 42, 0.08);
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  position: relative;
  z-index: 1;
  isolation: isolate;
  gap: 16px;
  padding: 16px;
}

.console-page.is-fullscreen {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 9999;
  padding: 16px;
  background: var(--console-panel-bg);
}

:global(.v-theme--bluebusinessdarktheme) .console-page {
  --console-panel-bg: rgba(var(--v-theme-surface), 0.72);
  --console-card-bg: rgba(var(--v-theme-surface-variant), 0.74);
  --console-border: rgba(var(--v-theme-borderLight), 0.46);
  --console-shadow: none;
}

.console-topbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  padding: 16px 20px;
  background: var(--console-panel-bg);
  border: 1px solid var(--console-border);
  border-radius: 12px;
  backdrop-filter: blur(16px);
  box-shadow: var(--console-shadow);
  flex-shrink: 0;
}

.topbar-left {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.topbar-title {
  font-size: 18px;
  font-weight: 700;
  color: var(--console-primary) !important;
  -webkit-text-fill-color: var(--console-primary);
}

.topbar-right {
  display: flex;
  align-items: center;
  gap: 10px;
}

.console-content {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  position: relative;
  z-index: 1;
  background: var(--console-panel-bg);
  border: 1px solid var(--console-border);
  border-radius: 12px;
  backdrop-filter: blur(16px);
  box-shadow: var(--console-shadow);
}

.console-dialog-card {
  border: 1px solid var(--console-border);
  border-radius: 18px;
  background: var(--console-panel-bg);
}

@media (max-width: 900px) {
  .console-topbar {
    flex-direction: column;
    align-items: flex-start;
  }
  .topbar-right {
    width: 100%;
  }
  .console-page {
    gap: 12px;
    padding: 12px;
  }
}
</style>
