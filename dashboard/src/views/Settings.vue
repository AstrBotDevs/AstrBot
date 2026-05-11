<template>
  <div class="settings-page">
    <!-- Network Card -->
    <v-card class="mb-4" variant="flat">
      <v-card-title class="d-flex align-center">
        <v-icon class="mr-2" size="20">mdi-earth</v-icon>
        {{ tm("network.title") }}
      </v-card-title>
      <v-card-text>
        <ProxySelector />
      </v-card-text>
    </v-card>

    <!-- Sidebar Card -->
    <v-card class="mb-4" variant="flat">
      <v-card-title class="d-flex align-center">
        <v-icon class="mr-2" size="20">mdi-menu</v-icon>
        {{ tm("sidebar.title") }}
      </v-card-title>
      <v-card-subtitle>{{ tm("sidebar.customize.subtitle") }}</v-card-subtitle>
      <v-card-text>
        <SidebarCustomizer />
      </v-card-text>
    </v-card>

    <!-- Theme Card -->
    <v-card class="mb-4" variant="flat">
      <v-card-title class="d-flex align-center">
        <v-icon class="mr-2" size="20">mdi-palette</v-icon>
        {{ tm("theme.customize.title") }}
      </v-card-title>
      <v-card-subtitle>{{ tm("theme.subtitle") }}</v-card-subtitle>
      <v-card-text>
        <!-- Row 1: Preset selector + theme mode -->
        <div class="d-flex flex-wrap align-center ga-4 mb-4 ml-3">
          <v-select
            v-model="selectedThemePreset"
            :items="presetOptions"
            :label="tm('theme.customize.preset')"
            hide-details
            variant="outlined"
            density="compact"
            style="min-width: 200px; max-width: 280px"
            @update:model-value="applyThemePreset"
          />
          <v-btn-toggle
            v-model="themeMode"
            mandatory
            density="compact"
            color="primary"
          >
            <v-btn value="light" size="small">
              <v-icon class="mr-1" size="18">mdi-white-balance-sunny</v-icon>
              {{ tm("theme.customize.light") }}
            </v-btn>
            <v-btn value="dark" size="small">
              <v-icon class="mr-1" size="18">mdi-moon-waning-crescent</v-icon>
              {{ tm("theme.customize.dark") }}
            </v-btn>
            <v-btn value="auto" size="small">
              <v-icon class="mr-1" size="18">mdi-sync</v-icon>
              {{ tm("theme.customize.auto") }}
            </v-btn>
          </v-btn-toggle>
          <v-tooltip location="top">
            <template #activator="{ props }">
              <v-icon v-bind="props" size="16" color="primary" class="ml-1"
                >mdi-help-circle-outline</v-icon
              >
            </template>
            <span>{{ tm("theme.customize.autoSwitchDesc") }}</span>
          </v-tooltip>
        </div>

        <!-- Row 2: Color pickers + reset -->
        <v-card variant="outlined" class="pa-3">
          <div class="text-body-2 text-medium-emphasis mb-3">
            {{ tm("theme.customize.colors") }}
          </div>
          <div class="d-flex flex-wrap align-center ga-4">
            <div class="d-flex align-center ga-3">
              <v-text-field
                v-model="primaryColor"
                type="color"
                :label="tm('theme.customize.primary')"
                hide-details
                variant="outlined"
                density="compact"
                style="width: 140px"
              />
              <div
                class="color-preview"
                :style="{ backgroundColor: primaryColor }"
              />
            </div>
            <div class="d-flex align-center ga-3">
              <v-text-field
                v-model="secondaryColor"
                type="color"
                :label="tm('theme.customize.secondary')"
                hide-details
                variant="outlined"
                density="compact"
                style="width: 140px"
              />
              <div
                class="color-preview"
                :style="{ backgroundColor: secondaryColor }"
              />
            </div>
            <v-btn
              size="small"
              variant="tonal"
              color="primary"
              @click="resetThemeColors"
            >
              <v-icon class="mr-1" size="16">mdi-restore</v-icon>
              {{ tm("theme.customize.reset") }}
            </v-btn>
          </div>
        </v-card>
      </v-card-text>
    </v-card>

    <!-- System Card -->
    <v-card class="mb-4" variant="flat">
      <v-card-title class="d-flex align-center">
        <v-icon class="mr-2" size="20">mdi-cog</v-icon>
        {{ tm("system.title") }}
      </v-card-title>
      <v-card-text>
        <div class="d-flex flex-wrap ga-3 mb-4">
          <div>
            <div class="text-body-2 mb-1">{{ tm("system.backup.title") }}</div>
            <div class="text-caption text-medium-emphasis mb-2">
              {{ tm("system.backup.subtitle") }}
            </div>
            <v-btn color="primary" size="small" @click="openBackupDialog">
              <v-icon class="mr-1" size="16">mdi-backup-restore</v-icon>
              {{ tm("system.backup.button") }}
            </v-btn>
          </div>
          <v-divider vertical class="mx-2 mx-md-4" />
          <div>
            <div class="text-body-2 mb-1">{{ tm("system.restart.title") }}</div>
            <div class="text-caption text-medium-emphasis mb-2">
              {{ tm("system.restart.subtitle") }}
            </div>
            <v-btn color="error" size="small" @click="restartAstrBot">
              <v-icon class="mr-1" size="16">mdi-restart</v-icon>
              {{ tm("system.restart.button") }}
            </v-btn>
          </div>
          <v-divider vertical class="mx-2 mx-md-4" />
          <div>
            <div class="text-body-2 mb-1">
              {{ tm("system.migration.title") }}
            </div>
            <div class="text-caption text-medium-emphasis mb-2">
              {{ tm("system.migration.subtitle") }}
            </div>
            <v-btn
              color="primary"
              size="small"
              variant="outlined"
              @click="startMigration"
            >
              <v-icon class="mr-1" size="16">mdi-database-import</v-icon>
              {{ tm("system.migration.button") }}
            </v-btn>
          </div>
        </div>
        <StorageCleanupPanel />
      </v-card-text>
    </v-card>

    <!-- API Key Card -->
    <v-card class="mb-4" variant="flat">
      <v-card-title class="d-flex align-center">
        <v-icon class="mr-2" size="20">mdi-key</v-icon>
        {{ tm("apiKey.manageTitle") }}
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
      </v-card-title>
      <v-card-subtitle>{{ tm("apiKey.subtitle") }}</v-card-subtitle>
      <v-card-text>
        <v-row density="compact">
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
          <v-col v-if="newApiKeyExpiresInDays === 'permanent'" cols="12">
            <v-alert type="warning" variant="tonal" density="comfortable">
              {{ tm("apiKey.permanentWarning") }}
            </v-alert>
          </v-col>
          <v-col cols="12">
            <div class="text-caption text-medium-emphasis mb-2">
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
                  <v-icon class="mr-1">mdi-content-copy</v-icon>
                  {{ tm("apiKey.copy") }}
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
      </v-card-text>
    </v-card>
  </div>

  <WaitingForRestart ref="wfr" />
  <MigrationDialog ref="migrationDialog" />
  <BackupDialog ref="backupDialog" />
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import axios, { AxiosError } from "@/utils/request";
import WaitingForRestart from "@/components/shared/WaitingForRestart.vue";
import ProxySelector from "@/components/shared/ProxySelector.vue";
import MigrationDialog from "@/components/shared/MigrationDialog.vue";
import SidebarCustomizer from "@/components/shared/SidebarCustomizer.vue";
import BackupDialog from "@/components/shared/BackupDialog.vue";
import StorageCleanupPanel from "@/components/shared/StorageCleanupPanel.vue";
import { restartAstrBot as restartAstrBotRuntime } from "@/utils/restartAstrBot";
import { useModuleI18n } from "@/i18n/composables";
import { useTheme } from "vuetify";
import { BlueBusinessLightTheme } from "@/theme/BlueBusinessLightTheme";
import {
  LIGHT_THEME_NAME,
  DARK_THEME_NAME,
  ThemeMode,
} from "@/theme/constants";
import { useToastStore } from "@/stores/toast";
import { useCustomizerStore } from "@/stores/customizer";
import {
  ApiKey,
  ApiKeyActionResponse,
  ApiKeyCreatePayload,
  ApiKeyCreateResponse,
  ApiKeyExpiresDays,
  ApiKeyListResponse,
} from "@/types/api";

