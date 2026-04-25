<template>
  <v-dialog v-model="dialog" max-width="880" scrollable class="chat-settings-dialog">
    <v-card class="settings-card">
      <v-btn
        icon="mdi-close"
        variant="text"
        size="small"
        class="close-btn"
        :aria-label="tm('settings.close')"
        @click="dialog = false"
      />

      <div class="settings-shell">
        <aside class="settings-nav">
          <button
            type="button"
            class="nav-item"
            :class="{ active: activePanel === 'basic' }"
            @click="activePanel = 'basic'"
          >
            <v-icon size="18">mdi-cog-outline</v-icon>
            <span>{{ tm('settings.basic') }}</span>
          </button>
          <button
            v-if="isAdmin"
            type="button"
            class="nav-item"
            :class="{ active: activePanel === 'users' }"
            @click="activePanel = 'users'"
          >
            <v-icon size="18">mdi-account-multiple-outline</v-icon>
            <span>{{ tm('settings.multiUser') }}</span>
          </button>
        </aside>

        <section class="settings-content">
          <template v-if="activePanel === 'basic'">
            <header class="content-header">
              <div>
                <h2>{{ tm('settings.basic') }}</h2>
                <p>{{ tm('settings.basicSubtitle') }}</p>
              </div>
            </header>

            <section class="settings-list">
              <article class="setting-row">
                <div class="setting-copy">
                  <h3>{{ tm('settings.language') }}</h3>
                  <p>{{ tm('settings.languageSubtitle') }}</p>
                </div>
                <v-select
                  :model-value="locale"
                  :items="languageOptions"
                  item-title="label"
                  item-value="value"
                  density="compact"
                  variant="outlined"
                  hide-details
                  class="setting-control"
                  @update:model-value="switchLanguage($event as Locale)"
                >
                  <template #selection="{ item }">
                    <span class="language-flag">{{ item.raw.flag }}</span>
                    <span>{{ item.raw.label }}</span>
                  </template>
                  <template #item="{ props: itemProps, item }">
                    <v-list-item v-bind="itemProps">
                      <template #prepend>
                        <span class="language-flag">{{ item.raw.flag }}</span>
                      </template>
                    </v-list-item>
                  </template>
                </v-select>
              </article>

              <article class="setting-row">
                <div class="setting-copy">
                  <h3>{{ tm('settings.appearance') }}</h3>
                  <p>{{ tm('settings.appearanceSubtitle') }}</p>
                </div>
                <v-btn-toggle
                  v-model="selectedTheme"
                  mandatory
                  divided
                  class="setting-toggle"
                >
                  <v-btn value="light" prepend-icon="mdi-white-balance-sunny">
                    {{ tm('settings.light') }}
                  </v-btn>
                  <v-btn value="dark" prepend-icon="mdi-weather-night">
                    {{ tm('settings.dark') }}
                  </v-btn>
                </v-btn-toggle>
              </article>

              <article class="setting-row">
                <div class="setting-copy">
                  <h3>{{ tm('transport.title') }}</h3>
                </div>
                <v-btn-toggle
                  v-model="selectedTransportMode"
                  mandatory
                  divided
                  class="setting-toggle"
                >
                  <v-btn value="sse" prepend-icon="mdi-swap-horizontal">
                    SSE
                  </v-btn>
                  <v-btn value="websocket" prepend-icon="mdi-connection">
                    WebSocket
                  </v-btn>
                </v-btn-toggle>
              </article>
            </section>
          </template>

          <template v-else>
            <header class="content-header">
              <div>
                <h2>{{ tm('settings.multiUser') }}</h2>
                <p>{{ tm('settings.multiUserSubtitle') }}</p>
              </div>
            </header>

            <v-alert
              v-if="generatedPassword"
              class="password-alert"
              color="success"
              variant="tonal"
              density="comfortable"
              icon="mdi-key-variant"
            >
              <div class="password-alert-body">
                <div>
                  <div class="password-alert-title">
                    {{ tm('settings.passwordShownOnce', { username: generatedPassword.username }) }}
                  </div>
                  <code>{{ generatedPassword.password }}</code>
                </div>
                <v-btn
                  variant="text"
                  color="success"
                  prepend-icon="mdi-content-copy"
                  @click="copyPassword(generatedPassword.password)"
                >
                  {{ tm('actions.copy') }}
                </v-btn>
              </div>
            </v-alert>

            <section v-if="selectedUser" class="user-detail-panel">
              <button
                type="button"
                class="back-button"
                @click="selectedUserId = ''"
              >
                {{ tm('settings.backToUsers') }}
              </button>

              <div class="user-detail-title">
                <h3>{{ selectedUser.username }}</h3>
              </div>

              <article class="user-detail-row">
                <div class="setting-copy">
                  <h3>{{ tm('settings.configFiles') }}</h3>
                </div>
                <v-select
                  v-model="selectedUser.allowed_config_ids"
                  :items="configOptions"
                  item-title="name"
                  item-value="id"
                  :label="tm('settings.allowedConfigFiles')"
                  density="comfortable"
                  variant="outlined"
                  multiple
                  chips
                  hide-details
                  class="detail-control"
                  @update:model-value="updateUser(selectedUser)"
                />
              </article>

              <article class="user-detail-row">
                <div class="setting-copy">
                  <h3>{{ tm('settings.manageProvidersAndModels') }}</h3>
                </div>
                <v-switch
                  v-model="selectedUser.allow_provider_management"
                  color="primary"
                  density="compact"
                  inset
                  hide-details
                  @update:model-value="updateUser(selectedUser)"
                />
              </article>

              <article class="user-detail-row">
                <div class="setting-copy">
                  <h3>{{ tm('settings.enabled') }}</h3>
                </div>
                <v-switch
                  v-model="selectedUser.enabled"
                  color="primary"
                  density="compact"
                  inset
                  hide-details
                  @update:model-value="updateUser(selectedUser)"
                />
              </article>

              <div class="user-detail-actions">
                <v-btn
                  variant="outlined"
                  class="neutral-outline-btn"
                  :loading="resettingUserId === selectedUser.user_id"
                  @click="resetPassword(selectedUser)"
                >
                  {{ tm('settings.resetPassword') }}
                </v-btn>
                <v-btn
                  variant="outlined"
                  color="error"
                  :loading="deletingUserId === selectedUser.user_id"
                  @click="deleteUser(selectedUser)"
                >
                  {{ tm('settings.deleteUser') }}
                </v-btn>
              </div>
            </section>

            <template v-else>
              <div v-if="loading" class="text-center py-10">
                <v-progress-circular indeterminate color="primary" />
              </div>

              <section v-else class="user-list">
                <h3 class="user-list-title">{{ tm('settings.createdUsers') }}</h3>
                <button
                  v-for="user in users"
                  :key="user.user_id"
                  type="button"
                  class="user-list-item"
                  @click="selectedUserId = user.user_id"
                >
                  <v-avatar class="user-list-avatar" size="28">
                    {{ user.username.slice(0, 1).toUpperCase() }}
                  </v-avatar>
                  <span class="user-list-name">{{ user.username }}</span>
                  <v-chip
                    size="x-small"
                    label
                    class="user-status-chip"
                    :class="{ 'is-disabled': !user.enabled }"
                  >
                    {{ user.enabled ? tm('settings.enabledStatus') : tm('settings.disabled') }}
                  </v-chip>
                  <span class="user-list-arrow">›</span>
                </button>

                <div v-if="users.length === 0" class="empty-state">
                  {{ tm('settings.noUsers') }}
                </div>
              </section>

              <section class="create-action-section">
                <v-btn
                  class="create-user-outline-btn"
                  variant="outlined"
                  prepend-icon="mdi-account-plus-outline"
                  @click="createUserDialog = true"
                >
                  {{ tm('settings.createUser') }}
                </v-btn>
              </section>
            </template>
          </template>
        </section>
      </div>
    </v-card>
  </v-dialog>

  <v-dialog v-model="createUserDialog" max-width="520">
    <v-card class="create-user-card">
      <v-card-title class="create-user-title">
        <span>{{ tm('settings.createUser') }}</span>
        <v-btn
          icon="mdi-close"
          variant="text"
          size="small"
          @click="createUserDialog = false"
        />
      </v-card-title>
      <v-card-text class="create-user-body">
        <v-text-field
          v-model="newUsername"
          :label="tm('settings.username')"
          density="comfortable"
          variant="outlined"
          hide-details
          autofocus
        />
        <v-select
          v-model="newAllowedConfigIds"
          :items="configOptions"
          item-title="name"
          item-value="id"
          :label="tm('settings.allowedConfigFiles')"
          density="comfortable"
          variant="outlined"
          multiple
          chips
          hide-details
        />
        <v-switch
          v-model="newAllowProviderManagement"
          color="primary"
          density="comfortable"
          inset
          hide-details
          :label="tm('settings.manageProvidersAndModels')"
        />
      </v-card-text>
      <v-card-actions class="create-user-actions">
        <v-spacer />
        <v-btn variant="text" @click="createUserDialog = false">
          {{ tm('settings.cancel') }}
        </v-btn>
        <v-btn
          color="primary"
          :loading="creating"
          :disabled="!newUsername.trim()"
          @click="createUser"
        >
          {{ tm('settings.create') }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import axios from 'axios';
import { useLanguageSwitcher, useModuleI18n } from '@/i18n/composables';
import type { Locale } from '@/i18n/types';
import { useAuthStore } from '@/stores/auth';
import { useCustomizerStore } from '@/stores/customizer';
import { useToast } from '@/utils/toast';

type SettingsPanel = 'basic' | 'users';
type TransportMode = 'sse' | 'websocket';
type ThemeMode = 'light' | 'dark';

interface WebUIUser {
  user_id: string;
  username: string;
  scope: string;
  enabled: boolean;
  allowed_config_ids: string[];
  allow_provider_management: boolean;
}

interface ConfigInfo {
  id: string;
  name: string;
}

interface PasswordPayload {
  username: string;
  password: string;
}

const props = defineProps<{
  modelValue: boolean;
  transportMode: TransportMode;
}>();

const emit = defineEmits<{
  'update:modelValue': [value: boolean];
  'update:transportMode': [value: TransportMode];
}>();

const dialog = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit('update:modelValue', value),
});

