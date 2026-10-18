const STORAGE_KEY = "astrbot.pluginOrganizer";
const LEGACY_STORAGE_KEY = "astrbot.pluginManager.organizer.v1";

const normalizePreferences = (value) => {
  const folders = Array.isArray(value?.folders)
    ? [
        ...new Set(
          value.folders
            .filter((item) => typeof item === "string")
            .map((item) => item.trim())
            .filter(Boolean),
        ),
      ]
    : [];
  const allowedFolders = new Set(folders);
  const assignments = Object.fromEntries(
    Object.entries(value?.assignments || {}).filter(
      ([name, folder]) =>
        typeof name === "string" &&
        typeof folder === "string" &&
        allowedFolders.has(folder),
    ),
  );
  return { folders, assignments };
};

export const readPluginOrganizerPreferences = () => {
  if (typeof window === "undefined") return { folders: [], assignments: {} };
  try {
    const current = window.localStorage.getItem(STORAGE_KEY);
    const legacy = current
      ? null
      : window.localStorage.getItem(LEGACY_STORAGE_KEY);
    const preferences = normalizePreferences(
      JSON.parse(current || legacy || "{}"),
    );
    if (!current && legacy) {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(preferences));
    }
    return preferences;
  } catch {
    return { folders: [], assignments: {} };
  }
};

export const writePluginOrganizerPreferences = (value) => {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify(normalizePreferences(value)),
    );
  } catch {
    // Ignore restricted storage environments.
  }
};
