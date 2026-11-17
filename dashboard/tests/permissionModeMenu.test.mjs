import assert from "node:assert/strict";
import test from "node:test";
import { ref } from "vue";
import { loadSource, mountSetup } from "./helpers/vueHarness.mjs";

function mountInput(permissionMode) {
  const component = loadSource(
    new URL("../src/components/chat/ChatInput.vue", import.meta.url),
    {
      vuetify: { useDisplay: () => ({ smAndDown: ref(false) }) },
      "@lucide/vue": {},
      "./AudioWaveform.vue": {},
      "@/i18n/composables": {
        useI18n: () => ({ t: (key) => key, locale: ref("en-US") }),
        useModuleI18n: () => ({ tm: (key) => key }),
      },
      "@/stores/customizer": { useCustomizerStore: () => ({ uiTheme: "" }) },
      "@/utils/imeInput.mjs": { isComposingEnter: () => false },
      "@/api/v1": { commandApi: { list: async () => ({ data: {} }) } },
      "./ConfigSelector.vue": {},
      "./ProviderModelMenu.vue": {},
      "@/components/shared/StyledMenu.vue": {},
      "./CommandSuggestion.vue": {},
      "./attachmentPresentation": { attachmentPresentation: () => ({}) },
    },
    {
      document: { addEventListener() {}, removeEventListener() {} },
      window: { addEventListener() {}, removeEventListener() {} },
    },
  ).default;
  return mountSetup(component, { prompt: "", permissionMode });
}

test("workspace without asking shows as workspace; choosing workspace asks again", () => {
  const h = mountInput("workspace_no_ask");
  try {
    // No separate menu item: the workspace item is the active one, and its
    // click sets plain "workspace", which asks again.
    assert.deepEqual([...h.state.MENU_MODES], ["workspace", "ask", "full"]);
    assert.equal(h.state.menuMode, "workspace");
    assert.equal(
      h.state.PERMISSION_MODE_ICONS.workspace_no_ask,
      h.state.PERMISSION_MODE_ICONS.workspace,
    );
  } finally {
    h.stop();
  }
  for (const mode of ["workspace", "ask", "full"]) {
    const other = mountInput(mode);
    try {
      assert.equal(other.state.menuMode, mode);
    } finally {
      other.stop();
    }
  }
});