interface WfrHandle {
  check: (initialStartTime?: number | null) => void | Promise<void>;
  stop?: () => void;
}

interface MigrationDialogHandle {
  open: () => Promise<{ success: boolean; message: string }>;
}

interface BackupDialogHandle {
  open: () => void;
}

const { tm } = useModuleI18n("features/settings");
const toastStore = useToastStore();
const theme = useTheme();
const customizer = useCustomizerStore();

// Theme mode toggle (light/dark/auto)
const themeMode = computed({
  get() {
    if (customizer.autoSwitchTheme) return "auto";
    return customizer.isDarkTheme ? "dark" : "light";
  },
  set(mode: ThemeMode) {
    if (mode === "auto") {
      customizer.SET_AUTO_SYNC(true);
      customizer.APPLY_SYSTEM_THEME();
      return;
    }

    customizer.SET_AUTO_SYNC(false);
    const newTheme = mode === "dark" ? DARK_THEME_NAME : LIGHT_THEME_NAME;
    customizer.SET_UI_THEME(newTheme);
  },
});

const getStoredColor = (key: string, fallback: string) => {
  const stored =
    typeof window !== "undefined" ? localStorage.getItem(key) : null;
  return stored || fallback;
};

const primaryColor = ref(
  getStoredColor("themePrimary", BlueBusinessLightTheme.colors.primary),
);
const secondaryColor = ref(
  getStoredColor("themeSecondary", BlueBusinessLightTheme.colors.secondary),
);

