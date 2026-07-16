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
    :location="snackbarLocation"
    close-on-back
  >
    <div class="app-snackbar-message">
      <v-icon v-if="toastIcon" :icon="toastIcon" size="24" />
      <span>{{ toastStore.current.message }}</span>
    </div>
    <template v-if="toastStore.current.closable" #actions>
      <v-btn
        icon="mdi-close"
        variant="text"
        size="small"
        aria-label="Close notification"
        @click="snackbarShow = false"
      />
    </template>
  </v-snackbar>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { RouterView } from "vue-router";
// biome-ignore lint/style/useImportType: Vue template components require runtime imports.
import WaitingForRestart from "@/components/shared/WaitingForRestart.vue";
import { useCustomizerStore } from "@/stores/customizer";
import { useToastStore } from "@/stores/toast";

type SnackAnchor =
  | "top"
  | "bottom"
  | "start"
  | "end"
  | "center"
  | "center center"
  | "top center"
  | "top start"
  | "top end"
  | "bottom center"
  | "bottom start"
  | "bottom end";

const toastStore = useToastStore();
const customizer = useCustomizerStore();
const globalWaitingRef = ref<InstanceType<typeof WaitingForRestart> | null>(null);
let disposeTrayRestartListener: (() => void) | null = null;

const snackbarShow = computed({
  get: () => !!toastStore.current,
  set: (val) => {
    if (!val) toastStore.shift();
  },
});

const snackbarLocation = computed<SnackAnchor | undefined>(
  () => toastStore.current?.location as SnackAnchor | undefined,
);

const toastIcon = computed(
  () =>
    ({
      success: "mdi-check-circle-outline",
      error: "mdi-alert-circle-outline",
      warning: "mdi-alert-outline",
      info: "mdi-information-outline",
      primary: "mdi-information-outline",
    })[toastStore.current?.color ?? ""] ?? "",
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
