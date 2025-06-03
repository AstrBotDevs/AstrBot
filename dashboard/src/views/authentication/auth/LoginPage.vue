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
  background: linear-gradient(135deg, #ebf5fd 0%, #e0e9f8 100%);
  overflow: hidden;
}

.login-page-container-dark {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 100vh;
  width: 100%;
  position: relative;
  background: linear-gradient(135deg, #1a1b1c 0%, #1d1e21 100%);
  overflow: hidden;
}

.login-background {
  position: absolute;
  width: 200%;
  height: 200%;
  top: -50%;
  left: -50%;
  background: radial-gradient(circle, rgba(94, 53, 177, 0.03) 0%, rgba(30, 136, 229, 0.06) 70%);
  z-index: 0;
  animation: rotate 60s linear infinite;
}

.login-background-dark {
  position: absolute;
  width: 200%;
  height: 200%;
  top: -50%;
  left: -50%;
  background-color: var(--v-theme-surface);
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

.login-card {
  max-width: 520px;
  width: 90%;
  color: var(--v-theme-primaryText) !important;
  border-radius: 12px !important;
  border-color: var(--v-theme-border) !important;
  box-shadow: 0 8px 30px rgba(0, 0, 0, 0.07) !important;
  background-color: var(--v-theme-surface) !important;
  transform: translateY(20px);
  opacity: 0;
  transition: all 0.5s ease;
  z-index: 1;
  
  &.card-visible {
    transform: translateY(0);
    opacity: 1;
  }
}

.logo-wrapper {
  margin-bottom: 10px;
}

.divider-container {
  margin: 20px 0;
}

.custom-divider {
  border-color: rgba(0, 0, 0, 0.05) !important;
  opacity: 0.8;
}

.loginBox {
  max-width: 475px;
  margin: 0 auto;
}
</style>
