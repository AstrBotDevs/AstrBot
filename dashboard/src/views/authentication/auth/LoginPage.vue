<script setup lang="ts">
import AuthLogin from '../authForms/AuthLogin.vue';
import Logo from '@/components/shared/Logo.vue';
import { onMounted, ref } from 'vue';
import { useAuthStore } from '@/stores/auth';
import { useRouter } from 'vue-router';
import {useCustomizerStore} from "@/stores/customizer";

const cardVisible = ref(false);
const router = useRouter();
const authStore = useAuthStore();
const customizer = useCustomizerStore();

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
    
    <!-- 主题切换按钮 -->
    <div class="theme-toggle-container">
      <v-btn
        @click="toggleTheme"
        class="theme-toggle-btn"
        icon
        variant="flat"
        size="small"
        color="primary"
        elevation="2"
      >
        <v-icon size="20">mdi-weather-night</v-icon>
        <v-tooltip activator="parent" location="left">
          切换到深色主题
        </v-tooltip>
      </v-btn>
    </div>
    
    <v-card 
      variant="outlined" 
      class="login-card" 
      :class="{ 'card-visible': cardVisible }"
    >
      <v-card-text class="pa-10">
        <div class="logo-wrapper">
          <Logo />
        </div>
        <div class="divider-container">
          <v-divider class="custom-divider"></v-divider>
        </div>
        <AuthLogin />
      </v-card-text>
    </v-card>
  </div>
  <div v-else class="login-page-container-dark">
    <div class="login-background-dark"></div>
    
    <!-- 主题切换按钮 -->
    <div class="theme-toggle-container">
      <v-btn
        @click="toggleTheme"
        class="theme-toggle-btn"
        icon
        variant="flat"
        size="small"
        color="secondary"
        elevation="2"
      >
        <v-icon size="20">mdi-white-balance-sunny</v-icon>
        <v-tooltip activator="parent" location="left">
          切换到浅色主题
        </v-tooltip>
      </v-btn>
    </div>
    
    <v-card
        variant="outlined"
        class="login-card"
        :class="{ 'card-visible': cardVisible }"
    >
      <v-card-text class="pa-10">
        <div class="logo-wrapper">
          <Logo />
        </div>
        <div class="divider-container">
          <v-divider class="custom-divider"></v-divider>
        </div>
        <AuthLogin />
      </v-card-text>
    </v-card>
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

.theme-toggle-container {
  position: absolute;
  top: 20px;
  right: 20px;
  z-index: 10;
}

.theme-toggle-btn {
  transition: all 0.3s ease;
  
  &:hover {
    transform: scale(1.1);
  }
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
  border-color: rgba(94, 53, 177, 0.1) !important;
  opacity: 1;
}

.login-page-container-dark .custom-divider {
  border-color: rgba(114, 46, 209, 0.08) !important;
}

.loginBox {
  max-width: 475px;
  margin: 0 auto;
}
</style>
