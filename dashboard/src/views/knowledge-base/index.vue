<template>
  <div class="kb-container">
    <router-view v-slot="{ Component }">
      <transition name="kb-fade" mode="out-in">
        <component :is="Component" :key="$route.fullPath" />
      </transition>
    </router-view>
  </div>
</template>

<script setup lang="ts">
// 主容器组件,提供路由出口和页面切换动画
</script>

<style scoped>
.kb-container {
  width: 100%;
  height: 100%;
  position: relative;
}

/* 页面切换动画 */
.kb-fade-enter-active,
.kb-fade-leave-active {
  transition: opacity 0.3s ease, transform 0.3s ease;
}

.kb-fade-enter-from {
  opacity: 0;
  transform: translateY(10px);
}

.kb-fade-leave-to {
  opacity: 0;
  transform: translateY(-10px);
}
</style>
