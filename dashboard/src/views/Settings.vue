<template>
  <div style="height: 100%; overflow-y: scroll">
    <!-- Proxy Settings -->
    <!-- <div class="text-h6 mb-2">{{ tm('network.title') }}</div> -->

    <v-list lines="two" subheader>
      <v-list-subheader>{{ tm("network.title") }}</v-list-subheader>

      <v-list-item
        :subtitle="tm('network.proxy.subtitle')"
        :title="tm('network.proxy.title')"
      >
        <ProxySelector />
      </v-list-item>

      <v-list-item
        :subtitle="tm('network.server.subtitle')"
        :title="tm('network.server.title')"
      >
        <!-- <div class="text-caption text-medium-emphasis mb-2">
            {{ tm('network.server.description') }}
        </div> -->
        <v-row class="mt-2">
          <v-col cols="12">
            <div class="d-flex align-center">
              <!-- <v-text-field
                v-model="apiBaseUrl"
                :label="tm('network.server.label')"
                variant="outlined"
                density="compact"
                hide-details
                class="flex-grow-1"
            ></v-text-field>
            <v-btn color="primary" class="ml-2" @click="saveApiUrl">
                {{ tm('common.save') }}
            </v-btn> -->

              <div class="mb-2">
                <div class="d-flex align-center justify-space-between mb-1">
                  <div class="text-caption text-medium-emphasis">
                    {{ tm("network.server.presets") }}
                  </div>
                  <v-btn
                    size="x-small"
                    variant="text"
                    prepend-icon="mdi-plus"
                    @click="showAddPreset = !showAddPreset"
                  >
                    {{ tm("network.server.preset.add") }}
                  </v-btn>
                </div>

                <v-expand-transition>
                  <div
                    v-if="showAddPreset"
                    class="mb-2 pa-2 bg-grey-lighten-4 rounded"
                  >
                    <v-text-field
                      v-model="newPresetName"
                      :label="tm('network.server.preset.name')"
                      density="compact"
                      hide-details
                      class="mb-2"
                      variant="outlined"
                      bg-color="white"
                    ></v-text-field>
                    <v-text-field
                      v-model="newPresetUrl"
                      :label="tm('network.server.preset.url')"
                      density="compact"
                      hide-details
                      class="mb-2"
                      variant="outlined"
                      bg-color="white"
                    ></v-text-field>
                    <v-btn
                      size="small"
                      block
                      color="primary"
                      variant="flat"
                      @click="savePreset"
                      >{{ tm("network.server.preset.add") }}</v-btn
                    >
                  </div>
                </v-expand-transition>

                <v-chip-group column>
                  <v-chip
                    v-for="preset in apiStore.presets"
                    :key="preset.name"
                    size="small"
                    @click="apiBaseUrl = preset.url"
                    :variant="apiBaseUrl === preset.url ? 'flat' : 'tonal'"
                    :color="apiBaseUrl === preset.url ? 'primary' : undefined"
                    :closable="isCustomPreset(preset.name)"
                    @click:close="apiStore.removePreset(preset.name)"
                  >
                    {{ preset.name }}
                  </v-chip>
                </v-chip-group>
              </div>
              <v-text-field
                v-model="apiBaseUrl"
                :label="tm('network.server.label')"
                :placeholder="tm('network.server.placeholder')"
                :hint="tm('network.server.hint')"
                persistent-hint
                hide-details="auto"
                variant="outlined"
                density="compact"
              >
                <template v-slot:append>
                  <v-btn
                    size="small"
                    color="primary"
                    variant="tonal"
                    @click="saveApiUrl"
                  >
                    {{ tm("network.server.save") }}
                  </v-btn>
                </template>
              </v-text-field>
            </div>
          </v-col>
        </v-row>
      </v-list-item>

      <v-list-subheader>{{ tm("apiKey.title") }}</v-list-subheader>

      <v-list-item :subtitle="tm('apiKey.subtitle')">
        <template #title>
          <div class="d-flex align-center">
            <span>{{ tm("apiKey.manageTitle") }}</span>
            <v-tooltip location="top">
              <template #activator="{ props }">
                <v-btn
                  v-bind="props"
                  icon
                  size="x-small"
                  variant="text"
                  class="ml-2"
                  :aria-label="tm('apiKey.docsLink')"
                  href="https://docs.astrbot.app/dev/openapi.html"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <v-icon size="18">mdi-help-circle-outline</v-icon>
                </v-btn>
              </template>
              <span>{{ tm("apiKey.docsLink") }}</span>
            </v-tooltip>
          </div>
        </template>
        <v-row class="mt-2" dense>
          <v-col cols="12" md="4">
            <v-text-field
              v-model="newApiKeyName"
              :label="tm('apiKey.name')"
              variant="outlined"
              density="compact"
              hide-details
            />
          </v-col>
          <v-col cols="12" md="3">
            <v-select
              v-model="newApiKeyExpiresInDays"
              :items="apiKeyExpiryOptions"
              :label="tm('apiKey.expiresInDays')"
              variant="outlined"
              density="compact"
              hide-details
            />
          </v-col>
          <v-col v-if="newApiKeyExpiresInDays === 'permanent'" cols="12">
            <v-alert type="warning" variant="tonal" density="comfortable">
              {{ tm("apiKey.permanentWarning") }}
            </v-alert>
          </v-col>
          <v-col cols="12" md="5" class="d-flex align-center">
            <v-btn
              color="primary"
              :loading="apiKeyCreating"
              @click="createApiKey"
            >
              <v-icon class="mr-2">mdi-key-plus</v-icon>
              {{ tm("apiKey.create") }}
            </v-btn>
          </v-col>

          <v-col cols="12">
            <div class="text-caption text-medium-emphasis mb-1">
              {{ tm("apiKey.scopes") }}
            </div>
            <v-chip-group v-model="newApiKeyScopes" multiple>
              <v-chip
                v-for="scope in availableScopes"
                :key="scope.value"
                :value="scope.value"
                :color="
                  newApiKeyScopes.includes(scope.value) ? 'primary' : undefined
                "
                :variant="
                  newApiKeyScopes.includes(scope.value) ? 'flat' : 'tonal'
                "
              >
                {{ scope.label }}
              </v-chip>
            </v-chip-group>
          </v-col>

          <v-col v-if="createdApiKeyPlaintext" cols="12">
            <v-alert type="warning" variant="tonal">
              <div class="d-flex align-center justify-space-between flex-wrap">
                <span>{{ tm("apiKey.plaintextHint") }}</span>
                <v-btn
                  size="small"
                  variant="text"
                  color="primary"
                  @click="copyCreatedApiKey"
                >
                  <v-icon class="mr-1">mdi-content-copy</v-icon
                  >{{ tm("apiKey.copy") }}
                </v-btn>
              </div>
              <code style="word-break: break-all">{{
                createdApiKeyPlaintext
              }}</code>
            </v-alert>
          </v-col>

          <v-col cols="12">
            <v-table density="compact">
              <thead>
                <tr>
                  <th>{{ tm("apiKey.table.name") }}</th>
                  <th>{{ tm("apiKey.table.prefix") }}</th>
                  <th>{{ tm("apiKey.table.scopes") }}</th>
                  <th>{{ tm("apiKey.table.status") }}</th>
                  <th>{{ tm("apiKey.table.lastUsed") }}</th>
                  <th>{{ tm("apiKey.table.createdAt") }}</th>
                  <th>{{ tm("apiKey.table.actions") }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in apiKeys" :key="item.key_id">
                  <td>{{ item.name }}</td>
                  <td>
                    <code>{{ item.key_prefix }}</code>
                  </td>
                  <td>{{ (item.scopes || []).join(", ") }}</td>
                  <td>
                    <v-chip
                      size="small"
                      :color="
                        item.is_revoked || item.is_expired ? 'error' : 'success'
                      "
                      variant="tonal"
                    >
                      {{
                        item.is_revoked || item.is_expired
                          ? tm("apiKey.status.inactive")
                          : tm("apiKey.status.active")
                      }}
                    </v-chip>
                  </td>
                  <td>{{ formatDate(item.last_used_at) }}</td>
                  <td>{{ formatDate(item.created_at) }}</td>
                  <td>
                    <v-btn
                      v-if="!item.is_revoked"
                      size="x-small"
                      color="warning"
                      variant="tonal"
                      class="mr-2"
                      @click="revokeApiKey(item.key_id)"
                    >
                      {{ tm("apiKey.revoke") }}
                    </v-btn>
                    <v-btn
                      size="x-small"
                      color="error"
                      variant="tonal"
                      @click="deleteApiKey(item.key_id)"
                    >
                      {{ tm("apiKey.delete") }}
                    </v-btn>
                  </td>
                </tr>
                <tr v-if="apiKeys.length === 0">
                  <td colspan="7" class="text-center text-medium-emphasis">
                    {{ tm("apiKey.empty") }}
                  </td>
                </tr>
              </tbody>
            </v-table>
          </v-col>
        </v-row>
      </v-list-item>

      <v-list-item
        :subtitle="tm('system.migration.subtitle')"
        :title="tm('system.migration.title')"
      >
        <v-btn
          style="margin-top: 16px"
          color="primary"
          @click="startMigration"
          >{{ tm("system.migration.button") }}</v-btn
        >
      </v-list-item>

      <v-list-subheader>{{ tm("sidebar.title") }}</v-list-subheader>

      <v-list-item
        :subtitle="tm('sidebar.customize.subtitle')"
        :title="tm('sidebar.customize.title')"
      >
        <SidebarCustomizer></SidebarCustomizer>
      </v-list-item>

      <v-list-subheader>{{ tm("style.title") }}</v-list-subheader>

      <v-list-item
        :subtitle="tm('style.color.subtitle')"
        :title="tm('style.color.title')"
      >
        <template #append> </template>

        <v-row class="mt-2" dense>
          <v-col cols="12" md="4">
            <v-text-field
              v-model="primaryColor"
              :label="tm('style.color.primary')"
              variant="outlined"
              density="compact"
              hide-details
            >
              <template v-slot:append-inner>
                <div
                  :style="{
                    backgroundColor: primaryColor,
                    width: '20px',
                    height: '20px',
                    borderRadius: '4px',
                    border: '1px solid #ccc',
                  }"
                  class="mr-2"
                ></div>
              </template>
            </v-text-field>
          </v-col>
          <v-col cols="12" md="4">
            <v-text-field
              v-model="secondaryColor"
              :label="tm('style.color.secondary')"
              variant="outlined"
              density="compact"
              hide-details
            >
              <template v-slot:append-inner>
                <div
                  :style="{
                    backgroundColor: secondaryColor,
                    width: '20px',
                    height: '20px',
                    borderRadius: '4px',
                    border: '1px solid #ccc',
                  }"
                  class="mr-2"
                ></div>
              </template>
            </v-text-field>
          </v-col>
          <v-col cols="12" md="4">
            <v-btn color="primary" block @click="applyThemeColors">
              <v-icon start>mdi-palette</v-icon>
              {{ t("core.common.save") }}
            </v-btn>
          </v-col>
        </v-row>
      </v-list-item>

      <v-list-subheader>{{ tm("backup.title") }}</v-list-subheader>

      <v-list-item
        :subtitle="tm('backup.subtitle')"
        :title="tm('backup.operate')"
      >
        <div class="d-flex align-center mt-2">
          <v-btn
            variant="tonal"
            prepend-icon="mdi-backup-restore"
            @click="openBackupDialog"
          >
            {{ tm("backup.open") }}
          </v-btn>
        </div>
      </v-list-item>

      <v-list-item :subtitle="tm('reset.subtitle')" :title="tm('reset.title')">
        <div class="d-flex align-center mt-2">
          <v-btn
            color="error"
            variant="tonal"
            prepend-icon="mdi-refresh"
            @click="resetThemeColors"
          >
            {{ tm("reset.button") }}
          </v-btn>
        </div>
      </v-list-item>

      <v-list-item
        :subtitle="tm('system.restart.subtitle')"
        :title="tm('system.restart.title')"
      >
        <div class="d-flex align-center mt-2">
          <v-btn
            color="warning"
            variant="tonal"
            prepend-icon="mdi-restart"
            @click="restartAstrBot"
          >
            {{ tm("system.restart.button") }}
          </v-btn>
        </div>
      </v-list-item>
    </v-list>
  </div>

  <WaitingForRestart ref="wfr" />
  <MigrationDialog ref="migrationDialog" />
  <BackupDialog ref="backupDialog" />
