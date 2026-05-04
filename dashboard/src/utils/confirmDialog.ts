import { inject } from 'vue'

export type ConfirmDialogOptions = {
  title?: string
  message?: string
}

export type ConfirmDialogHandler = (options: ConfirmDialogOptions) => Promise<boolean>

export type ConfirmDialogCandidate = ConfirmDialogHandler | null | undefined

export function useConfirmDialog(): ConfirmDialogHandler | undefined {
  return inject<ConfirmDialogHandler | undefined>('$confirm', undefined)
}

export async function askForConfirmation(
  message: string,
  candidate?: ConfirmDialogCandidate
): Promise<boolean> {
  const confirmDialog = candidate ?? undefined

  if (confirmDialog) {
    try {
      return await confirmDialog({ message })
    } catch {
      return false
    }
  }

  return window.confirm(message)
}
