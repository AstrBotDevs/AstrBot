<script setup lang="ts">
import { ref, computed, watch, onMounted, defineAsyncComponent } from 'vue';
import { useCustomizerStore } from '@/stores/customizer';
import { useDisplay } from 'vuetify';
import Logo from '@/components/shared/Logo.vue';
import { useAuthStore } from '@/stores/auth';
import { useCommonStore } from '@/stores/common';
import { useI18n } from '@/i18n/composables';
import { router } from '@/router';
import { useRoute } from 'vue-router';
import StyledMenu from '@/components/shared/StyledMenu.vue';
import { useLanguageSwitcher } from '@/i18n/composables';
import type { Locale } from '@/i18n/types';
import { authApi, statsApi } from '@/api/v1';

const AboutPage = defineAsyncComponent(() => import('@/views/AboutPage.vue'));

const customizer = useCustomizerStore();
const { xs } = useDisplay();
const commonStore = useCommonStore();
const authStore = useAuthStore();
const { t } = useI18n();
const route = useRoute();
const LAST_BOT_ROUTE_KEY = 'astrbot:last_bot_route';
const LAST_CHAT_ROUTE_KEY = 'astrbot:last_chat_route';
let dialog = ref(false);
let accountWarning = ref(false);
let accountWarningMd5 = ref(false);
let accountWarningUpgrade = ref(false);
let aboutDialog = ref(false);
const username = localStorage.getItem('user');
let password = ref('');
let newPassword = ref('');
let confirmPassword = ref('');
let newUsername = ref('');
let botCurrVersion = ref('');
const isChatPath = computed(
  () => route.path === '/chat' || route.path.startsWith('/chat/'),
);
// Form validation
const formValid = ref(true);
const passwordRules = computed(() => [
  (v: string) =>
    Boolean(v) || t('core.header.accountDialog.validation.passwordRequired'),
  (v: string) =>
    v.length >= 8 ||
    t('core.header.accountDialog.validation.passwordMinLength'),
  (v: string) =>
    /[A-Z]/.test(v) ||
    t('core.header.accountDialog.validation.passwordUppercase'),
  (v: string) =>
    /[a-z]/.test(v) ||
    t('core.header.accountDialog.validation.passwordLowercase'),
  (v: string) =>
    /\d/.test(v) || t('core.header.accountDialog.validation.passwordDigit'),
]);
const confirmPasswordRules = computed(() => [
  (v: string) =>
    !newPassword.value ||
    Boolean(v) ||
    t('core.header.accountDialog.validation.passwordRequired'),
  (v: string) =>
    !newPassword.value ||
    v === newPassword.value ||
    t('core.header.accountDialog.validation.passwordMatch'),
]);
const usernameRules = computed(() => [
  (v: string) =>
    !v ||
    v.length >= 3 ||
    t('core.header.accountDialog.validation.usernameMinLength'),
]);

// 显示密码相关
const showPassword = ref(false);
const showNewPassword = ref(false);
const showConfirmPassword = ref(false);

// 账户修改状态
const accountEditStatus = ref({
  loading: false,
  success: false,
  error: false,
  message: '',
});

// 账户修改
function accountEdit() {
  accountEditStatus.value.loading = true;
  accountEditStatus.value.error = false;
  accountEditStatus.value.success = false;

  const currentPasswordValue = password.value ? password.value : '';
  const newPasswordValue = newPassword.value ? newPassword.value : '';
  const confirmPasswordValue = confirmPassword.value
    ? confirmPassword.value
    : '';

  authApi
    .updateAccount({
      password: currentPasswordValue,
      new_password: newPasswordValue,
      confirm_password: confirmPasswordValue,
      new_username: newUsername.value || username || undefined,
    })
    .then((res) => {
      if (res.data.status === 'error') {
        accountEditStatus.value.error = true;
        accountEditStatus.value.message = res.data.message || '';
        password.value = '';
        newPassword.value = '';
        confirmPassword.value = '';
        return;
      }
      accountEditStatus.value.success = true;
      accountEditStatus.value.message = res.data.message || '';
      setTimeout(() => {
        dialog.value = !dialog.value;
        authStore.logout();
      }, 2000);
    })
    .catch((err) => {
      console.log(err);
      accountEditStatus.value.error = true;
      accountEditStatus.value.message =
        typeof err === 'string'
          ? err
          : t('core.header.accountDialog.messages.updateFailed');
      password.value = '';
      newPassword.value = '';
      confirmPassword.value = '';
    })
    .finally(() => {
      accountEditStatus.value.loading = false;
    });
}

