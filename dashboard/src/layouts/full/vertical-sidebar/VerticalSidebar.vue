<script setup>
import { ref, shallowRef, onMounted } from 'vue';
import axios from 'axios';
import { useCustomizerStore } from '../../../stores/customizer';
import sidebarItems from './sidebarItem';
import NavItem from './NavItem.vue';

const customizer = useCustomizerStore();
const sidebarMenu = shallowRef(sidebarItems);

const showIframe = ref(false);

// 默认桌面端 iframe 样式
const iframeStyle = ref({
  position: 'fixed',
  bottom: '16px',
  right: '16px',
  width: '490px',
  height: '640px',
  minWidth: '300px',
  minHeight: '200px',
  background: 'white',
  resize: 'both',
  overflow: 'auto',
  zIndex: '10000000',
  borderRadius: '12px',
  boxShadow: '0px 4px 12px rgba(0, 0, 0, 0.1)',
});

// 如果为移动端，则采用百分比尺寸，并设置初始位置
if (window.innerWidth < 768) {
  iframeStyle.value = {
    position: 'fixed',
    top: '10%',
    left: '0%',
    width: '100%',
    height: '50%',
    minWidth: '300px',
    minHeight: '200px',
    background: 'white',
    resize: 'both',
    overflow: 'auto',
    zIndex: '1002',
    borderRadius: '12px',
    boxShadow: '0px 4px 12px rgba(0, 0, 0, 0.1)',
  };
  // 移动端默认关闭侧边栏
  customizer.Sidebar_drawer = false;
}

const dragHeaderStyle = {
  width: '100%',
  padding: '8px',
  background: '#f0f0f0',
  borderBottom: '1px solid #ccc',
  borderTopLeftRadius: '8px',
  borderTopRightRadius: '8px',
  display: 'flex',
  justifyContent: 'space-between',
  alignItems: 'center',
  cursor: 'move'
};

function toggleIframe() {
  showIframe.value = !showIframe.value;
}

function openIframeLink(url) {
  if (typeof window !== 'undefined') {
    let url_ = url || "https://astrbot.app";
    window.open(url_, "_blank");
  }
}

// 拖拽相关变量与函数
let offsetX = 0;
let offsetY = 0;
let isDragging = false;

// 辅助函数：限制数值在一定范围内
function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function startDrag(clientX, clientY) {
  isDragging = true;
  const dm = document.getElementById('draggable-iframe');
  const rect = dm.getBoundingClientRect();
  offsetX = clientX - rect.left;
  offsetY = clientY - rect.top;
  document.body.style.userSelect = 'none';
  // 绑定全局鼠标和触摸事件
  document.addEventListener('mousemove', onMouseMove);
  document.addEventListener('mouseup', onMouseUp);
  document.addEventListener('touchmove', onTouchMove, { passive: false });
  document.addEventListener('touchend', onTouchEnd);
}

function onMouseDown(event) {
  startDrag(event.clientX, event.clientY);
}

function onMouseMove(event) {
  if (isDragging) {
    moveAt(event.clientX, event.clientY);
  }
}

function onMouseUp() {
  endDrag();
}

function onTouchStart(event) {
  if (event.touches.length === 1) {
    const touch = event.touches[0];
    startDrag(touch.clientX, touch.clientY);
  }
}

function onTouchMove(event) {
  if (isDragging && event.touches.length === 1) {
    event.preventDefault();
    const touch = event.touches[0];
    moveAt(touch.clientX, touch.clientY);
  }
}

function onTouchEnd() {
  endDrag();
}

function moveAt(clientX, clientY) {
  const dm = document.getElementById('draggable-iframe');
  const newLeft = clamp(clientX - offsetX, 0, window.innerWidth - dm.offsetWidth);
  const newTop = clamp(clientY - offsetY, 0, window.innerHeight - dm.offsetHeight);
  // 将拖拽后的位置同步到响应式样式变量中
  iframeStyle.value.left = newLeft + 'px';
  iframeStyle.value.top = newTop + 'px';
}

function endDrag() {
  isDragging = false;
  document.body.style.userSelect = '';
  document.removeEventListener('mousemove', onMouseMove);
  document.removeEventListener('mouseup', onMouseUp);
  document.removeEventListener('touchmove', onTouchMove);
  document.removeEventListener('touchend', onTouchEnd);
}

</script>

<template>
  <v-navigation-drawer
    left
    v-model="customizer.Sidebar_drawer"
    elevation="0"
    rail-width="80"
    app
    class="leftSidebar"
    width="220"
    :rail="customizer.mini_sidebar"
  >
    <div class="sidebar-container">
      <v-list class="pa-4 listitem flex-grow-1">
        <template v-for="(item, i) in sidebarMenu" :key="i">
          <NavItem :item="item" class="leftPadding" />
        </template>
      </v-list>
      <div class="sidebar-footer" v-if="!customizer.mini_sidebar">
        <v-btn style="margin-bottom: 8px;" size="small" variant="primary" to="/settings">
          🔧 设置
        </v-btn>
        <v-btn style="margin-bottom: 8px;" size="small" variant="plain" @click="toggleIframe">
          官方文档
        </v-btn>
        <v-btn style="margin-bottom: 8px;" size="small" variant="plain" @click="openIframeLink('https://github.com/AstrBotDevs/AstrBot')">
          GitHub
        </v-btn>
      </div>
    </div>
  </v-navigation-drawer>
  
  <div
    v-if="showIframe"
    id="draggable-iframe"
    :style="iframeStyle"
  >
    <!-- 拖拽头部：支持鼠标和触摸 -->
    <div :style="dragHeaderStyle" @mousedown="onMouseDown" @touchstart="onTouchStart">
      <div style="display: flex; align-items: center;">
        <v-icon icon="mdi-cursor-move" />
        <span style="margin-left: 8px;">拖拽</span>
      </div>
      <div style="display: flex; gap: 8px;">
        <!-- 跳转按钮 -->
        <v-btn
          icon
          @click.stop="openIframeLink"
          @mousedown.stop
          style="border-radius: 8px; border: 1px solid #ccc;"
        >
          <v-icon icon="mdi-open-in-new" />
        </v-btn>
        <!-- 关闭按钮 -->
        <v-btn
          icon
          @click.stop="toggleIframe"
          @mousedown.stop
          style="border-radius: 8px; border: 1px solid #ccc;"
        >
          <v-icon icon="mdi-close" />
        </v-btn>
      </div>
    </div>
    <!-- iframe 区域 -->
    <iframe
      src="https://astrbot.app"
      style="width: 100%; height: calc(100% - 56px); border: none; border-bottom-left-radius: 12px; border-bottom-right-radius: 12px;"
    ></iframe>
  </div>
</template>
