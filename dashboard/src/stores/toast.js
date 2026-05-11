import { defineStore } from "pinia";
import { ref, computed } from "vue";

/**
 * @typedef {Object} ToastItem
 * @property {string} message
 * @property {string} color
 * @property {number} timeout
 * @property {boolean} closable
 * @property {boolean} multiLine
 * @property {string} location
 */

export const useToastStore = defineStore("toast", () => {
  /** @type {import('vue').Ref<ToastItem[]>} */
  const queue = ref([]);
  const current = computed(() => queue.value[0]);

  function add({
    message,
    color = "info", // Vuetify 颜色
    timeout = 3000,
    closable = true,
    multiLine = false,
    location = "top center",
  }) {
    queue.value.push({
      message,
      color,
      timeout,
      closable,
      multiLine,
      location,
    });
  }

  function shift() {
    queue.value.shift();
  }

  return { current, add, shift };
});
