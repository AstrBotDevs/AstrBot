<template>
  <RouterView />
  <WaitingForRestart ref="globalWaitingRef" />

  <!-- 全局唯一 snackbar -->
  <v-snackbar
    v-if="toastStore.current"
    v-model="snackbarShow"
    :color="toastStore.current.color"
    :timeout="toastStore.current.timeout"
    :multi-line="toastStore.current.multiLine"
    :location="toastStore.current.location"
    close-on-back
  >
    {{ toastStore.current.message }}
    <template v-if="toastStore.current.closable" #actions>
      <v-btn variant="text" @click="snackbarShow = false"> 关闭 </v-btn>
    </template>
  </v-snackbar>
</template>

<script setup lang="ts">
import { RouterView } from "vue-router";
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useTheme } from "vuetify";
import { useToastStore } from "@/stores/toast";
import { useCustomizerStore } from "@/stores/customizer";
import WaitingForRestart from "@/components/shared/WaitingForRestart.vue";

const toastStore = useToastStore();
const theme = useTheme();
const customizer = useCustomizerStore();
const globalWaitingRef = ref(null);
let disposeTrayRestartListener = null;

const snackbarShow = computed({
  get: () => !!toastStore.current,
  set: (val) => {
    if (!val) toastStore.shift();
  },
});

// 统一监听 uiTheme 变化并同步到 Vuetify
watch(
  () => customizer.uiTheme,
  (newTheme) => {
    if (newTheme) {

    }
  },
  { immediate: true },
);

onMounted(() => {
  const desktopBridge = window.astrbotDesktop;
  if (!desktopBridge?.onTrayRestartBackend) {
    return;
  }
  disposeTrayRestartListener = desktopBridge.onTrayRestartBackend(async () => {
    try {
      await globalWaitingRef.value?.check?.();
    } catch (error) {
      globalWaitingRef.value?.stop?.();
      console.error("Tray restart backend failed:", error);
    }
  });
});

onBeforeUnmount(() => {
  if (disposeTrayRestartListener) {
    disposeTrayRestartListener();
    disposeTrayRestartListener = null;
  }
});
</script>