</template>

<script setup>
import { ref, onMounted, computed, watch } from "vue";
import { useTheme } from "vuetify";
import { useCustomizerStore } from "@/stores/customizer";
import { useCommonStore } from "@/stores/common";
import { useApiStore } from "@/stores/api";
import ProxySelector from "@/components/shared/ProxySelector.vue";
import SidebarCustomizer from "@/components/shared/SidebarCustomizer.vue";
import WaitingForRestart from "@/components/shared/WaitingForRestart.vue";
import MigrationDialog from "@/components/shared/MigrationDialog.vue";
import BackupDialog from "@/components/shared/BackupDialog.vue";
import axios from "axios";
import { useI18n, useModuleI18n } from "@/i18n/composables";
import { useToast } from "@/utils/toast";

const { t } = useI18n();
const { tm } = useModuleI18n("features/settings");
const toastStore = useToast();

/* const i18n = {
    network: {
        title: 'Network Settings',
        proxy: {
            title: 'Proxy',
            subtitle: 'Configure proxy for network requests',
        },
        server: {
            title: 'Server URL',
            subtitle: 'Configure backend server URL',
            label: 'Backend URL',
            description: 'Set the URL of your AstrBot backend server.',
            hint: 'e.g. http://localhost:6185',
        }
    },
    common: {
        save: 'Save',
    }
} */

