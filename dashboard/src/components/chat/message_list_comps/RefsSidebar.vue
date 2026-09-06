<template>
  <transition name="chat-panel">
    <div v-if="isOpen" class="refs-sidebar chat-side-panel">
      <div class="sidebar-header">
        <h3 class="sidebar-title">{{ tm("refs.title") }}</h3>
        <v-btn
          icon="mdi-close"
          size="small"
          variant="text"
          @click="close"
        ></v-btn>
      </div>

      <div class="refs-list">
        <div
          v-for="(ref, index) in normalizedRefs"
          :key="ref.index || index"
          class="ref-item"
          @click="openLink(ref.url)"
        >
          <div class="ref-item-icon">
            <img
              v-if="ref.favicon"
              :src="ref.favicon"
              class="ref-item-favicon"
              @error="handleImgError"
            />
            <div v-else class="ref-item-initial">
              {{ getRefInitial(ref.title) }}
            </div>
          </div>
          <div class="ref-item-content">
            <div class="ref-item-title">{{ ref.title }}</div>
            <div class="ref-item-url">{{ formatUrl(ref.url) }}</div>
            <div v-if="ref.snippet" class="ref-item-snippet">
              {{ ref.snippet }}
            </div>
          </div>
          <v-icon size="small" class="ref-item-arrow">mdi-open-in-new</v-icon>
        </div>
      </div>
    </div>
  </transition>
</template>

<script lang="ts">
import "@/components/chat/chatPanelTransition.css";
import { defineComponent, type PropType } from "vue";
import { useModuleI18n } from "@/i18n/composables";

interface Reference {
  index?: string | number;
  title?: string;
  url?: string;
  snippet?: string;
  favicon?: string;
}

export default defineComponent({
  name: "RefsSidebar",
  props: {
    modelValue: {
      type: Boolean,
      default: false,
    },
    refs: {
      type: [Object, Array] as PropType<{ used?: Reference[] } | Reference[] | null>,
      default: null,
    },
  },
  emits: ["update:modelValue"],
  setup() {
    const { tm } = useModuleI18n("features/chat");
    return { tm };
  },
  computed: {
    isOpen: {
      get() {
        return this.modelValue;
      },
      set(value: boolean) {
        this.$emit("update:modelValue", value);
      },
    },
    normalizedRefs() {
      const refs = this.refs;
      const used = Array.isArray(refs) ? refs : refs?.used || [];
      return used
        .map(ref => ({ ...ref, title: ref.title || ref.url || "Reference" }))
        .filter((ref): ref is Reference & { url: string; title: string } => Boolean(ref.url));
    },
  },
  methods: {
    handleImgError(e: Event): void {
      const el = e.target as HTMLElement;
      if (el) el.style.display = "none";
    },

    close(): void {
      this.isOpen = false;
    },

    getRefInitial(title: string): string {
      if (!title) return "?";
      return title.charAt(0).toUpperCase();
    },

    formatUrl(url: string): string {
      if (!url) return "";
      try {
        const urlObj = new URL(url);
        return urlObj.hostname;
      } catch {
        return url;
      }
    },

    openLink(url: string): void {
      if (url) {
        window.open(url, "_blank");
      }
    },
  },
});
</script>

<style scoped>
.refs-sidebar {
  --chat-side-panel-width: 360px;
  width: var(--chat-side-panel-width);
  height: calc(100% - var(--chat-panel-top-offset, 0px));
  margin-top: var(--chat-panel-top-offset, 0px);
  background: var(--chat-page-bg, rgb(var(--v-theme-surface)));
  border-left: 1px solid var(--chat-border, rgba(var(--v-border-color), 0.16));
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}

.sidebar-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 16px 8px;
  flex-shrink: 0;
}

.sidebar-title {
  font-size: 16px;
  font-weight: 600;
  color: rgb(var(--v-theme-on-surface));
  line-height: 1.4;
  margin: 0;
}

.refs-list {
  padding: 12px;
  padding-top: 0;
  overflow-y: auto;
  flex: 1;
}

.ref-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 12px;
  margin-bottom: 8px;
  border-radius: 8px;
  border: 1px solid var(--v-theme-border);
  cursor: pointer;
  transition: all 0.2s ease;
}

.ref-item:hover {
  background-color: rgba(103, 58, 183, 0.05);
  border-color: rgba(103, 58, 183, 0.3);
}

.ref-item-icon {
  flex-shrink: 0;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
}

.ref-item-favicon {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.ref-item-initial {
  font-size: 14px;
  font-weight: 600;
  color: white;
}

.ref-item-content {
  flex: 1;
  min-width: 0;
}

.ref-item-title {
  font-size: 14px;
  font-weight: 500;
  color: var(--v-theme-primaryText);
  margin-bottom: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.ref-item-url {
  font-size: 12px;
  color: var(--v-theme-secondaryText);
  opacity: 0.7;
  margin-bottom: 6px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ref-item-snippet {
  font-size: 12px;
  color: var(--v-theme-secondaryText);
  opacity: 0.8;
  line-height: 1.5;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
}

.ref-item-arrow {
  flex-shrink: 0;
  margin-top: 4px;
  color: var(--v-theme-secondaryText);
  opacity: 0.5;
  transition: opacity 0.2s ease;
}

.ref-item:hover .ref-item-arrow {
  opacity: 1;
}

@media (max-width: 760px) {
  .refs-sidebar {
    position: fixed;
    inset: 0;
    z-index: 1300;
    width: 100vw;
    height: 100dvh;
    margin-top: 0;
    border-left: 0;
  }
}
</style>
