<script setup>
import { ref, shallowRef, onMounted, onUnmounted } from 'vue';
import { useCustomizerStore } from '../../../stores/customizer';
import { useI18n } from '@/i18n/composables';
import sidebarItems from './sidebarItem';
import NavItem from './NavItem.vue';
import { applySidebarCustomization } from '@/utils/sidebarCustomization';

const { t } = useI18n();

const customizer = useCustomizerStore();
const sidebarMenu = shallowRef(sidebarItems);

// Apply customization on mount and listen for storage changes
const handleStorageChange = (e) => {
  if (e.key === 'astrbot_sidebar_customization') {
    sidebarMenu.value = applySidebarCustomization(sidebarItems);
  }
};

const handleCustomEvent = () => {
  sidebarMenu.value = applySidebarCustomization(sidebarItems);
};

onMounted(() => {
  sidebarMenu.value = applySidebarCustomization(sidebarItems);
  
  window.addEventListener('storage', handleStorageChange);
  window.addEventListener('sidebar-customization-changed', handleCustomEvent);
});

onUnmounted(() => {
  window.removeEventListener('storage', handleStorageChange);
  window.removeEventListener('sidebar-customization-changed', handleCustomEvent);
});

const showIframe = ref(false);
const starCount = ref(null);

const sidebarWidth = ref(235);
const minSidebarWidth = 200;
const maxSidebarWidth = 300;
const isResizing = ref(false);

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

if (window.innerWidth < 768) {
  iframeStyle.value = {
    position: 'fixed',
    top: '10%',
    left: '0%',
    width: '100%',
    height: '80%',
    minWidth: '300px',
    minHeight: '200px',
    background: 'white',
    resize: 'both',
    overflow: 'auto',
    zIndex: '1002',
    borderRadius: '12px',
    boxShadow: '0px 4px 12px rgba(0, 0, 0, 0.1)',
  };
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

let offsetX = 0;
let offsetY = 0;
let isDragging = false;

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

function startSidebarResize(event) {
  isResizing.value = true;
  document.body.style.userSelect = 'none';
  document.body.style.cursor = 'ew-resize';
  
  const startX = event.clientX;
  const startWidth = sidebarWidth.value;
  
  function onMouseMoveResize(event) {
    if (!isResizing.value) return;
    
    const deltaX = event.clientX - startX;
    const newWidth = Math.max(minSidebarWidth, Math.min(maxSidebarWidth, startWidth + deltaX));
    sidebarWidth.value = newWidth;
  }
  
  function onMouseUpResize() {
    isResizing.value = false;
    document.body.style.userSelect = '';
    document.body.style.cursor = '';
    document.removeEventListener('mousemove', onMouseMoveResize);
    document.removeEventListener('mouseup', onMouseUpResize);
  }
  
  document.addEventListener('mousemove', onMouseMoveResize);
  document.addEventListener('mouseup', onMouseUpResize);
}

function formatNumber(num) {
  return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

async function fetchStarCount() {
  try {
    const response = await fetch('https://cloud.astrbot.app/api/v1/github/repo-info');
    const data = await response.json();
    if (data.data && data.data.stargazers_count) {
      starCount.value = data.data.stargazers_count;
      console.debug('Fetched star count:', starCount.value);
    }
  } catch (error) {
    console.debug('Failed to fetch star count:', error);
  }
}

fetchStarCount();

</script>

<template>
  <v-navigation-drawer
    left
    v-model="customizer.Sidebar_drawer"
    elevation="0"
    rail-width="80"
    app
    class="leftSidebar"
    :width="sidebarWidth"
    :rail="customizer.mini_sidebar"
  >
    <div class="sidebar-container">
      <v-list class="pa-4 listitem flex-grow-1">
        <template v-for="(item, i) in sidebarMenu" :key="i">
          <NavItem :item="item" class="leftPadding" />
        </template>
      </v-list>
      <div class="sidebar-footer" v-if="!customizer.mini_sidebar">
        <v-btn style="margin-bottom: 8px;" size="small" variant="tonal" color="primary" to="/settings">
          🔧 {{ t('core.navigation.settings') }}
        </v-btn>
        <v-btn style="margin-bottom: 8px;" size="small" variant="plain" @click="toggleIframe">
          {{ t('core.navigation.documentation') }}
        </v-btn>
        <v-btn style="margin-bottom: 8px;" size="small" variant="plain" @click="openIframeLink('https://github.com/AstrBotDevs/AstrBot')">
          {{ t('core.navigation.github') }}
           <v-chip
            v-if="starCount"
            size="x-small"
            variant="outlined"
            class="ml-2"
            style="font-weight: normal;"
          >{{ formatNumber(starCount) }}</v-chip>
        </v-btn>
      </div>
    </div>
    
    <div 
      v-if="!customizer.mini_sidebar && customizer.Sidebar_drawer"
      class="sidebar-resize-handle"
      @mousedown="startSidebarResize"
      :class="{ 'resizing': isResizing }"
    >
    </div>
  </v-navigation-drawer>
  
  <div
    v-if="showIframe"
    id="draggable-iframe"
    :style="iframeStyle"
  >

    <div :style="dragHeaderStyle" @mousedown="onMouseDown" @touchstart="onTouchStart">
      <div style="display: flex; align-items: center;">
        <v-icon icon="mdi-cursor-move" />
        <span style="margin-left: 8px;">{{ t('core.navigation.drag') }}</span>
      </div>
      <div style="display: flex; gap: 8px;">
        <v-btn
          icon
          @click.stop="openIframeLink('https://astrbot.app')"
          @mousedown.stop
          style="border-radius: 8px; border: 1px solid #ccc;"
        >
          <v-icon icon="mdi-open-in-new" />
        </v-btn>
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
    <iframe
      src="https://astrbot.app"
      style="width: 100%; height: calc(100% - 56px); border: none; border-bottom-left-radius: 12px; border-bottom-right-radius: 12px;"
    ></iframe>
  </div>
</template>

<style scoped>
.sidebar-resize-handle {
  position: absolute;
  top: 0;
  right: 0;
  width: 4px;
  height: 100%;
  background: transparent;
  cursor: ew-resize;
  user-select: none;
  z-index: 1000;
  transition: background-color 0.2s ease;
}

.sidebar-resize-handle:hover,
.sidebar-resize-handle.resizing {
  background: rgba(var(--v-theme-primary), 0.3);
}

.sidebar-resize-handle::before {
  content: '';
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 2px;
  height: 30px;
  background: rgba(var(--v-theme-on-surface), 0.3);
  border-radius: 1px;
  opacity: 0;
  transition: opacity 0.2s ease;
}

.sidebar-resize-handle:hover::before,
.sidebar-resize-handle.resizing::before {
  opacity: 1;
}

/* 确保侧边栏容器支持相对定位 */
.leftSidebar .v-navigation-drawer__content {
  position: relative;
}
</style>