function getVersion() {
  statsApi
    .version()
    .then((res) => {
      const data = res.data?.status === 'error' ? null : res.data?.data;
      if (!data || typeof data !== 'object') return;
      botCurrVersion.value = `v${data.version || ''}`;
      commonStore.setAstrBotVersion(
        data.version || '',
        data.dashboard_version || undefined,
      );
      const change_pwd_hint = data.change_pwd_hint;
      const md5_pwd_hint = data.md5_pwd_hint;
      const password_upgrade_required = data.password_upgrade_required;
      if (change_pwd_hint || md5_pwd_hint || password_upgrade_required) {
        dialog.value = true;
        accountWarning.value = true;
        accountWarningUpgrade.value = Boolean(password_upgrade_required);
        accountWarningMd5.value =
          Boolean(md5_pwd_hint) && !password_upgrade_required;
        if (change_pwd_hint || (md5_pwd_hint && !password_upgrade_required)) {
          localStorage.setItem('change_pwd_hint', 'true');
        } else {
          localStorage.removeItem('change_pwd_hint');
        }
        if (md5_pwd_hint && !password_upgrade_required) {
          localStorage.setItem('md5_pwd_hint', 'true');
        } else {
          localStorage.removeItem('md5_pwd_hint');
        }
        if (password_upgrade_required) {
          localStorage.setItem('password_upgrade_required', 'true');
        } else {
          localStorage.removeItem('password_upgrade_required');
        }
      } else {
        accountWarningMd5.value = false;
        accountWarningUpgrade.value = false;
        localStorage.removeItem('change_pwd_hint');
        localStorage.removeItem('md5_pwd_hint');
        localStorage.removeItem('password_upgrade_required');
      }
    })
    .catch((err) => {
      console.log(err);
    });
}

function initPasswordWarningFromStorage() {
  const hasChangePwdHint = localStorage.getItem('change_pwd_hint') === 'true';
  const hasMd5PwdHint = localStorage.getItem('md5_pwd_hint') === 'true';
  const hasPasswordUpgradeRequired =
    localStorage.getItem('password_upgrade_required') === 'true';
  if (hasChangePwdHint || hasMd5PwdHint || hasPasswordUpgradeRequired) {
    dialog.value = true;
    accountWarning.value = true;
    accountWarningUpgrade.value = hasPasswordUpgradeRequired;
    accountWarningMd5.value = hasMd5PwdHint && !hasPasswordUpgradeRequired;
  }
}

// 主题选项配置
const themeOptions = [
  {
    mode: 'light' as const,
    icon: 'mdi-white-balance-sunny',
    labelKey: 'core.header.buttons.theme.light',
  },
  {
    mode: 'dark' as const,
    icon: 'mdi-weather-night',
    labelKey: 'core.header.buttons.theme.dark',
  },
  {
    mode: 'system' as const,
    icon: 'mdi-sync',
    labelKey: 'core.header.buttons.theme.system',
  },
] as const;

function setThemeMode(mode: 'light' | 'dark' | 'system') {
  customizer.SET_THEME_MODE(mode);
}

function handleLogoClick() {
  if (isChatPath.value) {
    aboutDialog.value = true;
  } else {
    void router.push('/about');
  }
}

getVersion();
initPasswordWarningFromStorage();

void commonStore.createEventSource(); // log
commonStore.getStartTime();

// 视图模式切换
onMounted(() => {
  // 初次加載時保存當前路由
  if (typeof window !== 'undefined') {
    if (isChatPath.value) {
      // 保存 chat ID
      const parts = route.fullPath.split('/');
      const sessionId = parts[2];
      if (sessionId) {
        sessionStorage.setItem(LAST_CHAT_ROUTE_KEY, sessionId);
        console.log('Initial save chat ID:', sessionId);
      }
    } else {
      // 保存 bot 路由（非 chat 頁面）
      sessionStorage.setItem(LAST_BOT_ROUTE_KEY, route.fullPath);
      console.log('Initial save bot route:', route.fullPath);
    }
  }
});

