import { ref } from "vue";

const SELECTED_PROVIDER_KEY = "selectedProvider";
const SELECTED_PROVIDER_MODEL_KEY = "selectedProviderModel";

// Module-level state so every ProviderModelMenu instance (header, input)
// shares the same selection.
const selectedProviderId = ref("");
const selectedModelName = ref("");
let syncedFromStorage = false;

function syncFromStorage() {
  if (syncedFromStorage || typeof window === "undefined") return;
  syncedFromStorage = true;
  selectedProviderId.value = localStorage.getItem(SELECTED_PROVIDER_KEY) || "";
  selectedModelName.value = localStorage.getItem(SELECTED_PROVIDER_MODEL_KEY) || "";
}

export function useProviderModelSelection() {
  syncFromStorage();

  function setSelection(providerId: string, modelName = "") {
    selectedProviderId.value = providerId;
    selectedModelName.value = modelName;
    try {
      localStorage.setItem(SELECTED_PROVIDER_KEY, providerId);
      localStorage.setItem(SELECTED_PROVIDER_MODEL_KEY, modelName);
    } catch {
      // Selection persistence must not block the UI.
    }
  }

  return { selectedProviderId, selectedModelName, setSelection };
}
