export const CHAT_PREFERENCES_KEY = "astrbot.chat.preferences";

export interface WorkbenchLayout {
  tabs: Array<{
    id: string;
    name?: string;
    title?: string;
    plugin_name?: string;
    launcher?: boolean;
  }>;
  activeId: string;
  open: boolean;
  seen?: string[];
  width?: number | null;
}

export interface ChatPreferences {
  global: {
    provider?: { providerId: string; modelName: string };
    configId?: string;
    transportMode?: string;
    sttProvider?: string;
    expandedProjectIds?: string[];
    projectsExpanded?: boolean;
    navigationInSidebar?: boolean;
    draft?: string;
    workbench?: WorkbenchLayout;
  };
  sessions: Record<
    string,
    {
      provider?: { providerId: string; modelName: string };
      draft?: string;
      workbench?: WorkbenchLayout;
    }
  >;
}

/** Read or update the current user's ChatUI preferences, migrating legacy keys once.
 *
 * Only remove old entries after the consolidated record has been written.
 * Storage failures must not prevent using ChatUI.
 */
export function chatPreferences(
  update?: (preferences: ChatPreferences) => void,
  storage?: Storage,
): ChatPreferences {
  let preferences: ChatPreferences = { global: {}, sessions: {} };
  try {
    const target = storage ?? globalThis.localStorage;
    if (!target) {
      update?.(preferences);
      return preferences;
    }
    const storedUsername = target.getItem("user")?.trim();
    const username = storedUsername || "guest";
    const raw = target.getItem(CHAT_PREFERENCES_KEY);
    let root: { version: number; users: Record<string, ChatPreferences> } = {
      version: 1,
      users: {},
    };
    try {
      const parsed = JSON.parse(raw || "null");
      if (
        parsed?.version === 1 &&
        parsed.users &&
        typeof parsed.users === "object" &&
        !Array.isArray(parsed.users)
      )
        root = parsed;
    } catch {
      /* A malformed preferences record must not break chat. */
    }
    if (Object.prototype.hasOwnProperty.call(root.users, username)) {
      const saved = root.users[username];
      if (
        saved?.global &&
        typeof saved.global === "object" &&
        !Array.isArray(saved.global) &&
        saved.sessions &&
        typeof saved.sessions === "object" &&
        !Array.isArray(saved.sessions)
      )
        preferences = saved;
    }
    // Session IDs and usernames are object keys, including in migrated data.
    preferences.sessions = Object.assign(
      Object.create(null),
      preferences.sessions,
    );
    for (const [id, value] of Object.entries(preferences.sessions)) {
      if (!value || typeof value !== "object" || Array.isArray(value))
        delete preferences.sessions[id];
    }
    root.users = Object.assign(Object.create(null), root.users);
    root.users[username] = preferences;
    const migrated: string[] = [];
    if (storedUsername) {
      const globalKeys = {
        "chat.selectedConfigId": "configId",
        "chat.transportMode": "transportMode",
        "chat.sttProvider": "sttProvider",
      } as const;
      for (const [key, field] of Object.entries(globalKeys)) {
        const value = target.getItem(key);
        if (value !== null) {
          preferences.global[field] ??= value;
          migrated.push(key);
        }
      }
      const navigation = target.getItem("chatNavigationInSidebar");
      if (navigation !== null) {
        preferences.global.navigationInSidebar ??= navigation === "true";
        migrated.push("chatNavigationInSidebar");
      }
      const expanded = target.getItem("chat.projectExpandedIds");
      if (expanded !== null) {
        try {
          const ids = JSON.parse(expanded);
          if (Array.isArray(ids))
            preferences.global.expandedProjectIds ??= ids.filter(
              (id) => typeof id === "string",
            );
        } catch {
          /* Ignore an invalid legacy expansion list. */
        }
        migrated.push("chat.projectExpandedIds");
      }
      const providerId = target.getItem("selectedProvider");
      const modelName = target.getItem("selectedProviderModel");
      if (providerId !== null || modelName !== null) {
        if (providerId)
          preferences.global.provider ??= {
            providerId,
            modelName: modelName || "",
          };
        migrated.push("selectedProvider", "selectedProviderModel");
      }
      for (let index = 0; index < target.length; index++) {
        const key = target.key(index) || "";
        if (key.startsWith("chat.sessionProvider.")) {
          const id = key.slice("chat.sessionProvider.".length);
          try {
            const value = JSON.parse(target.getItem(key) || "null");
            if (
              id &&
              typeof value?.providerId === "string" &&
              value.providerId
            ) {
              const session = (preferences.sessions[id] ||= {});
              session.provider ??= {
                providerId: value.providerId,
                modelName:
                  typeof value.modelName === "string" ? value.modelName : "",
              };
            }
          } catch {
            /* Ignore invalid legacy model selections. */
          }
          migrated.push(key);
        } else if (key.startsWith("astrbot.chat.draft.")) {
          const id = key.slice("astrbot.chat.draft.".length);
          if (id === "new")
            preferences.global.draft ??= target.getItem(key) || "";
          else if (id)
            (preferences.sessions[id] ||= {}).draft ??=
              target.getItem(key) || "";
          migrated.push(key);
        }
      }
    }
    update?.(preferences);
    if (storedUsername && (update || migrated.length)) {
      target.setItem(CHAT_PREFERENCES_KEY, JSON.stringify(root));
      for (const key of migrated) target.removeItem(key);
    }
  } catch {
    // Private mode, storage quotas, and inaccessible storage must not block chat.
  }
  return preferences;
}