const toast = useToast();
const authStore = useAuthStore();
const customizer = useCustomizerStore();
const { tm } = useModuleI18n('features/chat');
const { languageOptions, switchLanguage, locale } = useLanguageSwitcher();
const activePanel = ref<SettingsPanel>('basic');
const users = ref<WebUIUser[]>([]);
const configOptions = ref<ConfigInfo[]>([]);
const loading = ref(false);
const creating = ref(false);
const createUserDialog = ref(false);
const deletingUserId = ref('');
const resettingUserId = ref('');
const selectedUserId = ref('');
const generatedPassword = ref<PasswordPayload | null>(null);
const newUsername = ref('');
const newAllowedConfigIds = ref<string[]>(['default']);
const newAllowProviderManagement = ref(false);

const isAdmin = computed(() => authStore.role === 'admin');
const selectedUser = computed(() =>
  users.value.find((user) => user.user_id === selectedUserId.value) || null,
);
const selectedTransportMode = computed({
  get: () => props.transportMode,
  set: (value: TransportMode) => emit('update:transportMode', value),
});
const selectedTheme = computed({
  get: (): ThemeMode => (customizer.uiTheme === 'PurpleThemeDark' ? 'dark' : 'light'),
  set: (value: ThemeMode) => {
    customizer.SET_UI_THEME(value === 'dark' ? 'PurpleThemeDark' : 'PurpleTheme');
  },
});

