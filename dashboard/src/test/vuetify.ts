// Author: elecvoid243, 2026-07-20
// Reusable Vuetify component stubs for component tests. Avoid pulling
// the full vuetify bundle (which trips Vite's CSS loader on the
// happy-dom transform). Keep stub markup minimal — output only the
// `data-test` hooks the tests actually assert on.
import type { Component } from "vue";

export const vuetifyStubs: Record<string, Component> = {
  "v-icon": {
    template: '<i data-test="v-icon-stub"><slot /></i>',
  },
};
