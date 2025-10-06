import { ref } from 'vue';

const LOCAL_KEY = 'sidebarCollapsed';

export function useSidebarState() {
  const sidebarCollapsed = ref(true);
  const sidebarHovered = ref(false);
  const sidebarHoverExpanded = ref(false);
  const sidebarHoverTimer = ref<number | null>(null);
  const sidebarHoverDelay = ref(100);

  // init from localStorage
  const saved = localStorage.getItem(LOCAL_KEY);
  if (saved !== null) sidebarCollapsed.value = JSON.parse(saved);

  function save() {
    localStorage.setItem(LOCAL_KEY, JSON.stringify(sidebarCollapsed.value));
  }

  function toggleSidebar() {
    if (sidebarHoverExpanded.value) {
      sidebarHoverExpanded.value = false;
      return;
    }
    sidebarCollapsed.value = !sidebarCollapsed.value;
    save();
  }

  function handleSidebarMouseEnter() {
    if (!sidebarCollapsed.value) return;
    sidebarHovered.value = true;
    sidebarHoverTimer.value = window.setTimeout(() => {
      if (sidebarHovered.value) {
        sidebarHoverExpanded.value = true;
        sidebarCollapsed.value = false;
      }
    }, sidebarHoverDelay.value);
  }

  function handleSidebarMouseLeave() {
    sidebarHovered.value = false;
    if (sidebarHoverTimer.value) {
      clearTimeout(sidebarHoverTimer.value);
      sidebarHoverTimer.value = null;
    }
    if (sidebarHoverExpanded.value) {
      sidebarCollapsed.value = true;
    }
    sidebarHoverExpanded.value = false;
  }

  function dispose() {
    if (sidebarHoverTimer.value) clearTimeout(sidebarHoverTimer.value);
  }

  return {
    sidebarCollapsed,
    sidebarHovered,
    sidebarHoverExpanded,
    sidebarHoverTimer,
    sidebarHoverDelay,
    toggleSidebar,
    handleSidebarMouseEnter,
    handleSidebarMouseLeave,
    dispose,
  };
}
