<script setup lang="ts">
import { shallowRef } from 'vue';
import { useCustomizerStore } from '../../../stores/customizer';
import sidebarItems from './sidebarItem';
import NavItem from './NavItem.vue';

const customizer = useCustomizerStore();
const sidebarMenu = shallowRef(sidebarItems);
</script>

<template>
  <v-navigation-drawer left v-model="customizer.Sidebar_drawer" elevation="0" rail-width="80"
    app class="leftSidebar" :rail="customizer.mini_sidebar">
    <v-list class="pa-4 listitem" style="height: auto">
      <template v-for="(item, i) in sidebarMenu" :key="i">
        <NavItem :item="item" class="leftPadding" />
      </template>
    </v-list>
    <div class="text-center">
      <v-chip color="inputBorder" size="small"> {{ version }} </v-chip>
    </div>

    <div style="position: absolute; bottom: 32px; width: 100%" class="text-center">
      <v-list-item v-if="!customizer.mini_sidebar" href="https://astrbot.soulter.top/">
        <v-btn variant="plain" size="small">
          🤔 初次使用？点击查看文档！
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