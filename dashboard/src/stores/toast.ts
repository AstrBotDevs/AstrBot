import { defineStore } from 'pinia';
import { computed, ref } from 'vue';

export type ToastColor = 'info' | 'success' | 'error' | 'primary' | 'warning';

export interface ToastItem {
  message: string;
  color: ToastColor;
  timeout: number;
  closable: boolean;
  location: string;
}

export interface ToastPayload {
  message: string;
  color?: ToastColor;
  timeout?: number;
  closable?: boolean;
  location?: string;
}

export const useToastStore = defineStore('toast', () => {
  const queue = ref<ToastItem[]>([]);
  const current = computed(() => queue.value[0] ?? null);

  function add({
    message,
    color = 'info',
    timeout = 3000,
    closable = true,
    location = 'top center',
  }: ToastPayload): void {
    queue.value.push({
      message,
      color,
      timeout,
      closable,
      location,
    });
  }

  function shift(): void {
    queue.value.shift();
  }

  return { current, add, shift };
});
