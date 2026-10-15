import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useToastStore = defineStore('toast', () => {
  const queue = ref([])
  const current = computed(() => queue.value[0])
  let nextId = 0

  function add({
    message,
    group = null,
    color = 'info',   // Vuetify 颜色
    timeout = 3000,
    closable = true,
    multiLine = false,
    location = 'top center'
  }) {
    const notification = {
      id: nextId++,
      group,
      message,
      color,
      timeout,
      closable,
      multiLine,
      location
    }
    const index = group == null ? -1 : queue.value.findIndex(item => item.group === group)
    if (index === -1) {
      queue.value.push(notification)
    } else {
      queue.value[index] = notification
    }
  }

  function shift() {
    queue.value.shift()
  }

  return { current, add, shift }
})
