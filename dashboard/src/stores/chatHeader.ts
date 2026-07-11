import { defineStore } from "pinia";

export const useChatHeaderStore = defineStore("chatHeader", {
  state: () => ({
    title: "",
    subtitle: "",
  }),

  actions: {
    SET_CONTEXT(payload: { title?: string; subtitle?: string }) {
      this.title = payload.title || "";
      this.subtitle = payload.subtitle || "";
    },
    CLEAR_CONTEXT() {
      this.title = "";
      this.subtitle = "";
    },
  },
});