watch(
  () => route.fullPath,
  (newPath) => {
    if (typeof window === 'undefined') return;
    console.log('Route changed:', {
      newPath,
      isChat: isChatPath.value,
      currentChatId: route.params.id,
    });
    try {
      // 使用現有的 isChatPath 計算屬性來避免名稱衝突
      const isChat = isChatPath.value; // 這裡使用已經計算好的 isChatPath

      // ✅ bot：只存「非 chat 頁」
      if (!isChat) {
        sessionStorage.setItem(LAST_BOT_ROUTE_KEY, newPath);
      }

      // ✅ chat：只存 sessionId
      if (isChat) {
        const parts = newPath.split('/');
        const sessionId = parts[2];

        if (sessionId) {
          sessionStorage.setItem(LAST_CHAT_ROUTE_KEY, sessionId);
        }
      }
    } catch (e) {
      console.error('Failed to save route:', e);
    }
  },
);

const currentMode = computed({
  get: () => (isChatPath.value ? 'chat' : 'bot'),
  set: (val: 'chat' | 'bot') => {
    try {
      // 檢查 window 和 sessionStorage 是否存在
      if (
        typeof window === 'undefined' ||
        typeof sessionStorage === 'undefined'
      ) {
        // 如果在非瀏覽器環境中，不做任何 sessionStorage 操作
        console.warn('sessionStorage is not available in this environment');
        return;
      }

      if (val === 'chat') {
        const lastSessionId = sessionStorage.getItem(LAST_CHAT_ROUTE_KEY);
        void router.push(lastSessionId ? `/chat/${lastSessionId}` : '/chat');
      } else {
        let lastBotRoute = sessionStorage.getItem(LAST_BOT_ROUTE_KEY) || '/';
        if (lastBotRoute.startsWith('/chat')) {
          lastBotRoute = '/';
        }
        void router.push(lastBotRoute);
      }
    } catch (e) {
      // 在受限隱私模式等環境中，sessionStorage 操作可能會拋出 SecurityError
      console.warn('Failed to access sessionStorage in currentMode setter:', e);
    }
  },
});

// Merry Christmas! 🎄
const isChristmas = computed(() => {
  const today = new Date();
  const month = today.getMonth() + 1; // getMonth() 返回 0-11
  const day = today.getDate();
  return month === 12 && day === 25;
});

// 语言切换相关
const mainMenuOpen = ref(false);
const { languageOptions, currentLanguage, switchLanguage, locale } =
  useLanguageSwitcher();
const languages = computed(() =>
  languageOptions.value.map((lang) => ({
    code: lang.value,
    name: lang.label,
    flag: lang.flag,
  })),
);
const currentLocale = computed(() => locale.value);
const changeLanguage = async (langCode: string) => {
  await switchLanguage(langCode as Locale);
  mainMenuOpen.value = false;
};
</script>