// Theme presets based on MD3 color system
const themePresets = [
  {
    id: "blue-business",
    name: "活力商务蓝",
    nameEn: "Business Blue",
    primary: "#005FB0",
    secondary: "#565E71",
    tertiary: "#006B5B",
  },
  {
    id: "purple-default",
    name: "优雅紫",
    nameEn: "Elegant Purple",
    primary: "#6750A4",
    secondary: "#625B71",
    tertiary: "#7D5260",
  },
  {
    id: "teal-fresh",
    name: "自然清新绿",
    nameEn: "Nature Green",
    primary: "#386A20",
    secondary: "#55624C",
    tertiary: "#19686A",
  },
  {
    id: "orange-warm",
    name: "温暖橙棕",
    nameEn: "Warm Orange",
    primary: "#9C4323",
    secondary: "#77574E",
    tertiary: "#6C5D2F",
  },
  {
    id: "ocean-breeze",
    name: "海洋清风",
    nameEn: "Ocean Breeze",
    primary: "#0077B6",
    secondary: "#4A5568",
    tertiary: "#00B4D8",
  },
  {
    id: "rose-romantic",
    name: "浪漫玫瑰",
    nameEn: "Romantic Rose",
    primary: "#BE185D",
    secondary: "#9F1239",
    tertiary: "#DB2777",
  },
];

// Get stored preset or default to blue-business name
const selectedThemePreset = ref(
  localStorage.getItem("themePreset") || themePresets[0].name,
);

// Simple array for dropdown display
const presetOptions = themePresets.map((p) => p.name);

const applyThemePreset = (presetName: string) => {
  const preset = themePresets.find((p) => p.name === presetName);
  if (!preset) return;

  // Store the preset selection (store by name for display consistency)
  localStorage.setItem("themePreset", presetName);
  selectedThemePreset.value = presetName;

  // Update primary and secondary colors
  primaryColor.value = preset.primary;
  secondaryColor.value = preset.secondary;
  localStorage.setItem("themePrimary", preset.primary);
  localStorage.setItem("themeSecondary", preset.secondary);

  // Apply to themes
  applyThemeColors(preset.primary, preset.secondary);

  toastStore.add({
    message: tm("theme.customize.presetApplied") || "主题已应用",
    color: "success",
  });
};

const resolveThemes = () => {
  return theme?.global?.themes?.value ?? null;
};

const applyThemeColors = (primary: string, secondary: string) => {
  const themes = resolveThemes();
  if (!themes) return;
  [LIGHT_THEME_NAME, DARK_THEME_NAME].forEach((name) => {
    const themeDef = themes[name];
    if (!themeDef?.colors) return;
    if (primary) themeDef.colors.primary = primary;
    if (secondary) themeDef.colors.secondary = secondary;
    if (primary && themeDef.colors.darkprimary)
      themeDef.colors.darkprimary = primary;
    if (secondary && themeDef.colors.darksecondary)
      themeDef.colors.darksecondary = secondary;
  });
};

applyThemeColors(primaryColor.value, secondaryColor.value);

