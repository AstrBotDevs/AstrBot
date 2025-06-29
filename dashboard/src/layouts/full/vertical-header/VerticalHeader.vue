<script setup lang="ts">
import {ref, computed} from 'vue';
import {useCustomizerStore} from '@/stores/customizer';
import axios from 'axios';
import Logo from '@/components/shared/Logo.vue';
import LanguageSwitcher from '@/components/shared/LanguageSwitcher.vue';
import {md5} from 'js-md5';
import {useAuthStore} from '@/stores/auth';
import {useCommonStore} from '@/stores/common';
import {marked} from 'marked';
import { useI18n } from '@/i18n/composables';

const customizer = useCustomizerStore();
const { t } = useI18n();
let dialog = ref(false);
let accountWarning = ref(false)
let updateStatusDialog = ref(false);
const username = localStorage.getItem('user');
let password = ref('');
let newPassword = ref('');
let newUsername = ref('');
let status = ref('');
let updateStatus = ref('')
let releaseMessage = ref('');
let hasNewVersion = ref(false);
let botCurrVersion = ref('');
let dashboardHasNewVersion = ref(false);
let dashboardCurrentVersion = ref('');
let version = ref('');
let releases = ref([]);
let devCommits = ref([]);
let updatingDashboardLoading = ref(false);
let installLoading = ref(false);

let tab = ref(0);

const releasesHeader = computed(() => [
  {title: t('core.header.updateDialog.table.tag'), key: 'tag_name'},
  {title: t('core.header.updateDialog.table.publishDate'), key: 'published_at'},
  {title: t('core.header.updateDialog.table.content'), key: 'body'},
  {title: t('core.header.updateDialog.table.sourceUrl'), key: 'zipball_url'},
  {title: t('core.header.updateDialog.table.actions'), key: 'switch'}
]);

// Form validation
const formValid = ref(true);
const passwordRules = computed(() => [
  (v: string) => !!v || t('core.header.accountDialog.validation.passwordRequired'),
  (v: string) => v.length >= 8 || t('core.header.accountDialog.validation.passwordMinLength')
]);
const usernameRules = computed(() => [
  (v: string) => !v || v.length >= 3 || t('core.header.accountDialog.validation.usernameMinLength')
]);

// 显示密码相关
const showPassword = ref(false);
const showNewPassword = ref(false);

// 账户修改状态
const accountEditStatus = ref({
  loading: false,
  success: false,
  error: false,
  message: ''
});

const open = (link: string) => {
  window.open(link, '_blank');
};

// 账户修改
function accountEdit() {
  accountEditStatus.value.loading = true;
  accountEditStatus.value.error = false;
  accountEditStatus.value.success = false;

  // md5加密
  // @ts-ignore
  if (password.value != '') {
    password.value = md5(password.value);
  }
  if (newPassword.value != '') {
    newPassword.value = md5(newPassword.value);
  }
  axios.post('/api/auth/account/edit', {
    password: password.value,
    new_password: newPassword.value,
    new_username: newUsername.value ? newUsername.value : username
  })
      .then((res) => {
        if (res.data.status == 'error') {
          accountEditStatus.value.error = true;
          accountEditStatus.value.message = res.data.message;
          password.value = '';
          newPassword.value = '';
          return;
        }
        accountEditStatus.value.success = true;
        accountEditStatus.value.message = res.data.message;
        setTimeout(() => {
          dialog.value = !dialog.value;
          const authStore = useAuthStore();
          authStore.logout();
        }, 2000);
      })
      .catch((err) => {
        console.log(err);
        accountEditStatus.value.error = true;
        accountEditStatus.value.message = typeof err === 'string' ? err : t('core.header.accountDialog.messages.updateFailed');
        password.value = '';
        newPassword.value = '';
      })
      .finally(() => {
        accountEditStatus.value.loading = false;
      });
}

function getVersion() {
  axios.get('/api/stat/version')
      .then((res) => {
        botCurrVersion.value = "v" + res.data.data.version;
        dashboardCurrentVersion.value = res.data.data?.dashboard_version;
        let change_pwd_hint = res.data.data?.change_pwd_hint;
        if (change_pwd_hint) {
          dialog.value = true;
          accountWarning.value = true;
          localStorage.setItem('change_pwd_hint', 'true');
        } else {
          localStorage.removeItem('change_pwd_hint');
        }
      })
      .catch((err) => {
        console.log(err);
      });
}

