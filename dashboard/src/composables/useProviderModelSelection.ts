import { ref } from "vue";
import {
  SELECTED_PROVIDER_KEY,
  SELECTED_PROVIDER_MODEL_KEY,
  clearProviderSelectionStorage,
} from "@/utils/providerSelectionStorage.mjs";

// Module-level state so every ProviderModelMenu instance (header, input)
// shares the same selection.
const selectedProviderId = ref("");
const selectedModelName = ref("");
let syncedFromStorage = false;

function syncFromStorage() {
  if (syncedFromStorage || typeof window === "undefined") return;
  syncedFromStorage = true;
  selectedProviderId.value = localStorage.getItem(SELECTED_PROVIDER_KEY) || "";
  selectedModelName.value =
    localStorage.getItem(SELECTED_PROVIDER_MODEL_KEY) || "";
}

export function useProviderModelSelection() {
  syncFromStorage();

  function setSelection(providerId: string, modelName = "") {
    selectedProviderId.value = providerId;
    selectedModelName.value = modelName;
    if (!providerId) {
      clearProviderSelectionStorage(localStorage);
      return;
    }
    try {
      localStorage.setItem(SELECTED_PROVIDER_KEY, providerId);
      localStorage.setItem(SELECTED_PROVIDER_MODEL_KEY, modelName);
    } catch {
      // Selection persistence must not block the UI.
    }
  }

  return { selectedProviderId, selectedModelName, setSelection };
}