watch(primaryColor, (value) => {
  if (!value) return;
  localStorage.setItem("themePrimary", value);
  applyThemeColors(value, secondaryColor.value);
});

watch(secondaryColor, (value) => {
  if (!value) return;
  localStorage.setItem("themeSecondary", value);
  applyThemeColors(primaryColor.value, value);
});

const resetThemeColors = () => {
  primaryColor.value = BlueBusinessLightTheme.colors.primary;
  secondaryColor.value = BlueBusinessLightTheme.colors.secondary;
  localStorage.removeItem("themePrimary");
  localStorage.removeItem("themeSecondary");
  applyThemeColors(primaryColor.value, secondaryColor.value);
};

const wfr = ref<WfrHandle | null>(null);
const migrationDialog = ref<MigrationDialogHandle | null>(null);
const backupDialog = ref<BackupDialogHandle | null>(null);
const apiKeys = ref<ApiKey[]>([]);
const apiKeyCreating = ref(false);
const newApiKeyName = ref("");
const newApiKeyExpiresInDays = ref<ApiKeyExpiresDays>(30);
const newApiKeyScopes = ref(["chat", "config", "file", "im"]);
const createdApiKeyPlaintext = ref("");
const apiKeyExpiryOptions = computed(() => [
  { title: tm("apiKey.expiryOptions.day1"), value: 1 },
  { title: tm("apiKey.expiryOptions.day7"), value: 7 },
  { title: tm("apiKey.expiryOptions.day30"), value: 30 },
  { title: tm("apiKey.expiryOptions.day90"), value: 90 },
  { title: tm("apiKey.expiryOptions.permanent"), value: "permanent" },
]);

const availableScopes = [
  { value: "chat", label: "chat" },
  { value: "config", label: "config" },
  { value: "file", label: "file" },
  { value: "im", label: "im" },
];

const showToast = (
  message: string,
  color: "success" | "error" | "warning" = "success",
) => {
  toastStore.add({
    message,
    color,
    timeout: 3000,
  });
};

const formatDate = (value: string | null) => {
  if (!value) return "-";
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return "-";
  return dt.toLocaleString();
};

const loadApiKeys = async () => {
  try {
    const res = await axios.get<ApiKeyListResponse>("/api/apikey/list");
    if (res.data.status !== "ok") {
      showToast(res.data.message || tm("apiKey.messages.loadFailed"), "error");
      return;
    }
    apiKeys.value = res.data.data;
  } catch (e: unknown) {
    if (e instanceof AxiosError) {
      const data = e.response?.data as { message?: string } | undefined;
      showToast(
        data?.message || tm("apiKey.messages.loadFailed"),
        "error",
      );
    } else {
      console.error("An unexpected error occurred while loading API keys:", e);
      showToast(tm("apiKey.messages.loadFailed"), "error");
    }
  }
};

const tryExecCommandCopy = (text: string): boolean => {
  let textArea: HTMLTextAreaElement | null = null;
  try {
    if (typeof document === "undefined" || !document.body) return false;
    textArea = document.createElement("textarea");
    textArea.value = text;
    textArea.setAttribute("readonly", "");
    textArea.style.position = "fixed";
    textArea.style.opacity = "0";
    textArea.style.pointerEvents = "none";
    textArea.style.left = "-9999px";
    document.body.appendChild(textArea);
    textArea.focus();
    textArea.select();
    textArea.setSelectionRange(0, text.length);
    // Fallback to deprecated execCommand for older browsers
    return document.execCommand("copy");
  } catch (_) {
    return false;
  } finally {
    try {
      if (textArea?.parentNode) {
        textArea.parentNode.removeChild(textArea);
      }
    } catch (_) {
      // ignore cleanup errors
    }
  }
};

const copyTextToClipboard = async (text: string): Promise<boolean> => {
  if (!text) return false;

  // 由于execCommand被弃用，改用推荐的Clipboard API，但仍保留execCommand作为兼容性回退
  if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch (_) {
      // Clipboard API failed, try fallback method
    }
  }

  // 回退到execCommand方法，兼容不支持Clipboard API的环境
  return tryExecCommandCopy(text);
};

const copyCreatedApiKey = async () => {
  if (!createdApiKeyPlaintext.value) return;
  const ok = await copyTextToClipboard(createdApiKeyPlaintext.value);
  if (ok) {
    showToast(tm("apiKey.messages.copySuccess"), "success");
  } else {
    showToast(tm("apiKey.messages.copyFailed"), "error");
  }
};

