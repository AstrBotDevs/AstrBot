<template>
  <div class="logo-container">
    <div class="logo-content">
      <div class="logo-image">
        <img width="80" src="@/assets/images/plugin_icon.png" alt="AstrBot Logo">
      </div>
      <div class="logo-text">
        <h2 
          v-html="formatTitle(title || t('core.header.logoTitle'))"
        ></h2>
        <h4 class="hint-text">{{ subtitle || t('core.header.accountDialog.title') }}</h4>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from '@/i18n/composables';

const { t } = useI18n();

const props = withDefaults(defineProps<{
  title?: string;
  subtitle?: string;
}>(), {
  title: '',  // 默认为空，组件会使用翻译值
  subtitle: ''
})

// 智能格式化标题，在小屏幕上允许在合适位置换行
const formatTitle = (title: string) => {
  // 如果标题包含 "AstrBot" 和其他文字，在它们之间添加换行机会
  if (title.includes('AstrBot ') || title.includes('AstrBot')) {
    // 处理 "AstrBot 仪表盘" 或 "AstrBot Dashboard" 等格式
    return title.replace(/(AstrBot)\s+(.+)/, '$1<wbr> $2');
  }
  return title;
}
</script>

<style scoped>
.logo-container {
  display: flex;
  justify-content: flex-start;
  align-items: center;
  width: 100%;
  margin-bottom: 10px;
}

.logo-content {
  display: flex;
  align-items: flex-start;
  gap: 16px;
  padding: 10px 0;
  max-width: 100%;
  overflow: visible;
}

.logo-image {
  display: flex;
  justify-content: center;
  align-items: center;
}

.logo-image img {
  transition: transform 0.3s ease;
}

.logo-text {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  min-width: 0;
  flex: 1;
}

.logo-text h2 {
  color: rgb(var(--v-theme-on-surface));
  margin: 0;
  font-size: 1.8rem;
  font-weight: 600;
  letter-spacing: 0.5px;
  white-space: nowrap;
  min-width: fit-content;
}

/* 在小屏幕上允许在指定位置换行 */
@media (max-width: 420px) {
  .logo-text h2 {
    line-height: 1.3;
  }
}

.logo-text h4 {
  color: rgba(var(--v-theme-on-surface), 0.72);
  margin: 4px 0 0 0;
  font-size: 1rem;
  font-weight: 400;
  letter-spacing: 0.3px;
  white-space: nowrap;
}

/* 响应式处理 */
@media (max-width: 520px) {
  .logo-content {
    gap: 8px;
  }
  
  .logo-text h2 {
    font-size: 1.6rem;
  }
  
  .logo-text h4 {
    font-size: 0.9rem;
  }
  
  .logo-image img {
    width: 64px;
  }
}
</style>
