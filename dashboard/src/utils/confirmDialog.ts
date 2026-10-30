import { inject } from 'vue'

export type ConfirmDialogCheckbox = {
  label: string
  hint?: string
}

export type ConfirmDialogResult = {
  confirmed: boolean
  checked: boolean
}

export type ConfirmDialogOptions = {
  title?: string
  message?: string
  checkbox?: ConfirmDialogCheckbox
}

export type ConfirmDialogHandler = (
  options: ConfirmDialogOptions
) => Promise<boolean | ConfirmDialogResult>

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
      const result = await confirmDialog({ message })
      return typeof result === 'object' ? result.confirmed : result
    } catch {
      return false
    }
  }

  return window.confirm(message)
}

export async function askForConfirmationWithCheckbox(
  message: string,
  options: {
    candidate?: ConfirmDialogCandidate
    checkbox?: ConfirmDialogCheckbox
  } = {}
): Promise<ConfirmDialogResult> {
  const confirmDialog = options.candidate ?? undefined

  if (confirmDialog) {
    try {
      const result = await confirmDialog({ message, checkbox: options.checkbox })
      if (typeof result === 'object') {
        return result
      }
      // Handler without checkbox support: treat it as a plain confirmation.
      return { confirmed: result, checked: false }
    } catch {
      return { confirmed: false, checked: false }
    }
  }

  // Native confirm cannot render a checkbox; stay on the safe side.
  return { confirmed: window.confirm(message), checked: false }
}