const createApiKey = async () => {
  const selectedScopes = availableScopes
    .map((scope) => scope.value)
    .filter((scope) => newApiKeyScopes.value.includes(scope));

  if (selectedScopes.length === 0) {
    showToast(tm("apiKey.messages.scopeRequired"), "warning");
    return;
  }
  apiKeyCreating.value = true;
  try {
    const payload: ApiKeyCreatePayload = {
      name: newApiKeyName.value,
      scopes: selectedScopes,
    };
    if (newApiKeyExpiresInDays.value !== "permanent") {
      payload.expires_in_days = Number(newApiKeyExpiresInDays.value);
    }
    const res = await axios.post<ApiKeyCreateResponse>(
      "/api/apikey/create",
      payload,
    );
    if (res.data.status !== "ok") {
      showToast(
        res.data.message || tm("apiKey.messages.createFailed"),
        "error",
      );
      return;
    }
    createdApiKeyPlaintext.value = res.data.data?.api_key || "";
    newApiKeyName.value = "";
    newApiKeyExpiresInDays.value = 30;
    showToast(tm("apiKey.messages.createSuccess"), "success");
    await loadApiKeys();
  } catch (e: unknown) {
    if (e instanceof AxiosError) {
      const data = e.response?.data as { message?: string } | undefined;
      showToast(
        data?.message || tm("apiKey.messages.createFailed"),
        "error",
      );
    } else {
      console.error("An unexpected error occurred while creating API key:", e);
      showToast(tm("apiKey.messages.createFailed"), "error");
    }
  } finally {
    apiKeyCreating.value = false;
  }
};

const revokeApiKey = async (keyId: string) => {
  try {
    const res = await axios.post<ApiKeyActionResponse>("/api/apikey/revoke", {
      key_id: keyId,
    });
    if (res.data.status !== "ok") {
      showToast(
        res.data.message || tm("apiKey.messages.revokeFailed"),
        "error",
      );
      return;
    }
    showToast(tm("apiKey.messages.revokeSuccess"), "success");
    await loadApiKeys();
  } catch (e: unknown) {
    if (e instanceof AxiosError) {
      const data = e.response?.data as { message?: string } | undefined;
      showToast(
        data?.message || tm("apiKey.messages.revokeFailed"),
        "error",
      );
    } else {
      console.error("An unexpected error occurred while revoking API key:", e);
      showToast(tm("apiKey.messages.revokeFailed"), "error");
    }
  }
};

const deleteApiKey = async (keyId: string) => {
  try {
    const res = await axios.post<ApiKeyActionResponse>("/api/apikey/delete", {
      key_id: keyId,
    });
    if (res.data.status !== "ok") {
      showToast(
        res.data.message || tm("apiKey.messages.deleteFailed"),
        "error",
      );
      return;
    }
    showToast(tm("apiKey.messages.deleteSuccess"), "success");
    await loadApiKeys();
  } catch (e: unknown) {
    if (e instanceof AxiosError) {
      const data = e.response?.data as { message?: string } | undefined;
      showToast(
        data?.message || tm("apiKey.messages.deleteFailed"),
        "error",
      );
    } else {
      console.error("An unexpected error occurred while deleting API key:", e);
      showToast(tm("apiKey.messages.deleteFailed"), "error");
    }
  }
};

const restartAstrBot = async () => {
  try {
    await restartAstrBotRuntime(wfr.value);
  } catch (error: unknown) {
    if (error instanceof AxiosError) {
      const data = error.response?.data as { message?: string } | undefined;
      showToast(
        data?.message || tm("apiKey.messages.restartFailed"),
        "error",
      );
    } else {
      console.error(
        "An unexpected error occurred while restarting AstrBot:",
        error,
      );
      showToast(tm("apiKey.messages.restartFailed"), "error");
    }
  }
};

const startMigration = async () => {
  if (migrationDialog.value) {
    try {
      const result = await migrationDialog.value.open();
      if (result.success) {
        console.info("Migration completed successfully:", result.message);
      }
    } catch (error) {
      console.error("Migration dialog error:", error);
    }
  }
};

const openBackupDialog = () => {
  if (backupDialog.value) {
    backupDialog.value.open();
  }
};

onMounted(() => {
  loadApiKeys();
});
</script>
