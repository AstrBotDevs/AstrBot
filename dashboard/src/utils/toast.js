import { useToastStore } from '@/stores/toast'

export function useToast() {
    const store = useToastStore()

    const toast = (message, color = 'info', opts = {}) =>
        store.add({ message, color, ...opts })

    return {
        toast,
        success: (msg, opts) => toast(msg, 'success', opts),
        error: (msg, opts) => toast(msg, 'error', opts),
        info: (msg, opts) => toast(msg, 'primary', opts),
        warning: (msg, opts) => toast(msg, 'warning', opts)
    }
}
