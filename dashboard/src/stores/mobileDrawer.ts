import { defineStore } from "pinia";

/**
 * Shared open state for the mobile navigation drawer. On small screens both
 * sidebars become temporary overlay drawers; the header's menu button and the
 * active sidebar bind to this single value (only one is mounted at a time).
 */
export const useMobileDrawerStore = defineStore("mobileDrawer", {
  state: () => ({
    open: false,
  }),
  actions: {
    SET(open: boolean) {
      this.open = open;
    },
    TOGGLE() {
      this.open = !this.open;
    },
  },
});
