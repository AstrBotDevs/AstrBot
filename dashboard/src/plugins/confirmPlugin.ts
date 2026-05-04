import type { App } from "vue";
import { h, render } from "vue";
import ConfirmDialog from "@/components/ConfirmDialog.vue";

export default {
  install(app: App) {
    const mountNode = document.createElement("div");
    document.body.appendChild(mountNode);

    const vNode = h(ConfirmDialog);
    vNode.appContext = app._context;
    render(vNode, mountNode);

    const confirm = (options: { title?: string; message?: string }) => {
      return new Promise<boolean>((resolve) => {
        vNode.component?.exposed?.open(options).then(resolve); // ✅ 确保返回 `Promise<boolean>`
      });
    };

    app.config.globalProperties.$confirm = confirm;
    app.provide("$confirm", confirm);
  },
};