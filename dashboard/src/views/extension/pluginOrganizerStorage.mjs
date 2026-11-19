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

const parsePreferences = (raw) => {
  if (typeof raw !== "string") return null;
  try {
    const value = JSON.parse(raw);
    if (
      !value ||
      typeof value !== "object" ||
      Array.isArray(value) ||
      !Array.isArray(value.folders) ||
      !value.assignments ||
      typeof value.assignments !== "object" ||
      Array.isArray(value.assignments)
    ) {
      return null;
    }
    return normalizePreferences(value);
  } catch {
    return null;
  }
};

export const readPluginOrganizerPreferences = () => {
  const emptyPreferences = { folders: [], assignments: {} };
  if (typeof window === "undefined") return emptyPreferences;

  try {
    const current = parsePreferences(window.localStorage.getItem(STORAGE_KEY));
    if (current) return current;

    const legacy = parsePreferences(
      window.localStorage.getItem(LEGACY_STORAGE_KEY),
    );
    if (!legacy) return emptyPreferences;

    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(legacy));
    } catch {
      // Keep using the legacy preferences if migration cannot be persisted.
    }
    return legacy;
  } catch {
    return emptyPreferences;
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
