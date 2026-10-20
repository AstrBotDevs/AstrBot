import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useToastStore = defineStore('toast', () => {
  const queue = ref([])
  const current = computed(() => queue.value[0])

  function add({
    message,
    color = 'info',   // Vuetify 颜色
    timeout = 3000,
    closable = true,
    multiLine = false,
    location = 'top center'
  }) {
    queue.value.push({
      message,
      color,
      timeout,
      closable,
      multiLine,
      location
    })
  }

  function shift() {
    queue.value.shift()
  }

  return { current, add, shift }
})
