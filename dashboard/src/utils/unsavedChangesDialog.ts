import type { App } from "vue";
import { h, render } from "vue";
import UnsavedChangesConfirmDialog from "../components/config/UnsavedChangesConfirmDialog.vue";

export type UnsavedChangesDialogOptions = {
  title?: string
  message: string
  confirmHint: string
  cancelHint: string
}

export type UnsavedChangesDialogHandler = (options: UnsavedChangesDialogOptions) => Promise<boolean>

let dialogHandler: UnsavedChangesDialogHandler | null = null;

export default {
  install(app: App) {
    const mountNode = document.createElement("div");
    document.body.appendChild(mountNode);

    const vNode = h(UnsavedChangesConfirmDialog);
    vNode.appContext = app._context;
    render(vNode, mountNode);

    dialogHandler = (options) => {
      return new Promise<boolean>((resolve) => {
        vNode.component?.exposed?.open(options).then(resolve);
      });
    };
  }
};

export function useUnsavedChangesDialog(): UnsavedChangesDialogHandler | null {
  return dialogHandler;
}

export async function askForUnsavedChangesConfirmation(
  options: UnsavedChangesDialogOptions
): Promise<boolean> {
  if (!dialogHandler) {
    throw new Error('UnsavedChangesDialog not installed. Use app.use(unsavedChangesDialogPlugin) in main.ts');
  }
  try {
    return await dialogHandler(options);
  } catch {
    return false;
  }
}
