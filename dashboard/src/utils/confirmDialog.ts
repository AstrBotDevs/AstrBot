import { inject } from 'vue'

export type ConfirmDialogOptions = {
  title?: string
  message?: string
}

export type ConfirmDialogHandler = (options: ConfirmDialogOptions) => Promise<boolean>

export function resolveConfirmDialog(candidate: unknown): ConfirmDialogHandler | undefined {
  if (typeof candidate === 'function') {
    return candidate as ConfirmDialogHandler
  }

  return undefined
}

export function useConfirmDialog(): ConfirmDialogHandler | undefined {
  return resolveConfirmDialog(inject('$confirm', undefined))
}

export async function askForConfirmation(
  message: string,
  candidate?: unknown
): Promise<boolean> {
  const confirmDialog = resolveConfirmDialog(candidate)

  if (confirmDialog) {
    try {
      return await confirmDialog({ message })
    } catch {
      return false
    }
  }

  return window.confirm(message)
}
