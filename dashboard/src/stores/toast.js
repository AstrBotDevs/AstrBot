import { defineStore } from "pinia";
import { computed, ref } from "vue";

/** @typedef {"top" | "bottom" | "start" | "end" | "center" | "center center" | "top center" | "top start" | "top end" | "bottom center" | "bottom start" | "bottom end"} ToastLocation */
/** @typedef {{label: string, onClick: () => void}} ToastAction */
/** @typedef {{message: string, color: string, timeout: number, closable: boolean, multiLine: boolean, location: ToastLocation, action: ToastAction | null}} Toast */

export const useToastStore = defineStore("toast", () => {
  const queue = ref(/** @type {Toast[]} */ ([]));
  const current = computed(() => queue.value[0]);

  /** @param {Pick<Toast, "message"> & Partial<Omit<Toast, "message">>} options */
  function add({
    message,
    color = "info", // Vuetify 颜色
    timeout = 3000,
    closable = true,
    multiLine = false,
    location = "top center",
    action = null,
  }) {
    queue.value.push({
      message,
      color,
      timeout,
      closable,
      multiLine,
      location,
      action,
    });
  }

  function shift() {
    queue.value.shift();
  }

  return { current, add, shift };
});