async function loadUsersData() {
  if (!isAdmin.value) return;
  loading.value = true;
  try {
    const [usersRes, configsRes] = await Promise.all([
      axios.get('/api/webui/users'),
      axios.get('/api/config/abconfs'),
    ]);
    users.value = usersRes.data.data || [];
    configOptions.value = configsRes.data.data?.info_list || [];
    if (selectedUserId.value && !users.value.some((user) => user.user_id === selectedUserId.value)) {
      selectedUserId.value = '';
    }
  } catch (error: any) {
    toast.error(error?.response?.data?.message || tm('settings.loadUsersFailed'));
  } finally {
    loading.value = false;
  }
}

async function createUser() {
  creating.value = true;
  try {
    const res = await axios.post('/api/webui/users/create', {
      username: newUsername.value.trim(),
      scope: 'chatui',
      allowed_config_ids: newAllowedConfigIds.value,
      allow_provider_management: newAllowProviderManagement.value,
    });
    generatedPassword.value = {
      username: res.data.data.username,
      password: res.data.data.initial_password,
    };
    newUsername.value = '';
    newAllowedConfigIds.value = ['default'];
    newAllowProviderManagement.value = false;
    createUserDialog.value = false;
    await loadUsersData();
  } catch (error: any) {
    toast.error(error?.response?.data?.message || tm('settings.createUserFailed'));
  } finally {
    creating.value = false;
  }
}

