import 'vue'

import type { ConfirmDialogHandler } from '@/utils/confirmDialog'

declare module 'vue' {
  interface ComponentCustomProperties {
    $confirm?: ConfirmDialogHandler
  }
}

export {}
