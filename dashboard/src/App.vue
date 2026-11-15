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
const scrollbarAnimations = new Map()
const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)')

// Capture nested scroll events and keep each scroll area's visibility independent.
const onScrollbarScroll = (event) => {
  const element = event.target === document ? document.scrollingElement : event.target
  if (!(element instanceof HTMLElement)) return

  const previous = scrollbarAnimations.get(element)
  clearTimeout(previous?.timer)
  cancelAnimationFrame(previous?.frame)
  element.style.setProperty('--astrbot-scrollbar-opacity', '1')
  const animation = { timer: 0, frame: 0 }
  animation.timer = setTimeout(() => {
    const started = performance.now()
    // Scrollbar pseudo-elements do not reliably support CSS transitions.
    animation.frame = requestAnimationFrame(function fadeScrollbar(now) {
      const opacity = reducedMotion.matches ? 0 : Math.max(0, Math.min(1, 1 - (now - started) / 250))
      element.style.setProperty('--astrbot-scrollbar-opacity', String(opacity))
      if (opacity > 0) {
        animation.frame = requestAnimationFrame(fadeScrollbar)
      } else {
        element.style.removeProperty('--astrbot-scrollbar-opacity')
        scrollbarAnimations.delete(element)
      }
    })
  }, 800)
  scrollbarAnimations.set(element, animation)
}

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
  document.addEventListener('scroll', onScrollbarScroll, { capture: true, passive: true })
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
  document.removeEventListener('scroll', onScrollbarScroll, true)
  for (const [element, animation] of scrollbarAnimations) {
    clearTimeout(animation.timer)
    cancelAnimationFrame(animation.frame)
    element.style.removeProperty('--astrbot-scrollbar-opacity')
  }
  scrollbarAnimations.clear()
  if (disposeTrayRestartListener) {
    disposeTrayRestartListener()
    disposeTrayRestartListener = null
  }
})
</script>