async function updateUser(user: WebUIUser) {
  try {
    await axios.post('/api/webui/users/update', {
      user_id: user.user_id,
      enabled: user.enabled,
      allowed_config_ids: user.allowed_config_ids,
      allow_provider_management: user.allow_provider_management,
    });
  } catch (error: any) {
    toast.error(error?.response?.data?.message || tm('settings.updateUserFailed'));
    await loadUsersData();
  }
}

async function resetPassword(user: WebUIUser) {
  resettingUserId.value = user.user_id;
  try {
    const res = await axios.post('/api/webui/users/update', {
      user_id: user.user_id,
      reset_password: true,
    });
    generatedPassword.value = {
      username: user.username,
      password: res.data.data.new_password,
    };
  } catch (error: any) {
    toast.error(error?.response?.data?.message || tm('settings.resetPasswordFailed'));
  } finally {
    resettingUserId.value = '';
  }
}

async function deleteUser(user: WebUIUser) {
  deletingUserId.value = user.user_id;
  try {
    await axios.post('/api/webui/users/delete', { user_id: user.user_id });
    users.value = users.value.filter((item) => item.user_id !== user.user_id);
    if (selectedUserId.value === user.user_id) {
      selectedUserId.value = '';
    }
  } catch (error: any) {
    toast.error(error?.response?.data?.message || tm('settings.deleteUserFailed'));
  } finally {
    deletingUserId.value = '';
  }
}

async function copyPassword(password: string) {
  try {
    await navigator.clipboard.writeText(password);
    toast.success(tm('settings.passwordCopied'));
  } catch {
    toast.error(tm('settings.copyPasswordFailed'));
  }
}

watch(dialog, (open) => {
  if (!open) {
    generatedPassword.value = null;
    return;
  }
  if (activePanel.value === 'users') {
    loadUsersData();
  }
});

watch(activePanel, (panel) => {
  if (panel === 'users') {
    loadUsersData();
  }
});

watch(isAdmin, (admin) => {
  if (!admin && activePanel.value === 'users') {
    activePanel.value = 'basic';
  }
});
</script>

<style scoped>
.settings-card {
  border-radius: 28px !important;
  min-height: 560px;
  overflow: hidden;
}

.close-btn {
  height: 32px !important;
  left: 22px;
  min-width: 32px !important;
  position: absolute;
  top: 20px;
  width: 32px !important;
  z-index: 2;
}

.settings-shell {
  display: grid;
  grid-template-columns: 210px 1fr;
  min-height: 560px;
}

