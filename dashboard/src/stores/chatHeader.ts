import { defineStore } from "pinia";

export const useChatHeaderStore = defineStore("chatHeader", {
  state: () => ({
    title: "",
    subtitle: "",
    // Double-clicking the header title asks the chat page to rename the
    // current conversation with its usual dialog.
    titleRenamable: false,
    renameRequested: false,
    projectId: "",
    workspaceFilesOpen: false,
    workbenchWidth: null as number | null,
  }),

  actions: {
    SET_CONTEXT(payload: {
      title?: string;
      subtitle?: string;
      projectId?: string;
      titleRenamable?: boolean;
    }) {
      const nextProjectId = payload.projectId || "";
      if (this.projectId !== nextProjectId) {
        this.workspaceFilesOpen = false;
      }
      this.title = payload.title || "";
      this.subtitle = payload.subtitle || "";
      this.projectId = nextProjectId;
      this.titleRenamable = Boolean(payload.titleRenamable);
    },
    REQUEST_RENAME() {
      if (this.titleRenamable) this.renameRequested = true;
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
      this.titleRenamable = false;
      this.renameRequested = false;
    },
  },
});
