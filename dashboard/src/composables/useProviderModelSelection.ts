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
  try {
    selectedProviderId.value =
      localStorage.getItem(SELECTED_PROVIDER_KEY) || "";
    selectedModelName.value = selectedProviderId.value
      ? localStorage.getItem(SELECTED_PROVIDER_MODEL_KEY) || ""
      : "";
  } catch {
    // Storage can be unavailable in restricted browser contexts.
  }
}

export function clearProviderSelectionStorage() {
  syncedFromStorage = false;
  selectedProviderId.value = "";
  selectedModelName.value = "";
  try {
    localStorage.removeItem(SELECTED_PROVIDER_KEY);
    localStorage.removeItem(SELECTED_PROVIDER_MODEL_KEY);
  } catch {
    // Selection persistence must not block the UI.
  }
}

export function useProviderModelSelection() {
  syncFromStorage();

  function setSelection(providerId: string, modelName = "") {
    if (!providerId) {
      clearProviderSelectionStorage();
      return;
    }

    selectedProviderId.value = providerId;
    selectedModelName.value = providerId ? modelName : "";
    try {
      if (providerId) {
        localStorage.setItem(SELECTED_PROVIDER_KEY, providerId);
        localStorage.setItem(SELECTED_PROVIDER_MODEL_KEY, modelName);
      } else {
        localStorage.removeItem(SELECTED_PROVIDER_KEY);
        localStorage.removeItem(SELECTED_PROVIDER_MODEL_KEY);
      }
    } catch {
      // Selection persistence must not block the UI.
    }
  }

  return {
    selectedProviderId,
    selectedModelName,
    setSelection,
    clearSelection: clearProviderSelectionStorage,
  };
}