const theme = useTheme();
const apiStore = useApiStore();

const apiBaseUrl = ref(apiStore.apiBaseUrl);

const showAddPreset = ref(false);
const newPresetName = ref("");
const newPresetUrl = ref("");

const savePreset = () => {
  if (newPresetName.value && newPresetUrl.value) {
    apiStore.addPreset({
      name: newPresetName.value,
      url: newPresetUrl.value,
    });
    newPresetName.value = "";
    newPresetUrl.value = "";
    showAddPreset.value = false;
  }
};

const isCustomPreset = (name) => {
  return !apiStore.configPresets.some((p) => p.name === name);
};

const saveApiUrl = () => {
  apiStore.setApiBaseUrl(apiBaseUrl.value);
  window.location.reload();
};

const getStoredColor = (key, defaultColor) => {
  const stored = localStorage.getItem(key);
  return stored ? stored : defaultColor;
};

// Initialize with stored values or current theme values
const primaryColor = ref(
  getStoredColor("themePrimary", theme.themes.value.PurpleTheme.colors.primary),
);
const secondaryColor = ref(
  getStoredColor(
    "themeSecondary",
    theme.themes.value.PurpleTheme.colors.secondary,
  ),
);

const resolveThemes = ["PurpleTheme", "PurpleThemeDark"];