function checkUpdate() {
  updateStatus.value = t('core.header.updateDialog.status.checking');
  axios.get('/api/update/check')
      .then((res) => {
        hasNewVersion.value = res.data.data.has_new_version;

        if (res.data.data.has_new_version) {
          releaseMessage.value = res.data.message;
          updateStatus.value = t('core.header.version.hasNewVersion');
        } else {
          updateStatus.value = res.data.message;
        }
        dashboardHasNewVersion.value = res.data.data.dashboard_has_new_version;
      })
      .catch((err) => {
        if (err.response && err.response.status == 401) {
          console.log("401");
          const authStore = useAuthStore();
          authStore.logout();
          return;
        }
        console.log(err);
        updateStatus.value = err
      });
}

function getReleases() {
  axios.get('/api/update/releases')
      .then((res) => {
        releases.value = res.data.data.map((item: any) => {
          item.published_at = new Date(item.published_at).toLocaleString();
          return item;
        })
      })
      .catch((err) => {
        console.log(err);
      });
}

function getDevCommits() {
  fetch('https://api.github.com/repos/Soulter/AstrBot/commits', {
    headers: {
      'Host': 'api.github.com',
      'Referer': 'https://api.github.com'
    }
  })
      .then(response => response.json())
      .then(data => {
        devCommits.value = data.map((commit: any) => ({
          sha: commit.sha,
          date: new Date(commit.commit.author.date).toLocaleString(),
          message: commit.commit.message
        }));
      })
      .catch(err => {
        console.log(err);
      });
}

function switchVersion(version: string) {
  updateStatus.value = t('core.header.updateDialog.status.switching');
  installLoading.value = true;
  axios.post('/api/update/do', {
    version: version,
    proxy: localStorage.getItem('selectedGitHubProxy') || ''
  })
      .then((res) => {
        updateStatus.value = res.data.message;
        if (res.data.status == 'ok') {
          setTimeout(() => {
            window.location.reload();
          }, 1000);
        }
      })
      .catch((err) => {
        console.log(err);
        updateStatus.value = err
      }).finally(() => {
    installLoading.value = false;
  });
}

function updateDashboard() {
  updatingDashboardLoading.value = true;
  updateStatus.value = t('core.header.updateDialog.status.updating');
  axios.post('/api/update/dashboard')
      .then((res) => {
        updateStatus.value = res.data.message;
        if (res.data.status == 'ok') {
          setTimeout(() => {
            window.location.reload();
          }, 1000);
        }
      })
      .catch((err) => {
        console.log(err);
        updateStatus.value = err
      }).finally(() => {
    updatingDashboardLoading.value = false;
  });
}

function toggleDarkMode() {
  customizer.SET_UI_THEME(customizer.uiTheme === 'PurpleThemeDark' ? 'PurpleTheme' : 'PurpleThemeDark');
}

getVersion();
checkUpdate();

const commonStore = useCommonStore();
commonStore.createEventSource(); // log
commonStore.getStartTime();

</script>

