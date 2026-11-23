import { computed, provide, type Ref, reactive, ref, watch } from "vue";
import { getStoredDashboardUsername } from "@/utils/chatConfigBinding";

import { chatPreferences, ensureSessionPreferences, type WorkbenchLayout } from "@/utils/chatPreferences";
import { type WorkbenchTab, type WorkbenchView, workbenchKey } from "@/utils/chatViews";

/** Keep tabs and dismissed views isolated to the conversation that owns them. */
export function useChatWorkbench(sessionId: Ref<string>, width: Ref<number | null> = ref(null)) {
  const sessions = reactive<
    Record<
      string,
      {
        tabs: WorkbenchTab[];
        activeId: string;
        open: boolean;
        seen: Set<string>;
      }
    >
  >(Object.create(null));
  const owner = getStoredDashboardUsername();
  const saved = chatPreferences();
  const globalLayout = saved.global.workbench;
  width.value =
    typeof globalLayout?.width === "number" && Number.isFinite(globalLayout.width)
      ? Math.max(320, Math.min(2000, globalLayout.width))
      : null;
  const layouts: Array<[string, WorkbenchLayout | undefined]> = [
    ["", globalLayout],
    ...Object.entries(saved.sessions).map(
      ([id, value]) => [id, value?.workbench] as [string, WorkbenchLayout | undefined],
    ),
  ];
  for (const [id, layout] of layouts) {
    if (!layout || !Array.isArray(layout.tabs)) continue;
    const tabs: WorkbenchTab[] = [];
    for (const tab of layout.tabs) {
      if (!tab || typeof tab.id !== "string" || !tab.id || tabs.some((item) => item.part.id === tab.id)) continue;
      const title = typeof tab.title === "string" ? tab.title : "";
      const name = typeof tab.name === "string" ? tab.name : "";
      if (tab.launcher && tab.id === "workbench:new") {
        tabs.push({ part: { type: "view", id: tab.id }, launcher: true });
      } else if (
        typeof tab.plugin_name === "string" &&
        tab.plugin_name &&
        name &&
        tab.id === `page:${tab.plugin_name}:${name}`
      ) {
        tabs.push({
          part: { type: "view", id: tab.id, title },
          page: {
            plugin_name: tab.plugin_name,
            name,
            title,
            display_name: "",
            description: "",
          },
        });
      } else if (!tab.launcher && !tab.plugin_name) {
        tabs.push({
          part: {
            type: "view",
            target: "chat_workbench",
            id: tab.id,
            name,
            title,
          },
        });
      }
    }
    const activeId = tabs.some((tab) => tab.part.id === layout.activeId)
      ? layout.activeId
      : String(tabs[0]?.part.id || "");
    // The empty session owns the new-chat workspace, including legacy global tabs.
    sessions[id] = {
      tabs,
      activeId,
      open: layout.open === true,
      seen: new Set([
        ...tabs.map((tab) => String(tab.part.id)),
        ...(Array.isArray(layout.seen) ? layout.seen.filter((value) => typeof value === "string") : []),
      ]),
    };
  }
  sessions[""] ||= { tabs: [], activeId: "", open: false, seen: new Set() };

  const previousLayouts = new Map(layouts.map(([id, layout]) => [id, JSON.stringify(layout)]));
  watch(
    [sessions, width],
    () => {
      if (getStoredDashboardUsername() !== owner) return;
      chatPreferences((preferences) => {
        for (const [id, current] of Object.entries(sessions)) {
          const layout: WorkbenchLayout = {
            tabs: current.tabs.map((tab) => ({
              id: String(tab.part.id),
              name: tab.page?.name || String(tab.part.name || ""),
              title: String(tab.part.title || ""),
              ...(tab.page ? { plugin_name: tab.page.plugin_name } : {}),
              ...(tab.launcher ? { launcher: true } : {}),
            })),
            activeId: current.activeId,
            open: current.open,
            seen: [...current.seen],
            ...(id === "" ? { width: width.value } : {}),
          };
          const serialized = JSON.stringify(layout);
          if (serialized !== previousLayouts.get(id)) {
            if (id === "") preferences.global.workbench = layout;
            else ensureSessionPreferences(preferences, id).workbench = layout;
            previousLayouts.set(id, serialized);
          }
        }
      });
    },
    { deep: true },
  );
  const state = computed(() => sessions[sessionId.value]);

  function ensureSession() {
    sessions[sessionId.value] ||= { tabs: [], activeId: "", open: false, seen: new Set() };
    return sessions[sessionId.value];
  }

  function openPage(page?: WorkbenchView) {
    const current = ensureSession();
    const id = page ? `page:${page.plugin_name}:${page.name}` : "workbench:new";
    if (!current.tabs.some((tab) => String(tab.part.id) === id)) {
      const tab: WorkbenchTab = {
        part: { type: "view", id, title: page?.title || "" },
        page,
        launcher: !page,
      };
      const launcherIndex = current.tabs.findIndex((tab) => tab.launcher);
      if (page && launcherIndex >= 0) current.tabs.splice(launcherIndex, 1, tab);
      else current.tabs.push(tab);
    }
    current.activeId = id;
    current.open = true;
  }

  provide(workbenchKey, {
    open(part, action, automatic) {
      if (!sessionId.value) return;
      const current = ensureSession();
      const id = String(part.id);
      const existing = current.tabs.find((tab) => String(tab.part.id) === id);
      if (existing) {
        existing.part = part;
        existing.action = action;
      }
      if (automatic === "history" || (automatic === "live" && current.seen.has(id))) {
        current.seen.add(id);
        return;
      }
      current.seen.add(id);
      if (!existing) current.tabs.push({ part, action });
      current.activeId = id;
      current.open = true;
    },
  });

  function closeTab(id: string) {
    const current = sessions[sessionId.value];
    if (!current) return;
    const index = current.tabs.findIndex((tab) => String(tab.part.id) === id);
    if (index < 0) return;
    current.tabs.splice(index, 1);
    if (current.activeId === id) {
      current.activeId = String(current.tabs[Math.min(index, current.tabs.length - 1)]?.part.id || "");
    }
    if (!current.tabs.length) current.open = false;
  }

  return { state, closeTab, openPage };
}
