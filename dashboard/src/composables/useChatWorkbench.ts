import { computed, provide, reactive, type Ref } from "vue";
import {
  workbenchKey,
  type WorkbenchView,
  type WorkbenchTab,
} from "@/utils/chatViews";

/** Keep tabs and dismissed views isolated to the conversation that owns them. */
export function useChatWorkbench(sessionId: Ref<string>) {
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
  >({});
  const pages = reactive<WorkbenchTab[]>([]);
  const pageState = reactive({ activeId: "", open: false });
  const state = computed(() => {
    const current = sessions[sessionId.value];
    if (!current && !pages.length) return undefined;
    return {
      tabs: [...pages, ...(current?.tabs || [])],
      get activeId() {
        return pageState.activeId || current?.activeId || "";
      },
      set activeId(id: string) {
        pageState.activeId = pages.some((tab) => String(tab.part.id) === id)
          ? id
          : "";
        if (!pageState.activeId && current) current.activeId = id;
      },
      get open() {
        return pageState.activeId ? pageState.open : current?.open || false;
      },
      set open(value: boolean) {
        pageState.open = value;
        if (current) current.open = value;
      },
    };
  });

  function openPage(page?: WorkbenchView) {
    const id = page ? `page:${page.plugin_name}:${page.name}` : "workbench:new";
    if (!pages.some((tab) => String(tab.part.id) === id)) {
      const tab: WorkbenchTab = {
        part: { type: "view", id, title: page?.title || "" },
        page,
        launcher: !page,
      };
      const launcherIndex = pages.findIndex((tab) => tab.launcher);
      if (page && launcherIndex >= 0) pages.splice(launcherIndex, 1, tab);
      else pages.push(tab);
    }
    pageState.activeId = id;
    pageState.open = true;
  }

  provide(workbenchKey, {
    open(part, action, automatic = false) {
      if (!sessionId.value) return;
      const current = (sessions[sessionId.value] ||= {
        tabs: [],
        activeId: "",
        open: false,
        seen: new Set(),
      });
      const id = String(part.id);
      if (automatic && current.seen.has(id)) return;
      current.seen.add(id);
      if (!current.tabs.some((tab) => String(tab.part.id) === id)) {
        current.tabs.push({ part, action });
      }
      pageState.activeId = "";
      current.activeId = id;
      current.open = true;
    },
  });

  function closeTab(id: string) {
    const pageIndex = pages.findIndex((tab) => String(tab.part.id) === id);
    if (pageIndex >= 0) {
      pages.splice(pageIndex, 1);
      if (pageState.activeId === id)
        pageState.activeId = String(
          pages[Math.min(pageIndex, pages.length - 1)]?.part.id || "",
        );
      if (!pages.length) pageState.open = false;
      return;
    }
    const current = sessions[sessionId.value];
    if (!current) return;
    const index = current.tabs.findIndex((tab) => String(tab.part.id) === id);
    if (index < 0) return;
    current.tabs.splice(index, 1);
    if (current.activeId === id) {
      current.activeId = String(
        current.tabs[Math.min(index, current.tabs.length - 1)]?.part.id || "",
      );
    }
    if (!current.tabs.length) {
      current.open = false;
      if (pages.length) {
        pageState.activeId = String(pages[0].part.id);
        pageState.open = true;
      }
    }
  }

  return { state, closeTab, openPage };
}
