import { defineStore } from "pinia";
import type { Component } from "vue";

/**
 * Lets pages project contextual content into the top toolbar: a page registers
 * a component while it is visible, and the header renders it in its context
 * slot. Keep it a single component per page; register null when leaving.
 */
export const useHeaderContextStore = defineStore("headerContext", {
  state: () => ({
    component: null as Component | null,
  }),
  actions: {
    SET_COMPONENT(component: Component | null) {
      this.component = component;
    },
  },
});