// Watch for store changes to update local refs if reset happens elsewhere
const customizer = useCustomizerStore();

const applyThemeColors = () => {
  const themes = theme.themes.value;

  resolveThemes.forEach((name) => {
    const themeDef = themes[name];
    if (themeDef) {
      themeDef.colors.primary = primaryColor.value;
      themeDef.colors.secondary = secondaryColor.value;
      // Also update dark variants if needed, or keep them same/derived
      if (themeDef.colors.darkprimary)
        themeDef.colors.darkprimary = primaryColor.value;
      if (themeDef.colors.darksecondary)
        themeDef.colors.darksecondary = secondaryColor.value;
    }
  });

  // Save to localStorage
  localStorage.setItem("themePrimary", primaryColor.value);
  localStorage.setItem("themeSecondary", secondaryColor.value);

  // Force update CustomizerStore to trigger reactivity if needed
  // (Optional, depending on if other components react to store or Vuetify theme)
  customizer.setTheme(customizer.actTheme); // Re-set to trigger updates?

  toastStore.success(tm("common.saved"));
};

const wfr = ref(null);
const migrationDialog = ref(null);
const backupDialog = ref(null);
const apiKeys = ref([]);
const apiKeyCreating = ref(false);
const newApiKeyName = ref("");
const newApiKeyExpiresInDays = ref(30);
const newApiKeyScopes = ref(["chat"]);
const createdApiKeyPlaintext = ref("");
const apiKeyExpiryOptions = computed(() => [
  { title: tm("apiKey.expiry.7days"), value: 7 },
  { title: tm("apiKey.expiry.30days"), value: 30 },
  { title: tm("apiKey.expiry.90days"), value: 90 },
  { title: tm("apiKey.expiry.180days"), value: 180 },
  { title: tm("apiKey.expiry.365days"), value: 365 },
  // { title: tm('apiKey.expiry.permanent'), value: 'permanent' },
]);

const availableScopes = [
  { value: "chat", label: "Chat (chat)" },
  { value: "file", label: "File (file)" },
  { value: "config", label: "Config (config)" },
  { value: "im", label: "IM (im)" },
];

const showToast = (message, type = "success") => {
  // 简单的 toast 实现，或者使用你的 toastStore
  if (toastStore) {
    if (type === "success") toastStore.success(message);
    else if (type === "error") toastStore.error(message);
  } else {
    alert(message);
  }
};

