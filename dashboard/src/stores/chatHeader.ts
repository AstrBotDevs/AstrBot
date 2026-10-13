import { defineStore } from "pinia";

export const useChatHeaderStore = defineStore("chatHeader", {
  state: () => ({
    title: "",
    subtitle: "",
    projectId: "",
    workspaceFilesOpen: false,
  }),

  actions: {
    SET_CONTEXT(payload: {
      title?: string;
      subtitle?: string;
      projectId?: string;
    }) {
      const nextProjectId = payload.projectId || "";
      if (this.projectId !== nextProjectId) {
        this.workspaceFilesOpen = false;
      }
      this.title = payload.title || "";
      this.subtitle = payload.subtitle || "";
      this.projectId = nextProjectId;
    },
    TOGGLE_WORKSPACE_FILES() {
      if (this.projectId) {
        this.workspaceFilesOpen = !this.workspaceFilesOpen;
      }
    },
    SET_WORKSPACE_FILES_OPEN(open: boolean) {
      this.workspaceFilesOpen = Boolean(open && this.projectId);
    },
    CLEAR_CONTEXT() {
      this.title = "";
      this.subtitle = "";
      this.projectId = "";
      this.workspaceFilesOpen = false;
    },
  },
});
