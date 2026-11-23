import { shallowMount } from "@vue/test-utils";
import { createPinia } from "pinia";
import { createMemoryHistory, createRouter } from "vue-router";
import { createVuetify } from "vuetify";
import { initI18n } from "../../src/i18n/composables.ts";

export async function mountDashboard(component, { route = "/", locale = "en-US", ...options } = {}) {
  await initI18n(locale);
  const pinia = createPinia();
  const vuetify = createVuetify();
  const router = createRouter({
    history: createMemoryHistory(),
    routes: ["/chat/:conversationId?", "/chatbox/:conversationId?", "/:pathMatch(.*)*"].map((path) => ({
      path,
      component: { render: () => null },
    })),
  });
  await router.push(route);
  await router.isReady();
  const wrapper = shallowMount(component, {
    ...options,
    global: {
      renderStubDefaultSlot: true,
      ...options.global,
      stubs: {
        ...Object.fromEntries(
          [
            "VAlert",
            "VAutocomplete",
            "VAvatar",
            "VBtn",
            "VBtnToggle",
            "VCard",
            "VCardActions",
            "VCardText",
            "VCardTitle",
            "VCheckbox",
            "VCheckboxBtn",
            "VChip",
            "VChipGroup",
            "VCol",
            "VCombobox",
            "VDialog",
            "VDivider",
            "VExpandTransition",
            "VIcon",
            "VList",
            "VListItem",
            "VListItemTitle",
            "VMenu",
            "VNavigationDrawer",
            "VOverlay",
            "VProgressCircular",
            "VProgressLinear",
            "VRadio",
            "VRadioGroup",
            "VRow",
            "VSelect",
            "VSheet",
            "VSlider",
            "VSpacer",
            "VSwitch",
            "VTab",
            "VTabs",
            "VTable",
            "VTextField",
            "VTextarea",
            "VTooltip",
            "VWindow",
            "VWindowItem",
          ].map((name) => [name, true]),
        ),
        ...options.global?.stubs,
      },
      plugins: [pinia, vuetify, router, ...(options.global?.plugins || [])],
    },
  });
  return { wrapper, vm: wrapper.vm, pinia, vuetify, router };
}
