<script setup lang="ts">
import { RouterView } from 'vue-router';
import { ref, onMounted } from 'vue';
import axios from 'axios';
import VerticalSidebarVue from './vertical-sidebar/VerticalSidebar.vue';
import VerticalHeaderVue from './vertical-header/VerticalHeader.vue';
import MigrationDialog from '@/components/shared/MigrationDialog.vue';
import { useCustomizerStore } from '@/stores/customizer';

const customizer = useCustomizerStore();
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
      <VerticalHeaderVue />
      <VerticalSidebarVue />
      <v-main>
        <v-container fluid class="page-wrapper" style="height: calc(100% - 8px)">
          <div style="height: 100%;">
            <RouterView />
          </div>
        </v-container>
      </v-main>
      
      <!-- Migration Dialog -->
      <MigrationDialog ref="migrationDialog" />
    </v-app>
  </v-locale-provider>
</template>