<template>
  <v-app-bar elevation="0" height="55">

    <v-btn v-if="useCustomizerStore().uiTheme==='PurpleTheme'" style="margin-left: 22px;" class="hidden-md-and-down text-secondary" color="lightsecondary" icon rounded="sm"
           variant="flat" @click.stop="customizer.SET_MINI_SIDEBAR(!customizer.mini_sidebar)" size="small">
      <v-icon>mdi-menu</v-icon>
    </v-btn>
    <v-btn v-else style="margin-left: 22px; color: var(--v-theme-primaryText); background-color: var(--v-theme-secondary)" class="hidden-md-and-down" icon rounded="sm"
           variant="flat" @click.stop="customizer.SET_MINI_SIDEBAR(!customizer.mini_sidebar)" size="small">
      <v-icon>mdi-menu</v-icon>
    </v-btn>
    <v-btn v-if="useCustomizerStore().uiTheme==='PurpleTheme'" class="hidden-lg-and-up ms-3" color="lightsecondary" icon rounded="sm" variant="flat"
           @click.stop="customizer.SET_SIDEBAR_DRAWER" size="small">
      <v-icon>mdi-menu</v-icon>
    </v-btn>
    <v-btn v-else class="hidden-lg-and-up ms-3" icon rounded="sm" variant="flat"
           @click.stop="customizer.SET_SIDEBAR_DRAWER" size="small">
      <v-icon>mdi-menu</v-icon>
    </v-btn>

    <div class="logo-container" :class="{'mobile-logo': $vuetify.display.xs}">
      <span class="logo-text">Astr<span class="logo-text-light">Bot</span></span>
      <span class="version-text hidden-xs">{{ botCurrVersion }}</span>
    </div>

    <v-spacer/>

    <!-- 版本提示信息 - 在手机上隐藏 -->
    <div class="mr-4 hidden-xs">
      <small v-if="hasNewVersion">
        {{ t('core.header.version.hasNewVersion') }}
      </small>
      <small v-else-if="dashboardHasNewVersion">
        {{ t('core.header.version.dashboardHasNewVersion') }}
      </small>
    </div>

    <!-- 语言切换器 -->
    <LanguageSwitcher variant="header" />

    <!-- 主题切换按钮 -->
    <v-btn size="small" @click="toggleDarkMode();" class="action-btn" 
           color="var(--v-theme-surface)" variant="flat" rounded="sm">
      <v-icon v-if="useCustomizerStore().uiTheme === 'PurpleThemeDark'">mdi-weather-night</v-icon>
      <v-icon v-else>mdi-white-balance-sunny</v-icon>
    </v-btn>

    <!-- 更新对话框 -->
    <v-dialog v-model="updateStatusDialog" :width="$vuetify.display.smAndDown ? '100%' : '1000'" :fullscreen="$vuetify.display.xs">
      <template v-slot:activator="{ props }">
        <v-btn size="small" @click="checkUpdate(); getReleases(); getDevCommits();" class="action-btn"
               color="var(--v-theme-surface)" variant="flat" rounded="sm" v-bind="props">
          <v-icon class="hidden-sm-and-up">mdi-update</v-icon>
          <span class="hidden-xs">{{ t('core.header.buttons.update') }}</span>
        </v-btn>
      </template>
      <v-card>
        <v-card-title class="mobile-card-title">
          <span class="text-h5">{{ t('core.header.updateDialog.title') }}</span>
          <v-btn v-if="$vuetify.display.xs" icon @click="updateStatusDialog = false">
            <v-icon>mdi-close</v-icon>
          </v-btn>
        </v-card-title>
        <v-card-text>
          <v-container>
            <v-progress-linear v-show="installLoading" class="mb-4" indeterminate color="primary"></v-progress-linear>

            <div>
              <h1 style="display:inline-block;">{{ botCurrVersion }}</h1>
              <small style="margin-left: 4px;">{{ updateStatus }}</small>
            </div>

            <div v-if="releaseMessage"
                style="background-color: #646cff24; padding: 16px; border-radius: 10px; font-size: 14px; max-height: 400px; overflow-y: auto;"
                v-html="marked(releaseMessage)" class="markdown-content">
            </div>

            <div class="mb-4 mt-4">
              <small>{{ t('core.header.updateDialog.tip') }} <a
                  href="https://github.com/Soulter/AstrBot/releases">{{ t('core.header.updateDialog.tipLink') }}</a>
                {{ t('core.header.updateDialog.tipContinue') }}</small>
            </div>

            <v-tabs v-model="tab">
              <v-tab value="0">{{ t('core.header.updateDialog.tabs.release') }}</v-tab>
              <v-tab value="1">{{ t('core.header.updateDialog.tabs.dev') }}</v-tab>
            </v-tabs>
            <v-tabs-window v-model="tab">

              <!-- 发行版 -->
              <v-tabs-window-item key="0" v-show="tab == 0">
                <v-btn class="mt-4 mb-4" @click="switchVersion('latest')" color="primary" style="border-radius: 10px;"
                       :disabled="!hasNewVersion">
                  {{ t('core.header.updateDialog.updateToLatest') }}
                </v-btn>
                <div class="mb-4">
                  <small>{{ t('core.header.updateDialog.dockerTip') }} <a
                        href="https://containrrr.dev/watchtower/usage-overview/">{{ t('core.header.updateDialog.dockerTipLink') }}</a> {{ t('core.header.updateDialog.dockerTipContinue') }}</small>
                </div>

                <v-data-table :headers="releasesHeader" :items="releases" item-key="name">
                  <template v-slot:item.body="{ item }: { item: { body: string } }">
                    <v-tooltip :text="item.body">
                      <template v-slot:activator="{ props }">
                        <v-btn v-bind="props" rounded="xl" variant="tonal" color="primary" size="small">{{ t('core.header.updateDialog.table.view') }}</v-btn>
                      </template>
                    </v-tooltip>
                  </template>
                  <template v-slot:item.switch="{ item }: { item: { tag_name: string } }">
                    <v-btn @click="switchVersion(item.tag_name)" rounded="xl" variant="plain" color="primary">
                      {{ t('core.header.updateDialog.table.switch') }}
                    </v-btn>
                  </template>
                </v-data-table>
              </v-tabs-window-item>

              <!-- 开发版 -->
              <v-tabs-window-item key="1" v-show="tab == 1">
                <div style="margin-top: 16px;">
                  <v-data-table
                      :headers="[
                        { title: t('core.header.updateDialog.table.sha'), key: 'sha' }, 
                        { title: t('core.header.updateDialog.table.date'), key: 'date' }, 
                        { title: t('core.header.updateDialog.table.message'), key: 'message' }, 
                        { title: t('core.header.updateDialog.table.actions'), key: 'switch' }
                      ]"
                      :items="devCommits" item-key="sha">
                    <template v-slot:item.switch="{ item }: { item: { sha: string } }">
                      <v-btn @click="switchVersion(item.sha)" rounded="xl" variant="plain" color="primary">
                        {{ t('core.header.updateDialog.table.switch') }}
                      </v-btn>
                    </template>
                  </v-data-table>
                </div>
              </v-tabs-window-item>

            </v-tabs-window>

            <h3 class="mb-4">{{ t('core.header.updateDialog.manualInput.title') }}</h3>

            <v-text-field :label="t('core.header.updateDialog.manualInput.placeholder')" v-model="version" required
                          variant="outlined"></v-text-field>
            <div class="mb-4">
              <small>{{ t('core.header.updateDialog.manualInput.hint') }}</small>
              <br>
              <a href="https://github.com/Soulter/AstrBot/commits/master"><small>{{ t('core.header.updateDialog.manualInput.linkText') }}</small></a>
            </div>
            <v-btn color="error" style="border-radius: 10px;" @click="switchVersion(version)">
              {{ t('core.header.updateDialog.manualInput.confirm') }}
            </v-btn>

            <v-divider class="mt-4 mb-4"></v-divider>
            <div style="margin-top: 16px;">
              <h3 class="mb-4">{{ t('core.header.updateDialog.dashboardUpdate.title') }}</h3>
              <div class="mb-4">
                <small>{{ t('core.header.updateDialog.dashboardUpdate.currentVersion') }} {{ dashboardCurrentVersion }}</small>
                <br>

              </div>

              <div class="mb-4">
                <p v-if="dashboardHasNewVersion">
                  {{ t('core.header.updateDialog.dashboardUpdate.hasNewVersion') }}
                </p>
                <p v-else="dashboardHasNewVersion">
                  {{ t('core.header.updateDialog.dashboardUpdate.isLatest') }}
                </p>
              </div>

              <v-btn color="primary" style="border-radius: 10px;" @click="updateDashboard()"
                     :disabled="!dashboardHasNewVersion" :loading="updatingDashboardLoading">
                {{ t('core.header.updateDialog.dashboardUpdate.downloadAndUpdate') }}
              </v-btn>
            </div>
          </v-container>
        </v-card-text>
        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn color="blue-darken-1" variant="text" @click="updateStatusDialog = false">
            {{ t('core.common.close') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 账户对话框 -->
    <v-dialog v-model="dialog" persistent :max-width="$vuetify.display.xs ? '90%' : '500'">
      <template v-slot:activator="{ props }">
        <v-btn size="small" class="action-btn mr-4" color="var(--v-theme-surface)" variant="flat" rounded="sm" v-bind="props">
          <v-icon>mdi-account</v-icon>
          <span class="hidden-xs ml-1">{{ t('core.header.buttons.account') }}</span>
        </v-btn>
      </template>
      <v-card class="account-dialog">
        <v-card-text class="py-6">
          <div class="d-flex flex-column align-center mb-6">
            <logo :title="t('core.header.logoTitle')" :subtitle="t('core.header.accountDialog.title')"></logo>
          </div>
          <v-alert 
            v-if="accountWarning" 
            type="warning"
            variant="tonal"
            border="start"
            class="mb-4"
          >
            <strong>{{ t('core.header.accountDialog.securityWarning') }}</strong>
          </v-alert>

          <v-alert
            v-if="accountEditStatus.success"
            type="success"
            variant="tonal"
            border="start"
            class="mb-4"
          >
            {{ accountEditStatus.message }}
          </v-alert>

          <v-alert
            v-if="accountEditStatus.error"
            type="error"
            variant="tonal"
            border="start"
            class="mb-4"
          >
            {{ accountEditStatus.message }}
          </v-alert>

          <v-form v-model="formValid" @submit.prevent="accountEdit">
            <v-text-field
              v-model="password"
              :append-inner-icon="showPassword ? 'mdi-eye-off' : 'mdi-eye'"
              :type="showPassword ? 'text' : 'password'"
              :label="t('core.header.accountDialog.form.currentPassword')"
              variant="outlined"
              required
              clearable
              @click:append-inner="showPassword = !showPassword"
              prepend-inner-icon="mdi-lock-outline"
              hide-details="auto"
              class="mb-4"
            ></v-text-field>

            <v-text-field
              v-model="newPassword"
              :append-inner-icon="showNewPassword ? 'mdi-eye-off' : 'mdi-eye'"
              :type="showNewPassword ? 'text' : 'password'"
              :rules="passwordRules"
              :label="t('core.header.accountDialog.form.newPassword')"
              variant="outlined"
              required
              clearable
              @click:append-inner="showNewPassword = !showNewPassword"
              prepend-inner-icon="mdi-lock-plus-outline"
              :hint="t('core.header.accountDialog.form.passwordHint')"
              persistent-hint
              class="mb-4"
            ></v-text-field>

            <v-text-field
              v-model="newUsername"
              :rules="usernameRules"
              :label="t('core.header.accountDialog.form.newUsername')"
              variant="outlined"
              clearable
              prepend-inner-icon="mdi-account-edit-outline"
              :hint="t('core.header.accountDialog.form.usernameHint')"
              persistent-hint
              class="mb-3"
            ></v-text-field>
          </v-form>
          
          <div class="text-caption text-medium-emphasis mt-2">
            {{ t('core.header.accountDialog.form.defaultCredentials') }}
          </div>
        </v-card-text>
        
        <v-divider></v-divider>
        
        <v-card-actions class="pa-4">
          <v-spacer></v-spacer>
          <v-btn
            v-if="!accountWarning"
            variant="tonal"
            color="secondary"
            @click="dialog = false"
            :disabled="accountEditStatus.loading"
          >
            {{ t('core.header.accountDialog.actions.cancel') }}
          </v-btn>
          <v-btn
            color="primary"
            @click="accountEdit"
            :loading="accountEditStatus.loading"
            :disabled="!formValid"
            prepend-icon="mdi-content-save"
          >
            {{ t('core.header.accountDialog.actions.save') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-app-bar>
</template>

<style>
.markdown-content h1 {
  font-size: 1.3em;
}

.markdown-content ol {
  padding-left: 24px;
  /* Adds indentation to ordered lists */
  margin-top: 8px;
  margin-bottom: 8px;
}

.markdown-content ul {
  padding-left: 24px;
  /* Adds indentation to unordered lists */
  margin-top: 8px;
  margin-bottom: 8px;
}

.account-dialog .v-card-text {
  padding-top: 24px;
  padding-bottom: 24px;
}

.account-dialog .v-alert {
  margin-bottom: 20px;
}

.account-dialog .v-btn {
  text-transform: none;
  font-weight: 500;
  border-radius: 8px;
}

.account-dialog .v-avatar {
  transition: transform 0.3s ease;
}

.account-dialog .v-avatar:hover {
  transform: scale(1.05);
}

/* 响应式布局样式 */
.logo-container {
  margin-left: 16px; 
  display: flex; 
  align-items: center; 
  gap: 8px;
}

.mobile-logo {
  margin-left: 8px;
  gap: 4px;
}

.logo-text {
  font-size: 24px; 
  font-weight: 1000;
}

.logo-text-light {
  font-weight: normal;
}

.version-text {
  font-size: 12px; 
  color: var(--v-theme-secondaryText);
}

.action-btn {
  margin-right: 6px;
}

/* 移动端对话框标题样式 */
.mobile-card-title {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

/* 移动端样式优化 */
@media (max-width: 600px) {
  .logo-text {
    font-size: 20px;
  }
  
  .action-btn {
    margin-right: 4px;
    min-width: 32px !important;
    width: 32px;
  }

  .v-card-title {
    padding: 12px 16px;
  }
  
  .v-card-text {
    padding: 16px;
  }
  
  .v-tabs .v-tab {
    padding: 0 10px;
    font-size: 0.9rem;
  }
}
</style>