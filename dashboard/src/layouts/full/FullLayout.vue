<script setup lang="ts">
import { RouterView, useRoute } from 'vue-router';
import { ref, onMounted, computed, watch, defineAsyncComponent } from 'vue';
import VerticalSidebarVue from './vertical-sidebar/VerticalSidebar.vue';
import VerticalHeaderVue from './vertical-header/VerticalHeader.vue';
import { useCustomizerStore } from '@/stores/customizer';
import { useRouterLoadingStore } from '@/stores/routerLoading';
import { useCommonStore } from '@/stores/common';
import { useAppearanceStore } from '@/stores/appearance';
import { statsApi } from '@/api/v1';
import { useI18n } from '@/i18n/composables';
import DashboardWallpaperLayer from '@/components/appearance/DashboardWallpaperLayer.vue';

const FIRST_NOTICE_SEEN_KEY = 'astrbot:first_notice_seen:v1';
const ReadmeDialog = defineAsyncComponent(
  () => import('@/components/shared/ReadmeDialog.vue'),
);
const Chat = defineAsyncComponent(() => import('@/components/chat/Chat.vue'));

const customizer = useCustomizerStore();
const appearance = useAppearanceStore();
const commonStore = useCommonStore();
const { locale } = useI18n();
const route = useRoute();
const routerLoadingStore = useRouterLoadingStore();
const isCurrentChatRoute = computed(
  () => route.path === '/chat' || route.path.startsWith('/chat/'),
);
const shouldMountChat = ref(isCurrentChatRoute.value);

const showSidebar = computed(() => !isCurrentChatRoute.value);

const showFirstNoticeDialog = ref(false);

watch(isCurrentChatRoute, (isChatRoute) => {
  if (isChatRoute) {
    shouldMountChat.value = true;
  }
});

const maybeShowFirstNotice = async () => {
  if (localStorage.getItem(FIRST_NOTICE_SEEN_KEY) === '1') {
    return;
  }

  try {
    const response = await statsApi.firstNotice(locale.value);
    if (response.data.status !== 'ok') {
      return;
    }

    const content = response.data?.data?.content;
    if (typeof content === 'string' && content.trim().length > 0) {
      showFirstNoticeDialog.value = true;
      return;
    }

    localStorage.setItem(FIRST_NOTICE_SEEN_KEY, '1');
  } catch (error) {
    console.error('Failed to load first notice:', error);
  }
};

const onFirstNoticeDialogUpdate = (visible: boolean) => {
  showFirstNoticeDialog.value = visible;
  if (!visible) {
    localStorage.setItem(FIRST_NOTICE_SEEN_KEY, '1');
  }
};

onMounted(() => {
  setTimeout(async () => {
    try {
      const response = await statsApi.version();
      if (response.data.status === 'ok') {
        commonStore.setAstrBotVersion(
          response.data.data?.version,
          response.data.data?.dashboard_version,
        );
      }
    } catch (error) {
      console.error('Failed to load version info:', error);
    }
    await maybeShowFirstNotice();
  }, 1000);
});
</script>

<template>
  <v-locale-provider>
    <v-app
      class="dashboard-app"
      :class="[
        customizer.mini_sidebar ? 'mini-sidebar' : '',
        customizer.inputBg ? 'inputWithbg' : '',
        appearance.active ? 'dashboard-appearance-active' : '',
      ]"
      :style="appearance.rootStyle"
    >
      <DashboardWallpaperLayer />
      <v-progress-linear
        v-if="routerLoadingStore.isLoading"
        :model-value="routerLoadingStore.progress"
        color="primary"
        height="2"
        fixed
        top
        class="router-progress"
      />
      <VerticalHeaderVue />
      <VerticalSidebarVue v-if="showSidebar" />
      <v-main
        class="dashboard-main"
        :class="{ 'dashboard-main--chat': isCurrentChatRoute }"
      >
        <v-container
          fluid
          class="page-wrapper"
          :class="{ 'chat-mode-container': isCurrentChatRoute }"
        >
          <div class="chat-layout-content">
            <div
              v-if="shouldMountChat"
              v-show="isCurrentChatRoute"
              class="chat-layout-panel"
            >
              <Chat :active="isCurrentChatRoute" />
            </div>
            <RouterView v-if="!isCurrentChatRoute" />
          </div>
        </v-container>
      </v-main>

      <ReadmeDialog
        :show="showFirstNoticeDialog"
        mode="first-notice"
        @update:show="onFirstNoticeDialogUpdate"
      />
    </v-app>
  </v-locale-provider>
</template>
