<script setup>
import { ref, shallowRef } from 'vue';
import { useCustomizerStore } from '../../../stores/customizer';
import sidebarItems from './sidebarItem';
import NavItem from './NavItem.vue';

const customizer = useCustomizerStore();
const sidebarMenu = shallowRef(sidebarItems);

const showIframe = ref(false);

const dragHeaderStyle = {
  width: '100%',
  padding: '4px',
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

let offsetX = 0;
let offsetY = 0;
let isDragging = false;

function onMouseDown(event) {
  // 如果点击的是关闭按钮则不启动拖拽
  // 可通过 event.target 判断（这里通过在关闭按钮上添加 .stop 处理）
  isDragging = true;
  const dm = document.getElementById('draggable-iframe');
  const rect = dm.getBoundingClientRect();
  offsetX = event.clientX - rect.left;
  offsetY = event.clientY - rect.top;
  // 禁用文字选中
  document.body.style.userSelect = 'none';
  // 绑定全局事件，确保拖拽不中断
  document.addEventListener('mousemove', onMouseMove);
  document.addEventListener('mouseup', onMouseUp);
}

function onMouseMove(event) {
  if (isDragging) {
    const dm = document.getElementById('draggable-iframe');
    dm.style.left = (event.clientX - offsetX) + 'px';
    dm.style.top = (event.clientY - offsetY) + 'px';
  }
}

function onMouseUp() {
  isDragging = false;
  document.body.style.userSelect = ''; // 恢复文字选中
  // 移除全局事件监听
  document.removeEventListener('mousemove', onMouseMove);
  document.removeEventListener('mouseup', onMouseUp);
}
</script>

<template>
  <v-navigation-drawer left v-model="customizer.Sidebar_drawer" elevation="0" rail-width="80" app class="leftSidebar" width="220"
    :rail="customizer.mini_sidebar">
    <v-list class="pa-4 listitem" style="height: auto;">
      <template v-for="(item, i) in sidebarMenu" :key="i">
        <NavItem :item="item" class="leftPadding" />
      </template>
    </v-list>
    <div class="text-center">
      <v-chip color="inputBorder" size="small"> {{ version }} </v-chip>
    </div>

    <div style="position: absolute; bottom: 32px; width: 100%; font-size: 13px;" class="text-center">
      <v-list-item v-if="!customizer.mini_sidebar" @click="toggleIframe">
        <v-btn variant="plain" size="small">
          🤔 点击此处 查看/关闭 悬浮文档！
        </v-btn>
      </v-list-item>
      <small style="display: block;" v-if="buildVer">WebUI 版本: {{ buildVer }}</small>
      <small style="display: block;" v-else>构建: embedded</small>
      <v-tooltip text="使用 /dashboard_update 指令更新管理面板">
        <template v-slot:activator="{ props }">
          <small v-bind="props" v-if="hasWebUIUpdate" style="display: block; margin-top: 4px;">面板有更新</small>
        </template>
      </v-tooltip>

      <small style="display: block; margin-top: 8px;">AGPL-3.0</small>
    </div>
  </v-navigation-drawer>
  
  <!-- 修改后的拖拽 iframe -->
  <div v-if="showIframe"
    id="draggable-iframe"
    style="position: fixed; bottom: 16px; right: 16px; width: 500px; height: 400px; min-width: 300px; min-height: 200px; border: 1px solid #ccc; background: white; resize: both; overflow: auto; z-index: 10000000; border-radius: 8px;">
    
    <!-- 拖拽头部，整个区域均可拖拽，内部的关闭按钮阻止事件冒泡 -->
    <div :style="dragHeaderStyle" @mousedown="onMouseDown">
      <div style="display: flex; align-items: center;">
        <v-icon icon="mdi-cursor-move" />
        <span style="margin-left: 8px;">拖拽</span>
      </div>
      <!-- 关闭按钮：点击时停止事件传播，避免触发拖拽 -->
      <v-btn 
        icon 
        @click.stop="toggleIframe" 
        @mousedown.stop
        style="border: 1px solid #ccc; border-radius: 8px; padding: 4px; width: 32px; height: 32px;"
      >
        <v-icon icon="mdi-close" />
      </v-btn>

    </div>
    
    <!-- iframe 区域 -->
    <iframe src="https://astrbot.app" style="width: 100%; height: calc(100% - 32px); border: none; border-bottom-left-radius: 8px; border-bottom-right-radius: 8px;"></iframe>
  </div>
</template>

<script>
import axios from 'axios';
export default {
  name: 'VerticalSidebar',
  components: {
    NavItem,
  },
  data: () => ({
    version: "",
    buildVer: "",
    hasWebUIUpdate: false,
  }),
  mounted() {
    this.get_version();
    this.check_webui_update();
  },
  methods: {
    get_version() {
      axios.get('/api/stat/version')
        .then((res) => {
          this.version = "v" + res.data.data.version;
        })
        .catch((err) => {
          console.log(err);
        });
    },
    check_webui_update() {
      axios.get('/api/update/check?type=dashboard')
        .then((res) => {
          this.hasWebUIUpdate = res.data.data.has_new_version;
          this.buildVer = res.data.data.current_version;
        })
        .catch((err) => {
          console.log(err);
        });
    }
  },
};
</script>
