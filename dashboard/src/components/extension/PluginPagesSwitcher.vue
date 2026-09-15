<script setup>
import { computed, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useModuleI18n } from "@/i18n/composables";
import { usePluginI18n } from "@/utils/pluginI18n";

const props = defineProps({
  plugins: { type: Array, required: true },
});

const route = useRoute();
const router = useRouter();
const { tm } = useModuleI18n("features/extension");
const { pluginName } = usePluginI18n();

const expanded = ref(false);

// Activated plugins that ship web pages; disabled ones are hidden since their
// pages cannot be opened anyway.
const pagePlugins = computed(() =>
  props.plugins.filter(
    (plugin) =>
      plugin.activated && Array.isArray(plugin?.pages) && plugin.pages.length > 0,
  ),
);

const openPluginPage = (plugin, event) => {
  const pages = plugin?.pages;
  if (!Array.isArray(pages) || pages.length === 0 || !plugin?.name) return;
  if (!plugin.activated) return;

  const openInNewTab =
    event.button === 1 || event.ctrlKey || event.metaKey || event.shiftKey;

  if (event.type === "auxclick" && !openInNewTab) {
    // Right-click (button === 2): leave the native context menu alone.
    return;
  }

  if (openInNewTab) {
    const url = router.resolve({
      name: "ExtensionPluginPages",
      params: { pluginName: plugin.name, pageName: pages[0] },
    }).href;
    window.open(url, "_blank", "noopener");
    return;
  }

  router.push({
    name: "ExtensionPluginPages",
    params: { pluginName: plugin.name, pageName: pages[0] },
  });
};

// Suppress the browser's native middle-click autoscroll indicator so the
// custom middle-click new-tab behavior is the only effect.
const onMouseDown = (event) => {
  if (event.button === 1) event.preventDefault();
};

// Convert vertical wheel input into horizontal scrolling for the switcher row,
// so a mouse wheel can sweep through many plugin entries. Once the row hits
// either end the wheel falls through to the page's vertical scroll again.
const onWheel = (event) => {
  const el = event.currentTarget;
  if (el.scrollWidth <= el.clientWidth) return;

  const delta = event.deltaMode === 1 ? event.deltaY * 16 : event.deltaY;
  const maxScroll = el.scrollWidth - el.clientWidth;
  const canScroll =
    (delta < 0 && el.scrollLeft > 0) || (delta > 0 && el.scrollLeft < maxScroll);
  if (!canScroll) return;

  event.preventDefault();
  el.scrollLeft += delta;
};
</script>

<template>
  <div
    v-if="pagePlugins.length > 0"
    class="plugin-pages-switcher"
    @mousedown="onMouseDown"
  >
    <div
      class="plugin-pages-switcher__list"
      :class="{ 'plugin-pages-switcher__list--expanded': expanded }"
      @wheel="onWheel"
    >
      <button
        v-for="plugin in pagePlugins"
        :key="plugin.name"
        type="button"
        class="plugin-pages-switcher__item"
        :class="{
          'plugin-pages-switcher__item--active':
            plugin.name === route.params.pluginName,
        }"
        @click="openPluginPage(plugin, $event)"
        @auxclick="openPluginPage(plugin, $event)"
      >
        {{ pluginName(plugin) }}
      </button>
    </div>

    <button
      type="button"
      class="plugin-pages-switcher__toggle"
      :title="expanded ? tm('buttons.collapse') : tm('buttons.expand')"
      :aria-label="expanded ? tm('buttons.collapse') : tm('buttons.expand')"
      :aria-expanded="expanded"
      @click="expanded = !expanded"
    >
      <v-icon
        :icon="expanded ? 'mdi-chevron-up' : 'mdi-chevron-down'"
        size="small"
      />
    </button>
  </div>
</template>

<style scoped>
/* Horizontal navigation row of every plugin that ships web pages. Collapsed
   it scrolls horizontally (hidden scrollbar like the workspace tab strip);
   expanded it wraps and shows every entry at once. */
.plugin-pages-switcher {
  align-items: center;
  display: flex;
  flex-shrink: 0;
  gap: 6px;
  padding: 8px 0;
}

.plugin-pages-switcher__list {
  align-items: center;
  display: flex;
  flex: 1;
  gap: 6px;
  min-width: 0;
  overflow-x: auto;
  scrollbar-width: none;
}

.plugin-pages-switcher__list::-webkit-scrollbar {
  display: none;
}

.plugin-pages-switcher__list--expanded {
  flex-wrap: wrap;
  overflow: visible;
}

.plugin-pages-switcher__item {
  align-items: center;
  background: transparent;
  border: 0;
  border-radius: 8px;
  color: rgba(var(--v-theme-on-surface), 0.58);
  cursor: pointer;
  display: inline-flex;
  flex-shrink: 0;
  font-size: 0.8125rem;
  font-weight: 500;
  height: 30px;
  padding: 0 12px;
  white-space: nowrap;
}

.plugin-pages-switcher__item:hover {
  background: rgba(var(--v-theme-on-surface), 0.045);
  color: rgba(var(--v-theme-on-surface), 0.78);
}

.plugin-pages-switcher__item--active {
  background: rgba(var(--v-theme-on-surface), 0.065);
  color: rgba(var(--v-theme-on-surface), 0.86);
}

.plugin-pages-switcher__toggle {
  align-items: center;
  background: transparent;
  border: 0;
  border-radius: 8px;
  color: rgba(var(--v-theme-on-surface), 0.58);
  cursor: pointer;
  display: inline-flex;
  flex-shrink: 0;
  height: 30px;
  justify-content: center;
  width: 30px;
}

.plugin-pages-switcher__toggle:hover {
  background: rgba(var(--v-theme-on-surface), 0.045);
  color: rgba(var(--v-theme-on-surface), 0.78);
}
</style>
