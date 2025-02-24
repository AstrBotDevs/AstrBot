<script setup lang="ts">
import { ref, shallowRef } from 'vue';
import { useCustomizerStore } from '../../../stores/customizer';
import sidebarItems from './sidebarItem';
import NavItem from './NavItem.vue';

const customizer = useCustomizerStore();
const sidebarMenu = shallowRef(sidebarItems);

const showIframe = ref(false);

const iframeStyle = ref({
  position: 'fixed',
  bottom: '16px',
  right: '16px',
  width: '500px',
  height: '400px',
  border: '1px solid #ccc',
  background: 'white',
  resize: 'both',
  overflow: 'auto',
  zIndex: 10000000,
  borderRadius: '8px'
});

const dragButtonStyle = {
  width: '100%',
  padding: '4px',
  cursor: 'move',
  background: '#f0f0f0',
  borderBottom: '1px solid #ccc',
  borderTopLeftRadius: '8px',
  borderTopRightRadius: '8px'
};

function toggleIframe() {
  showIframe.value = !showIframe.value;
}

let offsetX = 0;
let offsetY = 0;
let isDragging = false;

function onMouseDown(event) {
  isDragging = true;
  offsetX = event.clientX - event.target.parentElement.getBoundingClientRect().left;
  offsetY = event.clientY - event.target.parentElement.getBoundingClientRect().top;
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
}

</script>

<template>
  <v-navigation-drawer left v-model="customizer.Sidebar_drawer" elevation="0" rail-width="80" app class="leftSidebar"
    :rail="customizer.mini_sidebar">
    <v-list class="pa-4 listitem" style="height: auto">
      <template v-for="(item, i) in sidebarMenu" :key="i">
        <NavItem :item="item" class="leftPadding" />
      </template>
    </v-list>
    <div class="text-center">
      <v-chip color="inputBorder" size="small"> {{ version }} </v-chip>
    </div>

    <div style="position: absolute; bottom: 32px; width: 100%" class="text-center">
      <v-list-item v-if="!customizer.mini_sidebar" @click="toggleIframe">
        <v-btn variant="plain" size="small">
          🤔 点击查看悬浮文档！
        </v-btn>
      </v-list-item>
      <small style="display: block;" v-if="buildVer">构建: {{ buildVer }}</small>
      <small style="display: block;" v-else>构建: embedded</small>
      <v-tooltip text="使用 /dashboard_update 指令更新管理面板">
        <template v-slot:activator="{ props }">
          <small v-bind="props" v-if="hasWebUIUpdate" style="display: block; margin-top: 4px;">面板有更新</small>
        </template>
      </v-tooltip>


      <small style="display: block; margin-top: 8px;">© 2025 AstrBot</small>
    </div>

  </v-navigation-drawer>

  <div v-if="showIframe"
    id="draggable-iframe"
    :style="iframeStyle"
    @mousemove="onMouseMove"
    @mouseup="onMouseUp"
    @mouseleave="onMouseUp">
    <div :style="dragButtonStyle" @mousedown="onMouseDown">
      <v-icon icon="mdi-cursor-move" />
    </div>
    <iframe src="https://astrbot.app" style="width: 100%; height: calc(100% - 24px); border: none; border-bottom-left-radius: 8px; border-bottom-right-radius: 8px;"></iframe>
  </div>
</template>

<script lang="ts">
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
    this.get_version()
    this.check_webui_update()
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