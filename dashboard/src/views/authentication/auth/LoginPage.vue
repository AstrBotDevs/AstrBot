<script setup lang="ts">
import AuthLogin from '../authForms/AuthLogin.vue';
import Logo from '@/components/shared/Logo.vue';
import LanguageSwitcher from '@/components/shared/LanguageSwitcher.vue';
import { onMounted, ref } from 'vue';
import { useAuthStore } from '@/stores/auth';
import { useRouter } from 'vue-router';
import {useCustomizerStore} from "@/stores/customizer";
import { useModuleI18n } from '@/i18n/composables';

const cardVisible = ref(false);
const router = useRouter();
const authStore = useAuthStore();
const customizer = useCustomizerStore();
const { tm: t } = useModuleI18n('features/auth');

// 主题切换函数
function toggleTheme() {
  customizer.SET_UI_THEME(
    customizer.uiTheme === 'PurpleThemeDark' ? 'PurpleTheme' : 'PurpleThemeDark'
  );
}

onMounted(() => {
  // 检查用户是否已登录，如果已登录则重定向
  if (authStore.has_token()) {
    router.push(authStore.returnUrl || '/');
    return;
  }
  
  // 添加一个小延迟以获得更好的动画效果
  setTimeout(() => {
    cardVisible.value = true;
  }, 100);
});
</script>

<template>
  <div v-if="useCustomizerStore().uiTheme==='PurpleTheme'" class="login-page-container">
    <div class="login-background"></div>
    
    <div class="login-container">
      <!-- 桌面端：卡片样式 -->
      <v-card 
        v-if="!$vuetify.display.xs"
        variant="outlined" 
        class="login-card" 
        :class="{ 'card-visible': cardVisible }"
      >
        <v-card-text class="pa-10">
          <div class="logo-wrapper">
            <Logo :title="t('logo.title')" :subtitle="t('logo.subtitle')" />
          </div>
          <div class="divider-container">
            <v-divider class="custom-divider"></v-divider>
          </div>
          <AuthLogin />
        </v-card-text>
      </v-card>
      
      <!-- 移动端：全屏样式 -->
      <div 
        v-else
        class="mobile-login-container"
        :class="{ 'mobile-visible': cardVisible }"
      >
        <div class="mobile-content">
          <div class="logo-wrapper">
            <Logo :title="t('logo.title')" :subtitle="t('logo.subtitle')" />
          </div>
          <div class="divider-container">
            <v-divider class="custom-divider"></v-divider>
          </div>
          <AuthLogin />
        </div>
      </div>
      
      <!-- 悬浮式圆角工具栏 -->
      <v-card 
        class="floating-toolbar" 
        :class="{ 'toolbar-visible': cardVisible }"
        elevation="8" 
        rounded="xl"
      >
        <v-card-text class="pa-2">
          <div class="d-flex align-center gap-1">
            <LanguageSwitcher />
            <v-divider vertical class="mx-1" style="height: 24px !important; opacity: 0.7 !important; align-self: center !important; border-color: rgba(94, 53, 177, 0.4) !important;"></v-divider>
            <v-btn
              @click="toggleTheme"
              class="theme-toggle-btn"
              icon
              variant="text"
              size="small"
            >
              <v-icon 
                size="18" 
                :color="useCustomizerStore().uiTheme === 'PurpleTheme' ? '#5e35b1' : '#d7c5fa'"
              >
                mdi-weather-night
              </v-icon>
              <v-tooltip activator="parent" location="top">
                {{ t('theme.switchToDark') }}
              </v-tooltip>
            </v-btn>
          </div>
        </v-card-text>
      </v-card>
    </div>
  </div>
  <div v-else class="login-page-container-dark">
    <div class="login-background-dark"></div>
    
    <div class="login-container">
      <!-- 桌面端：卡片样式 -->
      <v-card
        v-if="!$vuetify.display.xs"
        variant="outlined"
        class="login-card"
        :class="{ 'card-visible': cardVisible }"
      >
        <v-card-text class="pa-10">
          <div class="logo-wrapper">
            <Logo :title="t('logo.title')" :subtitle="t('logo.subtitle')" />
          </div>
          <div class="divider-container">
            <v-divider class="custom-divider"></v-divider>
          </div>
          <AuthLogin />
        </v-card-text>
      </v-card>
      
      <!-- 移动端：全屏样式 -->
      <div 
        v-else
        class="mobile-login-container"
        :class="{ 'mobile-visible': cardVisible }"
      >
        <div class="mobile-content">
          <div class="logo-wrapper">
            <Logo :title="t('logo.title')" :subtitle="t('logo.subtitle')" />
          </div>
          <div class="divider-container">
            <v-divider class="custom-divider"></v-divider>
          </div>
          <AuthLogin />
        </div>
      </div>
      
      <!-- 悬浮式圆角工具栏 -->
      <v-card 
        class="floating-toolbar" 
        :class="{ 'toolbar-visible': cardVisible }"
        elevation="8" 
        rounded="xl"
      >
        <v-card-text class="pa-2">
          <div class="d-flex align-center gap-1">
            <LanguageSwitcher />
            <v-divider vertical class="mx-1" style="height: 24px !important; opacity: 0.9 !important; align-self: center !important; border-color: rgba(180, 148, 246, 0.8) !important;"></v-divider>
            <v-btn
              @click="toggleTheme"
              class="theme-toggle-btn"
              icon
              variant="text"
              size="small"
            >
              <v-icon 
                size="18" 
                :color="useCustomizerStore().uiTheme === 'PurpleTheme' ? '#5e35b1' : '#d7c5fa'"
              >
                mdi-white-balance-sunny
              </v-icon>
              <v-tooltip activator="parent" location="top">
                {{ t('theme.switchToLight') }}
              </v-tooltip>
            </v-btn>
          </div>
        </v-card-text>
      </v-card>
    </div>
  </div>
