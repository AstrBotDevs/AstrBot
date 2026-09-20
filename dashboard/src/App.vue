<template>
  <RouterView></RouterView>
  <WaitingForRestart ref="globalWaitingRef" />
  <UpgradeRecoveryDialog />

  <!-- 全局唯一 snackbar -->
  <v-snackbar v-if="toastStore.current" v-model="snackbarShow" :color="toastStore.current.color"
    :timeout="toastStore.current.timeout" :multi-line="toastStore.current.multiLine"
    :location="toastStore.current.location" close-on-back>
    <div class="app-snackbar-message">
      <v-icon v-if="toastIcon" :icon="toastIcon" size="24" />
      <span>{{ toastStore.current.message }}</span>
    </div>
    <template #actions v-if="toastStore.current.closable">
      <v-btn icon="mdi-close" variant="text" size="small" aria-label="Close notification" @click="snackbarShow = false" />
    </template>
  </v-snackbar>
</template>

<script setup>
import { RouterView } from 'vue-router';
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useToastStore } from '@/stores/toast'
import WaitingForRestart from '@/components/shared/WaitingForRestart.vue'
import UpgradeRecoveryDialog from '@/components/shared/UpgradeRecoveryDialog.vue'

const toastStore = useToastStore()
const globalWaitingRef = ref(null)
let disposeTrayRestartListener = null

const snackbarShow = computed({
  get: () => !!toastStore.current,
  set: (val) => {
    if (!val) toastStore.shift()
  }
})

const toastIcon = computed(() => ({
  success: 'mdi-check-circle-outline',
  error: 'mdi-alert-circle-outline',
  warning: 'mdi-alert-outline',
  info: 'mdi-information-outline',
  primary: 'mdi-information-outline'
})[toastStore.current?.color] || '')

onMounted(() => {
  const desktopBridge = window.astrbotDesktop
  if (!desktopBridge?.onTrayRestartBackend) {
    return
  }
  disposeTrayRestartListener = desktopBridge.onTrayRestartBackend(async () => {
    try {
      await globalWaitingRef.value?.check?.()
    } catch (error) {
      globalWaitingRef.value?.stop?.()
      console.error('Tray restart backend failed:', error)
    }
  })
})

onBeforeUnmount(() => {
  if (disposeTrayRestartListener) {
    disposeTrayRestartListener()
    disposeTrayRestartListener = null
  }
})
</script>
