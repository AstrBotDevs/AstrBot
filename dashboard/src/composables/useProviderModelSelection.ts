import { ref } from "vue";

import { chatPreferences } from "@/utils/chatPreferences";
import { getStoredDashboardUsername } from "@/utils/chatConfigBinding";

// Module-level state so every ProviderModelMenu instance (header, input)
// shares the same selection.
const selectedProviderId = ref("");
const selectedModelName = ref("");
let syncedUser = "";

function syncFromStorage() {
  const user = getStoredDashboardUsername();
  if (syncedUser === user) return;
  syncedUser = user;
  const selection = chatPreferences().global.provider;
  selectedProviderId.value = selection?.providerId || "";
  selectedModelName.value = selection?.modelName || "";
}

export function useProviderModelSelection() {
  syncFromStorage();

  function resetSelection() {
    syncedUser = "";
    selectedProviderId.value = "";
    selectedModelName.value = "";
  }

  function setSelection(providerId: string, modelName = "") {
    selectedProviderId.value = providerId;
    selectedModelName.value = providerId ? modelName : "";
    chatPreferences((preferences) => {
      if (providerId) preferences.global.provider = { providerId, modelName };
      else delete preferences.global.provider;
    });
  }

  return {
    selectedProviderId,
    selectedModelName,
    setSelection,
    resetSelection,
  };
}