<template>
  <v-app-bar elevation="0" height="50" class="top-header">
    <!-- 桌面端 menu 按钮 - 仅在 bot 模式下显示 -->
    <v-btn
      v-if="!isChatPath"
      class="top-header__menu-button hidden-md-and-down"
      icon
      rounded="sm"
      variant="flat"
      :aria-label="t('core.navigation.toggleSidebar')"
      :title="t('core.navigation.toggleSidebar')"
      @click.stop="customizer.SET_MINI_SIDEBAR(!customizer.mini_sidebar)"
    >
      <v-icon>mdi-menu</v-icon>
    </v-btn>

    <!-- 移动端 menu 按钮 -->
    <v-btn
      v-if="!isChatPath"
      class="top-header__menu-button--mobile hidden-lg-and-up ms-3"
      icon
      rounded="sm"
      variant="flat"
      :aria-label="t('core.navigation.toggleSidebar')"
      :title="t('core.navigation.toggleSidebar')"
      @click.stop="customizer.SET_SIDEBAR_DRAWER"
    >
      <v-icon>mdi-menu</v-icon>
    </v-btn>

    <v-btn
      v-if="isChatPath"
      class="hidden-lg-and-up ms-1"
      icon
      rounded="sm"
      variant="flat"
      :aria-label="t('core.navigation.toggleSidebar')"
      :title="t('core.navigation.toggleSidebar')"
      @click.stop="customizer.TOGGLE_CHAT_SIDEBAR()"
    >
      <v-icon>mdi-menu</v-icon>
    </v-btn>

    <div
      class="logo-container"
      :class="{
        'mobile-logo': xs,
        'chat-mode-logo': isChatPath,
      }"
      @click="handleLogoClick"
    >
      <span class="logo-text"
        >Astr<span class="logo-text bot-text-wrapper"
          >Bot
          <img
            v-if="isChristmas"
            src="@/assets/images/xmas-hat.png"
            alt="Christmas hat"
            class="xmas-hat"
          /> </span
      ></span>
      <span
        v-if="isChatPath"
        class="logo-text logo-text-light top-header__chat-label"
        >ChatUI</span
      >
      <span class="version-text hidden-xs">{{ botCurrVersion }}</span>
    </div>

    <v-spacer />

    <!-- Bot/Chat 模式切换按钮 - 手机端隐藏，移入 ... 菜单 -->
    <v-btn-toggle
      v-model="currentMode"
      mandatory
      variant="outlined"
      density="compact"
      class="mr-4 hidden-xs"
      color="primary"
    >
      <v-btn value="bot" size="small">
        <v-icon start>mdi-robot</v-icon>
        Bot
      </v-btn>
      <v-btn value="chat" size="small">
        <v-icon start>mdi-chat</v-icon>
        Chat
      </v-btn>
    </v-btn-toggle>

    <!-- 功能菜单 -->
    <StyledMenu v-model="mainMenuOpen" offset="12" location="bottom end">
      <template #activator="{ props: activatorProps }">
        <v-btn
          v-bind="activatorProps"
          size="small"
          class="action-btn mr-4"
          color="surface"
          variant="flat"
          rounded="sm"
          icon
        >
          <v-icon>mdi-dots-vertical</v-icon>
        </v-btn>
      </template>

      <!-- Bot/Chat 模式切换 - 仅在手机端显示 -->
      <template v-if="xs">
        <div class="mobile-mode-toggle-wrapper">
          <v-btn-toggle
            v-model="currentMode"
            mandatory
            variant="outlined"
            density="compact"
            class="mobile-mode-toggle"
            color="primary"
          >
            <v-btn value="bot" size="small">
              <v-icon start>mdi-robot</v-icon>
              Bot
            </v-btn>
            <v-btn value="chat" size="small">
              <v-icon start>mdi-chat</v-icon>
              Chat
            </v-btn>
          </v-btn-toggle>
        </div>
        <v-divider class="my-1" />
      </template>

      <!-- 语言切换分组 -->
      <v-menu
        open-on-click
        :open-on-hover="!xs"
        :open-delay="!xs ? 60 : 0"
        :close-delay="!xs ? 120 : 0"
        :location="xs ? 'bottom' : 'start center'"
        offset="8"
      >
        <template #activator="{ props: languageMenuProps }">
          <v-list-item
            v-bind="languageMenuProps"
            class="styled-menu-item language-group-trigger"
            rounded="md"
            @click.stop
          >
            <template #prepend>
              <v-icon>mdi-translate</v-icon>
            </template>
            <v-list-item-title>{{
              t('core.common.language')
            }}</v-list-item-title>
            <template #append>
              <span class="language-group-current">{{
                currentLanguage?.flag
              }}</span>
              <v-icon size="18" class="language-group-arrow"
                >mdi-chevron-right</v-icon
              >
            </template>
          </v-list-item>
        </template>

        <v-card
          class="styled-menu-card top-header__language-menu"
          elevation="4"
          rounded="md"
        >
          <v-list density="compact" class="styled-menu-list pa-1">
            <v-list-item
              v-for="lang in languages"
              :key="lang.code"
              :value="lang.code"
              :class="{
                'styled-menu-item-active': currentLocale === lang.code,
              }"
              class="styled-menu-item"
              rounded="md"
              @click="changeLanguage(lang.code)"
            >
              <template #prepend>
                <span class="language-flag">{{ lang.flag }}</span>
              </template>
              <v-list-item-title>{{ lang.name }}</v-list-item-title>
            </v-list-item>
          </v-list>
        </v-card>
      </v-menu>

      <!-- 主题切换分组 -->
      <v-menu
        open-on-click
        :open-on-hover="!xs"
        :open-delay="!xs ? 60 : 0"
        :close-delay="!xs ? 120 : 0"
        :location="xs ? 'bottom' : 'start center'"
        offset="8"
      >
        <template #activator="{ props: themeMenuProps }">
          <v-list-item
            v-bind="themeMenuProps"
            class="styled-menu-item theme-group-trigger"
            rounded="md"
            @click.stop
          >
            <template #prepend>
              <v-icon>mdi-brightness-6</v-icon>
            </template>
            <v-list-item-title>{{
              t('core.header.buttons.theme.title')
            }}</v-list-item-title>
            <template #append>
              <span class="theme-group-current">
                <v-icon size="16">{{
                  customizer.themeMode === 'dark'
                    ? 'mdi-weather-night'
                    : customizer.themeMode === 'system'
                      ? 'mdi-theme-light-dark'
                      : 'mdi-white-balance-sunny'
                }}</v-icon>
              </span>
              <v-icon size="18" class="language-group-arrow"
                >mdi-chevron-right</v-icon
              >
            </template>
          </v-list-item>
        </template>

        <v-card
          class="styled-menu-card top-header__theme-menu"
          elevation="4"
          rounded="md"
        >
          <v-list density="compact" class="styled-menu-list pa-1">
            <v-list-item
              v-for="option in themeOptions"
              :key="option.mode"
              :class="{
                'styled-menu-item-active': customizer.themeMode === option.mode,
              }"
              class="styled-menu-item"
              rounded="md"
              @click="setThemeMode(option.mode)"
            >
              <template #prepend>
                <v-icon size="18" class="theme-option-icon">{{
                  option.icon
                }}</v-icon>
              </template>
              <v-list-item-title>{{ t(option.labelKey) }}</v-list-item-title>
            </v-list-item>
          </v-list>
        </v-card>
      </v-menu>

      <!-- 账户按钮 -->
      <v-list-item class="styled-menu-item" rounded="md" @click="dialog = true">
        <template #prepend>
          <v-icon>mdi-account</v-icon>
        </template>
        <v-list-item-title>{{
          t('core.header.accountDialog.title')
        }}</v-list-item-title>
      </v-list-item>

      <v-divider class="my-1" />

      <v-list-item
        class="styled-menu-item text-error"
        prepend-icon="mdi-logout"
        rounded="md"
        @click="authStore.logout()"
      >
        <v-list-item-title>
          {{ t('core.header.buttons.logout') }}
        </v-list-item-title>
      </v-list-item>
    </StyledMenu>

    <!-- 账户对话框 -->
    <v-dialog v-model="dialog" persistent :max-width="xs ? '90%' : '500'">
      <v-card class="account-dialog">
        <v-card-text class="py-6">
          <div class="d-flex flex-column align-start mb-6">
            <logo
              :title="t('core.header.logoTitle')"
              :subtitle="t('core.header.accountDialog.title')"
            ></logo>
          </div>
          <v-alert
            v-if="accountWarning"
            type="warning"
            variant="tonal"
            border="start"
            class="mb-4"
          >
            <strong>{{
              t(
                accountWarningUpgrade
                  ? 'core.header.accountDialog.securityWarningUpgrade'
                  : accountWarningMd5
                    ? 'core.header.accountDialog.securityWarningMd5'
                    : 'core.header.accountDialog.securityWarning',
              )
            }}</strong>
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
              prepend-inner-icon="mdi-lock-outline"
              hide-details="auto"
              class="mb-4"
              @click:append-inner="showPassword = !showPassword"
            ></v-text-field>

            <v-text-field
              v-model="newPassword"
              :append-inner-icon="showNewPassword ? 'mdi-eye-off' : 'mdi-eye'"
              :type="showNewPassword ? 'text' : 'password'"
              :rules="passwordRules"
              :label="t('core.header.accountDialog.form.newPassword')"
              variant="outlined"
              clearable
              prepend-inner-icon="mdi-lock-plus-outline"
              :hint="t('core.header.accountDialog.form.passwordHint')"
              persistent-hint
              class="mb-4"
              @click:append-inner="showNewPassword = !showNewPassword"
            ></v-text-field>

            <v-text-field
              v-model="confirmPassword"
              :append-inner-icon="
                showConfirmPassword ? 'mdi-eye-off' : 'mdi-eye'
              "
              :type="showConfirmPassword ? 'text' : 'password'"
              :rules="confirmPasswordRules"
              :label="t('core.header.accountDialog.form.confirmPassword')"
              variant="outlined"
              clearable
              prepend-inner-icon="mdi-lock-check-outline"
              :hint="t('core.header.accountDialog.form.confirmPasswordHint')"
              persistent-hint
              class="mb-4"
              @click:append-inner="showConfirmPassword = !showConfirmPassword"
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

        <v-card-actions class="pa-4">
          <v-spacer></v-spacer>
          <v-btn
            v-if="!accountWarning"
            variant="tonal"
            color="secondary"
            :disabled="accountEditStatus.loading"
            @click="dialog = false"
          >
            {{ t('core.header.accountDialog.actions.cancel') }}
          </v-btn>
          <v-btn
            color="primary"
            :loading="accountEditStatus.loading"
            :disabled="!formValid"
            prepend-icon="mdi-content-save"
            @click="accountEdit"
          >
            {{ t('core.header.accountDialog.actions.save') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- About 对话框 - 仅在 chat mode 下使用 -->
    <v-dialog v-model="aboutDialog" width="600">
      <v-card class="app-dialog">
        <v-card-text class="top-header__about-content">
          <AboutPage />
        </v-card-text>
      </v-card>
    </v-dialog>
  </v-app-bar>
</template>

<style>
.top-header__menu-button {
  margin-left: var(--astrbot-space-4);
}

.top-header__chat-label {
  color: rgb(var(--v-theme-on-surface-variant));
}

.top-header__language-menu {
  min-width: 180px;
}

.top-header__theme-menu {
  min-width: 170px;
}

.top-header__about-content {
  overflow-y: auto;
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

.account-dialog-header {
  .theme-toggle-btn {
    opacity: 0.85;

    &:hover {
      opacity: 1;
    }
  }
}

.theme-toggle-btn {
  margin-left: 0;
}

.release-table-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.release-prerelease-switch {
  flex: 0 1 auto;
}

/* 响应式布局样式 */
.logo-container {
  margin-left: 10px;
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}

.mobile-logo {
  margin-left: 8px;
  gap: 4px;
}

.chat-mode-logo {
  margin-left: 22px;
}

.mobile-logo.chat-mode-logo {
  margin-left: 4px;
}

.logo-text {
  font-size: 24px;
  font-weight: 1000;
}

.logo-text-light {
  font-weight: normal;
}

.bot-text-wrapper {
  position: relative;
  display: inline-block;
}

.xmas-hat {
  position: absolute;
  top: -3px;
  right: -14px;
  width: 24px;
  height: 24px;
  z-index: 1;
}

.version-text {
  font-size: 12px;
  color: gray;
  margin-left: 4px;
}

.action-btn {
  margin-right: 6px;
}

.language-flag {
  font-size: 16px;
  margin-right: 8px;
}

.language-group-trigger .v-list-item__append {
  display: flex;
  align-items: center;
  gap: 6px;
}

.language-group-current {
  font-size: 16px;
  line-height: 1;
}

.language-group-arrow {
  opacity: 0.7;
}

.language-submenu-card {
  min-width: 180px;
}

.theme-group-trigger .v-list-item__append {
  display: flex;
  align-items: center;
  gap: 6px;
}

.theme-group-current {
  display: flex;
  align-items: center;
  opacity: 0.75;
}

.theme-option-icon {
  margin-right: 8px;
  opacity: 0.85;
}

.mobile-mode-toggle-wrapper {
  display: flex;
  justify-content: center;
  padding: 8px 12px 4px;
}

.mobile-mode-toggle {
  width: 100%;
}

.mobile-mode-toggle .v-btn {
  flex: 1;
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

  /* 移动端模式切换按钮样式 */
  .v-btn-toggle {
    margin-right: 8px;
  }

  .v-btn-toggle .v-btn {
    font-size: 0.75rem;
    padding: 0 8px;
  }

  .v-btn-toggle .v-icon {
    font-size: 16px;
  }
}
</style>
