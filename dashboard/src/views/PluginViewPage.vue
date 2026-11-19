<script setup lang="ts">
import { useRoute } from "vue-router";
import PluginViewFrame from "@/components/plugins/PluginViewFrame.vue";
const route = useRoute();
</script>

<template>
  <PluginViewFrame
    :plugin-id="String(route.params.pluginName || '')"
    :view-name="String(route.params.pageName || '')"
  />
</template>
