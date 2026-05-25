<script setup lang="ts">
import { RouterView, useRoute } from 'vue-router';
import { ref, onMounted, computed } from 'vue';
import axios from 'axios';
import VerticalSidebarVue from './vertical-sidebar/VerticalSidebar.vue';
import VerticalHeaderVue from './vertical-header/VerticalHeader.vue';
import MigrationDialog from '@/components/shared/MigrationDialog.vue';
import ReadmeDialog from '@/components/shared/ReadmeDialog.vue';
import Chat from '@/components/chat/Chat.vue';
import { useCustomizerStore } from '@/stores/customizer';
import { useRouterLoadingStore } from '@/stores/routerLoading';
import { useI18n } from '@/i18n/composables';

const FIRST_NOTICE_SEEN_KEY = 'astrbot:first_notice_seen:v1';

const customizer = useCustomizerStore();
const { locale } = useI18n();
const route = useRoute();
const routerLoadingStore = useRouterLoadingStore();

const isChatPage = computed(() => {
  return route.path.startsWith('/chat');
});

const showSidebar = computed(() => {
  return customizer.viewMode === 'bot';
});

const showChatPage = computed(() => {
  return customizer.viewMode === 'chat';
});

const migrationDialog = ref<InstanceType<typeof MigrationDialog> | null>(null);
const showFirstNoticeDialog = ref(false);

const checkMigration = async (): Promise<boolean> => {
  try {
    const response = await axios.get('/api/stat/version');
    if (response.data.status === 'ok' && response.data.data.need_migration) {
      if (migrationDialog.value && typeof migrationDialog.value.open === 'function') {
        const result = await migrationDialog.value.open();
        if (result.success) {
          console.log('Migration completed successfully:', result.message);
          window.location.reload();
        }
      }
      return true;
    }
  } catch (error) {
    console.error('Failed to check migration status:', error);
  }
  return false;
};

const maybeShowFirstNotice = async () => {
  if (localStorage.getItem(FIRST_NOTICE_SEEN_KEY) === '1') {
    return;
  }

  try {
    const response = await axios.get('/api/stat/first-notice', {
      params: { locale: locale.value },
    });
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
    const migrationPending = await checkMigration();
    if (!migrationPending) {
      await maybeShowFirstNotice();
    }
  }, 1000);
});
</script>

<template>
  <v-locale-provider>
    <v-app :theme="useCustomizerStore().uiTheme"
      :class="[customizer.fontTheme, customizer.mini_sidebar ? 'mini-sidebar' : '', customizer.inputBg ? 'inputWithbg' : '']"
    >
      <v-progress-linear
        v-if="routerLoadingStore.isLoading"
        :model-value="routerLoadingStore.progress"
        color="primary"
        height="2"
        fixed
        top
        style="z-index: 9999; position: absolute; opacity: 0.3; "
      />
      <VerticalHeaderVue />
      <VerticalSidebarVue v-if="showSidebar" />
      <v-main :style="{
        height: showChatPage ? 'calc(100vh - 55px)' : undefined,
        overflow: showChatPage ? 'hidden' : undefined
      }">
        <v-container
          fluid
          class="page-wrapper"
          :class="{ 'chat-mode-container': showChatPage }"
          :style="{
            height: showChatPage ? '100%' : 'calc(100% - 8px)',
            padding: (isChatPage || showChatPage) ? '0' : undefined,
            minHeight: showChatPage ? 'unset' : undefined
          }">
          <div :style="{ height: '100%', width: '100%', overflow: showChatPage ? 'hidden' : undefined }">
            <div v-if="showChatPage" style="height: 100%; width: 100%; overflow: hidden;">
              <Chat />
            </div>
            <RouterView v-else />
          </div>
        </v-container>
      </v-main>

      <MigrationDialog ref="migrationDialog" />
      <ReadmeDialog
        :show="showFirstNoticeDialog"
        mode="first-notice"
        @update:show="onFirstNoticeDialogUpdate"
      />
    </v-app>
  </v-locale-provider>
</template>

<style scoped>
.chat-mode-container {
  min-height: unset !important;
  height: 100% !important;
  overflow: hidden !important;
}
</style>
