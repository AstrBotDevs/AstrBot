<template>
  <div class="logo-container">
    <div class="logo-content">
      <div class="logo-image">
        <img width="110" src="@/assets/images/astrbot_logo_mini.webp" alt="AstrBot Logo">
      </div>
      <div class="logo-text">
        <h2 
          :style="{color: useCustomizerStore().uiTheme === 'PurpleTheme' ? '#5e35b1' : '#d7c5fa'}"
          v-html="formatTitle(title)"
        ></h2>
        <!-- 父子组件传递css变量可能会出错，暂时使用十六进制颜色值 -->
        <h4 :style="{color: useCustomizerStore().uiTheme === 'PurpleTheme' ? '#000000aa' : '#ffffffcc'}"
            class="hint-text">{{ subtitle }}</h4>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useCustomizerStore } from "@/stores/customizer";

const props = withDefaults(defineProps<{
  title?: string;
  subtitle?: string;
}>(), {
  title: 'AstrBot 仪表盘',
  subtitle: '欢迎使用'
})

// 格式化标题，在小屏幕上允许在合适位置换行
const formatTitle = (title: string) => {
  if (title === 'AstrBot 仪表盘') {
    return 'AstrBot<wbr> 仪表盘'
  } else if (title === 'AstrBot Dashboard') {
    return 'AstrBot<wbr> Dashboard'
  }
  return title
}
</script>

<style scoped>
.logo-container {
  display: flex;
  justify-content: center;
  align-items: center;
  width: 100%;
  margin-bottom: 10px;
}

.logo-content {
  display: flex;
  align-items: center;
  gap: 20px;
  padding: 10px;
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

.logo-image img:hover {
  transform: scale(1.05);
}

.logo-text {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  min-width: 0;
  flex: 1;
}

.logo-text h2 {
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
  margin: 4px 0 0 0;
  font-size: 1rem;
  font-weight: 400;
  letter-spacing: 0.3px;
  white-space: nowrap;
}

/* 响应式处理 */
@media (max-width: 520px) {
  .logo-content {
    gap: 15px;
  }
  
  .logo-text h2 {
    font-size: 1.6rem;
  }
  
  .logo-text h4 {
    font-size: 0.9rem;
  }
  
  .logo-image img {
    width: 90px;
  }
}
</style>