const formatDate = (dateStr) => {
  if (!dateStr) return "-";
  const dt = new Date(dateStr);
  return dt.toLocaleString();
};

const loadApiKeys = async () => {
  try {
    const res = await axios.get("/api/v1/apikeys");
    if (res.data.data) {
      apiKeys.value = res.data.data;
    }
  } catch (e) {
    console.error(e);
    // showToast(tm('apiKey.loadFailed'), 'error');
  }
};

const tryExecCommandCopy = (text) => {
  let textArea = document.createElement("textarea");
  textArea.value = text;
  textArea.style.position = "fixed";
  textArea.style.left = "-9999px";
  textArea.style.top = "0";
  document.body.appendChild(textArea);
  textArea.focus();
  textArea.select();

  return new Promise((resolve, reject) => {
    let successful = false;
    try {
      successful = document.execCommand("copy");
    } catch (err) {
      console.warn("execCommand copy failed", err);
    }
    document.body.removeChild(textArea);
    if (successful) {
      resolve();
    } else {
      reject(new Error("execCommand failed"));
    }
  });
};

const copyTextToClipboard = async (text) => {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    try {
      await navigator.clipboard.writeText(text);
    } catch (err) {
      // fallback
      await tryExecCommandCopy(text);
    }
  } else {
    await tryExecCommandCopy(text);
  }
};

const copyCreatedApiKey = async () => {
  try {
    await copyTextToClipboard(createdApiKeyPlaintext.value);
    showToast(tm("common.copied"));
  } catch (e) {
    showToast(tm("common.copyFailed"), "error");
  }
};

const createApiKey = async () => {
  if (!newApiKeyName.value) {
    showToast(tm("apiKey.nameRequired"), "error");
    return;
  }

  // 如果全选了所有 scope，可以传 '*'，或者后端自己判断
  // 这里简单处理，传列表
  const selectedScopes = newApiKeyScopes.value;
  if (selectedScopes.length === 0) {
    showToast(tm("apiKey.scopeRequired"), "error");
    return;
  }

  apiKeyCreating.value = true;
  try {
    const payload = {
      name: newApiKeyName.value,
      scopes: selectedScopes,
      expires_in_days:
        newApiKeyExpiresInDays.value === "permanent"
          ? null
          : newApiKeyExpiresInDays.value,
    };

    const res = await axios.post("/api/v1/apikeys", payload);
    if (res.data.code === 0) {
      createdApiKeyPlaintext.value = res.data.data.api_key; // 只显示一次
      showToast(tm("apiKey.createSuccess"));
      newApiKeyName.value = "";
      newApiKeyScopes.value = ["chat"];
      await loadApiKeys();
    } else {
      showToast(res.data.message || tm("apiKey.createFailed"), "error");
    }
  } catch (e) {
    showToast(tm("apiKey.createFailed"), "error");
    console.error(e);
  } finally {
    apiKeyCreating.value = false;
  }
};

const revokeApiKey = async (keyId) => {
  try {
    const res = await axios.post(`/api/v1/apikeys/${keyId}/revoke`);
    if (res.data.code === 0) {
      showToast(tm("apiKey.revokeSuccess"));
      await loadApiKeys();
    }
  } catch (e) {
    showToast(tm("apiKey.revokeFailed"), "error");
  }
};

const deleteApiKey = async (keyId) => {
  if (!confirm(tm("common.deleteConfirm"))) return;
  try {
    const res = await axios.delete(`/api/v1/apikeys/${keyId}`);
    if (res.data.code === 0) {
      showToast(tm("apiKey.deleteSuccess"));
      await loadApiKeys();
    }
  } catch (e) {
    showToast(tm("apiKey.deleteFailed"), "error");
  }
};

const restartAstrBot = async () => {
  const commonStore = useCommonStore();
  commonStore.restartAstrBot();
  wfr.value.dialog = true;
};

const startMigration = async () => {
  if (migrationDialog.value) {
    const result = await migrationDialog.value.open();
    if (result) {
      // Migration started or completed
    }
  }
};

const openBackupDialog = () => {
  backupDialog.value.open();
};

const resetThemeColors = () => {
  localStorage.removeItem("themePrimary");
  localStorage.removeItem("themeSecondary");
  window.location.reload();
};

onMounted(() => {
  loadApiKeys();
});
</script>