</template>

<style lang="scss">
.login-page-container {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 100vh;
  width: 100%;
  position: relative;
  background: 
    linear-gradient(-45deg, 
      #faf9f7 0%, 
      #f9f2f1 25%, 
      #f1f9f9 50%, 
      #f9f3f7 75%, 
      #faf9f7 100%
    );
  background-size: 400% 400%;
  animation: gradientShift 15s ease infinite;
  overflow: hidden;
}

.login-page-container-dark {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 100vh;
  width: 100%;
  position: relative;
  background: 
    linear-gradient(-45deg, 
      #1e1f21 0%, 
      #221e25 25%, 
      #1e2225 50%, 
      #221f23 75%, 
      #1e1f21 100%
    );
  background-size: 400% 400%;
  animation: gradientShift 15s ease infinite;
  overflow: hidden;
}

@keyframes gradientShift {
  0% {
    background-position: 0% 50%;
  }
  50% {
    background-position: 100% 50%;
  }
  100% {
    background-position: 0% 50%;
  }
}

.login-background {
  position: absolute;
  width: 200%;
  height: 200%;
  top: -50%;
  left: -50%;
  background: radial-gradient(circle, rgba(94, 53, 177, 0.02) 0%, rgba(94, 53, 177, 0.03) 70%);
  z-index: 0;
  animation: rotate 60s linear infinite;
}

.login-background-dark {
  position: absolute;
  width: 200%;
  height: 200%;
  top: -50%;
  left: -50%;
  background: radial-gradient(circle, rgba(114, 46, 209, 0.03) 0%, rgba(114, 46, 209, 0.04) 70%);
  z-index: 0;
  animation: rotate 60s linear infinite;
}

@keyframes rotate {
  0% {
    transform: rotate(0deg);
  }
  100% {
    transform: rotate(360deg);
  }
}

.login-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 20px;
}

.floating-toolbar {
  background: #f8f6fc !important;
  border: 1px solid rgba(94, 53, 177, 0.15) !important;
  box-shadow: 0 8px 30px rgba(0, 0, 0, 0.08) !important;
  backdrop-filter: blur(10px);
  transform: translateY(20px);
  opacity: 0;
  transition: transform 0.6s ease 0.2s, opacity 0.6s ease 0.2s, border-color 0.3s ease, box-shadow 0.3s ease;
  min-width: auto !important;
  width: fit-content;
  
  &.toolbar-visible {
    transform: translateY(0);
    opacity: 1;
  }
  
  &:hover {
    transform: translateY(-2px);
    border-color: rgba(158, 126, 222, 0.99) !important;
    box-shadow: 0 12px 40px rgba(175, 145, 230, 0.741) !important;
  }
}

