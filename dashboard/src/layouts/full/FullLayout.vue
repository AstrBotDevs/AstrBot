<script setup lang="ts">
import { RouterView, useRoute } from 'vue-router';
import { ref, onMounted, computed } from 'vue';
import axios from 'axios';
import VerticalSidebarVue from './vertical-sidebar/VerticalSidebar.vue';
import VerticalHeaderVue from './vertical-header/VerticalHeader.vue';
import MigrationDialog from '@/components/shared/MigrationDialog.vue';
import Chat from '@/components/chat/Chat.vue';
import { useCustomizerStore } from '@/stores/customizer';
import { useRouterLoadingStore } from '@/stores/routerLoading';

const customizer = useCustomizerStore();
const route = useRoute();
const routerLoadingStore = useRouterLoadingStore();

// 计算是否在聊天页面（非全屏模式）
const isChatPage = computed(() => {
  return route.path.startsWith('/chat');
});

// 计算是否显示 sidebar（仅在 bot 模式下显示）
const showSidebar = computed(() => {
  return customizer.viewMode === 'bot';
});

// 计算是否显示 chat 页面（在 chat 模式下显示）
const showChatPage = computed(() => {
  return customizer.viewMode === 'chat';
});

const migrationDialog = ref<InstanceType<typeof MigrationDialog> | null>(null);

// 检查是否需要迁移
const checkMigration = async () => {
  try {
    const response = await axios.get('/api/stat/version');
    if (response.data.status === 'ok' && response.data.data.need_migration) {
      // 需要迁移，显示迁移对话框
      if (migrationDialog.value && typeof migrationDialog.value.open === 'function') {
        const result = await migrationDialog.value.open();
        if (result.success) {
          // 迁移成功，可以显示成功消息
          console.log('Migration completed successfully:', result.message);
          // 可以考虑刷新页面或显示成功通知
          window.location.reload();
        }
      }
    }
  } catch (error) {
    console.error('Failed to check migration status:', error);
  }
};

onMounted(() => {
  // 页面加载时检查是否需要迁移
  setTimeout(checkMigration, 1000); // 延迟1秒执行，确保页面完全加载
});
</script>

<template>
  <v-locale-provider>
    <v-app :theme="useCustomizerStore().uiTheme"
      :class="[customizer.fontTheme, customizer.mini_sidebar ? 'mini-sidebar' : '', customizer.inputBg ? 'inputWithbg' : '']"
    >
      <!-- 路由切换进度条 -->
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
      
      <!-- Migration Dialog -->
      <MigrationDialog ref="migrationDialog" />
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