.settings-nav {
  border-right: 1px solid rgba(var(--v-theme-on-surface), 0.1);
  padding: 72px 20px 20px;
}

.nav-item {
  align-items: center;
  background: transparent;
  border: 0;
  border-radius: 16px;
  color: inherit;
  cursor: pointer;
  display: flex;
  font: inherit;
  font-size: 0.92rem;
  gap: 10px;
  margin-bottom: 6px;
  padding: 8px 11px;
  text-align: left;
  width: 100%;
}

.nav-item:hover,
.nav-item.active {
  background: rgba(var(--v-theme-on-surface), 0.06);
}

:global(.v-theme--PurpleThemeDark) .nav-item:hover,
:global(.v-theme--PurpleThemeDark) .nav-item.active {
  background: rgba(255, 255, 255, 0.08);
}

.settings-content {
  padding: 30px 26px 26px;
}

.content-header {
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.1);
  margin-inline: -26px;
  padding-bottom: 14px;
  padding-inline: 26px;
}

.content-header h2 {
  font-size: 1.28rem;
  font-weight: 650;
  line-height: 1.2;
  margin: 0 0 6px;
}

.content-header p,
.section-copy p,
.setting-copy p,
.user-meta p {
  color: rgba(var(--v-theme-on-surface), 0.56);
  font-size: 0.9rem;
  margin: 0;
}

.settings-list {
  display: grid;
}

.setting-row {
  align-items: center;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.1);
  display: grid;
  gap: 16px;
  grid-template-columns: minmax(190px, 270px) minmax(260px, 1fr);
  margin-inline: -26px;
  padding: 14px 0;
  padding-inline: 26px;
}

.setting-copy h3,
.section-copy h3,
.user-meta h3 {
  font-size: 0.92rem;
  font-weight: 650;
  margin: 0 0 4px;
}

.setting-control {
  justify-self: end;
  max-width: 320px;
  width: 100%;
}

.setting-toggle {
  justify-self: end;
}

.setting-toggle {
  border-color: rgba(var(--v-theme-on-surface), 0.18) !important;
}

.setting-toggle :deep(.v-btn) {
  border-color: rgba(var(--v-theme-on-surface), 0.18) !important;
}

.language-flag {
  display: inline-block;
  margin-right: 8px;
  width: 20px;
}

.password-alert {
  margin-top: 20px;
}

.password-alert-body {
  align-items: center;
  display: flex;
  gap: 18px;
  justify-content: space-between;
}

.password-alert-title {
  font-weight: 600;
  margin-bottom: 6px;
}

.password-alert code {
  background: rgba(var(--v-theme-surface), 0.75);
  border-radius: 8px;
  display: inline-block;
  font-size: 1rem;
  padding: 6px 10px;
}

.create-action-section {
  display: flex;
  justify-content: flex-start;
  padding: 20px 0;
}

.create-user-outline-btn {
  border-color: rgba(var(--v-theme-on-surface), 0.28) !important;
  border-radius: 999px !important;
  color: rgb(var(--v-theme-on-surface)) !important;
}

.create-user-outline-btn:hover {
  background: rgba(var(--v-theme-on-surface), 0.06) !important;
  border-color: rgba(var(--v-theme-on-surface), 0.54) !important;
}

.create-user-card {
  border-radius: 22px !important;
}

.create-user-title {
  align-items: center;
  display: flex;
  justify-content: space-between;
  padding: 18px 20px 8px;
}

.create-user-body {
  display: grid;
  gap: 14px;
  padding: 14px 20px 8px !important;
}

.create-user-actions {
  padding: 10px 20px 18px !important;
}

.user-list {
  display: grid;
}

.user-list-title {
  font-size: 0.92rem;
  font-weight: 650;
  margin: 16px 0 8px;
}