.login-page-container-dark .floating-toolbar {
  background: #2a2733 !important;
  border: 1px solid rgba(110, 60, 180, 0.692) !important;
  box-shadow: 0 8px 30px rgba(0, 0, 0, 0.3) !important;
  
  &:hover {
    border-color: rgba(160, 118, 219, 0.782) !important;
    box-shadow: 0 12px 40px rgba(99, 44, 175, 0.462) !important;
  }
}

.theme-toggle-btn {
  transition: all 0.3s ease;
  border-radius: 50% !important;
  min-width: 32px !important;
  width: 32px !important;
  height: 32px !important;
  
  &:hover {
    transform: scale(1.05);
    background: rgba(94, 53, 177, 0.08) !important;
  }
}

.login-page-container-dark .theme-toggle-btn:hover {
  background: rgba(114, 46, 209, 0.12) !important;
}

.login-card {
  max-width: 520px;
  width: 90%;
  position: relative;
  color: var(--v-theme-primaryText) !important;
  border-radius: 16px !important;
  border: 1px solid rgba(94, 53, 177, 0.15) !important;
  box-shadow: 0 8px 30px rgba(0, 0, 0, 0.08) !important;
  background: #f8f6fc !important;
  backdrop-filter: blur(10px);
  transform: translateY(20px);
  opacity: 0;
  transition: transform 0.5s ease, opacity 0.5s ease, border-color 0.3s ease, box-shadow 0.3s ease;
  z-index: 1;
  
  &::before {
    content: '';
    position: absolute;
    top: 50%;
    left: 50%;
    width: calc(100% + 4px);
    height: calc(100% + 4px);
    transform: translate(-50%, -50%);
    border-radius: 18px;
    border: 2px solid rgba(94, 53, 177, 0);
    transition: border-color 0.3s ease;
    pointer-events: none;
    z-index: -1;
  }
  
  &.card-visible {
    transform: translateY(0);
    opacity: 1;
  }
  
  &:hover {
    border-color: rgba(158, 126, 222, 0.99) !important;
    box-shadow: 0 12px 40px rgba(175, 145, 230, 0.741) !important;
    transform: translateY(-2px);
    
    &::before {
      border-color: rgba(156, 114, 239, 0.907);
    }
  }
}

.login-page-container-dark .login-card {
  border: 1px solid rgba(110, 60, 180, 0.692) !important;
  box-shadow: 0 8px 30px rgba(0, 0, 0, 0.3) !important;
  background: #2a2733 !important;
  
  &::before {
    border: 2px solid rgba(114, 46, 209, 0);
  }
  
  &:hover {
    border-color: rgba(160, 118, 219, 0.782) !important;
    box-shadow: 0 12px 40px rgba(99, 44, 175, 0.462) !important;
    transform: translateY(-2px);
    
    &::before {
      border-color: rgba(114, 46, 209, 0.15);
    }
  }
}

.logo-wrapper {
  margin-bottom: 10px;
}

.divider-container {
  margin: 20px 0;
}

.custom-divider {
  border-color: rgba(94, 53, 177, 0.3) !important;
  opacity: 1;
}

.login-page-container-dark .custom-divider {
  border-color: rgba(180, 148, 246, 0.4) !important;
}

.loginBox {
  max-width: 475px;
  margin: 0 auto;
}

/* 移动端全屏登录样式 */
.mobile-login-container {
  width: 100%;
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
  box-sizing: border-box;
  transform: translateY(20px);
  opacity: 0;
  transition: transform 0.5s ease, opacity 0.5s ease;
  z-index: 1;
  
  &.mobile-visible {
    transform: translateY(0);
    opacity: 1;
  }
}

.mobile-content {
  width: 100%;
  max-width: 400px;
  padding: 40px 20px;
}

/* 移动端调整工具栏位置 */
@media (max-width: 599px) {
  .floating-toolbar {
    position: fixed;
    bottom: 30px;
    left: 50%;
    transform: translateX(-50%) translateY(20px);
    z-index: 1000;
    
    &.toolbar-visible {
      transform: translateX(-50%) translateY(0);
    }
    
    &:hover {
      transform: translateX(-50%) translateY(-2px);
    }
  }
  
  .login-container {
    gap: 0;
  }
}
</style>