.user-list-item {
  align-items: center;
  background: transparent;
  border: 0;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.1);
  color: inherit;
  cursor: pointer;
  display: flex;
  font: inherit;
  gap: 14px;
  justify-content: space-between;
  margin-inline: -26px;
  min-height: 54px;
  padding: 0 26px;
  text-align: left;
}

.user-list-item:hover {
  background: rgba(var(--v-theme-on-surface), 0.04);
}

.user-list-name {
  flex: 1;
  font-weight: 400;
}

.user-list-avatar {
  background: rgba(var(--v-theme-on-surface), 0.08);
  color: rgb(var(--v-theme-on-surface));
  font-size: 0.78rem;
  font-weight: 650;
}

.user-list-arrow {
  color: rgba(var(--v-theme-on-surface), 0.42);
  font-size: 1.25rem;
  line-height: 1;
}

.user-status-chip {
  background: rgba(var(--v-theme-on-surface), 0.08) !important;
  color: rgba(var(--v-theme-on-surface), 0.72) !important;
  margin-left: auto;
}

.user-status-chip.is-disabled {
  background: rgba(var(--v-theme-on-surface), 0.04) !important;
  color: rgba(var(--v-theme-on-surface), 0.48) !important;
}

.user-detail-panel {
  padding-top: 16px;
}

.back-button {
  background: transparent;
  border: 0;
  border-radius: 999px;
  color: rgba(var(--v-theme-on-surface), 0.68);
  cursor: pointer;
  font: inherit;
  font-size: 0.88rem;
  margin: 0 0 12px;
  padding: 6px 0;
}

.back-button:hover {
  color: rgb(var(--v-theme-on-surface));
}

.user-detail-title {
  margin-bottom: 10px;
}

.user-detail-title h3 {
  font-size: 1.05rem;
  font-weight: 650;
  margin: 0;
}

.user-detail-row {
  align-items: center;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.1);
  display: grid;
  gap: 16px;
  grid-template-columns: minmax(190px, 240px) 1fr;
  margin-inline: -26px;
  padding: 14px 26px;
}

.detail-control {
  justify-self: end;
  max-width: 360px;
  width: 100%;
}

.user-detail-actions {
  display: flex;
  gap: 12px;
  justify-content: flex-start;
  padding-top: 18px;
}

.neutral-outline-btn {
  border-color: rgba(var(--v-theme-on-surface), 0.28) !important;
  color: rgb(var(--v-theme-on-surface)) !important;
}

.neutral-outline-btn:hover {
  background: rgba(var(--v-theme-on-surface), 0.06) !important;
  border-color: rgba(var(--v-theme-on-surface), 0.54) !important;
}

.empty-state {
  color: rgba(var(--v-theme-on-surface), 0.56);
  padding: 42px 0;
  text-align: center;
}

@media (max-width: 820px) {
  .settings-card {
    border-radius: 22px !important;
    min-height: 0;
  }

  .close-btn {
    left: 14px;
    top: 12px;
  }

  .settings-shell {
    display: block;
    min-height: 0;
  }

  .settings-nav {
    border-right: 0;
    display: flex;
    gap: 8px;
    padding: 58px 12px 0;
  }

  .nav-item {
    justify-content: center;
    margin-bottom: 0;
    padding: 8px 10px;
  }

  .settings-content {
    padding: 18px 14px 16px;
  }

  .content-header,
  .setting-row,
  .user-list-item,
  .user-detail-row {
    margin-inline: -14px;
    padding-inline: 14px;
  }

  .setting-row,
  .user-detail-row {
    grid-template-columns: 1fr;
  }

  .create-action-section {
    justify-content: flex-start;
  }

  .create-action-section .v-btn {
    width: auto;
  }

  .setting-control,
  .setting-toggle,
  .detail-control {
    justify-self: stretch;
  }

  .setting-toggle :deep(.v-btn) {
    flex: 1 1 0;
  }

  .password-alert-body {
    align-items: stretch;
    flex-direction: column;
  }

  .user-detail-actions {
    flex-direction: column;
  }
}
</style>
