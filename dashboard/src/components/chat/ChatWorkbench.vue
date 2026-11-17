<template>
  <Transition name="chat-panel" @after-leave="expanded = false">
    <aside
      v-show="open"
      ref="panel"
      class="chat-workbench chat-side-panel"
      :class="{ expanded, resizing }"
      :aria-label="tm('workbench.title')"
      @keydown.esc="expanded ? (expanded = false) : emit('close')"
    >
      <div
        v-if="!expanded && !smAndDown"
        class="workbench-resize-handle"
        role="separator"
        tabindex="0"
        aria-orientation="vertical"
        :aria-label="tm('workbench.resize')"
        :aria-valuenow="Math.round(panel?.getBoundingClientRect().width || 0)"
        aria-valuemin="320"
        :aria-valuemax="Math.max(320, (panel?.parentElement?.clientWidth || 640) - 320)"
        @pointerdown="startResize"
        @pointermove="resizePanel"
        @pointerup="resizing = false"
        @pointercancel="resizing = false"
        @lostpointercapture="resizing = false"
        @keydown.left.prevent="resizeByKeyboard(24)"
        @keydown.right.prevent="resizeByKeyboard(-24)"
      />
      <Teleport
        :to="headerTarget || 'body'"
        :disabled="!headerTarget || expanded || smAndDown"
      >
        <header v-if="open" class="workbench-header">
          <div
            class="workbench-tabs hidden-scrollbar"
            role="tablist"
            :aria-label="tm('workbench.title')"
          >
            <div
              v-for="tab in tabs"
              :key="String(tab.part.id)"
              class="workbench-tab"
              :class="{ active: String(tab.part.id) === activeId }"
            >
              <button
                :id="`workbench-tab-${tab.part.id}`"
                type="button"
                role="tab"
                :aria-selected="String(tab.part.id) === activeId"
                :aria-controls="`workbench-panel-${tab.part.id}`"
                :tabindex="String(tab.part.id) === activeId ? 0 : -1"
                :title="
                  String(
                    tab.launcher
                      ? tm('workbench.newTab')
                      : tab.part.title || tab.part.name,
                  )
                "
                @click="emit('select', String(tab.part.id))"
                @keydown="navigateTabs($event, String(tab.part.id))"
              >
                <File :size="15" :stroke-width="1.6" />
                <span>{{
                  tab.launcher
                    ? tm("workbench.newTab")
                    : tab.part.title || tab.part.name
                }}</span>
              </button>
              <button
                type="button"
                class="close-tab"
                :aria-label="
                  tm('workbench.closeTab', {
                    title: String(
                      tab.launcher
                        ? tm('workbench.newTab')
                        : tab.part.title || tab.part.name,
                    ),
                  })
                "
                @click="emit('close-tab', String(tab.part.id))"
              >
                <X :size="14" />
              </button>
            </div>
          </div>
          <div class="workbench-controls">
            <button
              type="button"
              :title="tm('workbench.newTab')"
              :aria-label="tm('workbench.newTab')"
              @click="emit('new-tab')"
            >
              <Plus :size="18" />
            </button>
            <button
              type="button"
              :aria-label="
                tm(expanded ? 'workbench.restore' : 'workbench.expand')
              "
              :title="tm(expanded ? 'workbench.restore' : 'workbench.expand')"
              @click="expanded = !expanded"
            >
              <Minimize2 v-if="expanded" :size="16" /><Maximize2
                v-else
                :size="16"
              />
            </button>
            <button
              type="button"
              :aria-label="tm('workbench.hide')"
              :title="tm('workbench.hide')"
              @click="emit('close')"
            >
              <PanelRightClose :size="18" />
            </button>
          </div>
        </header>
      </Teleport>
      <div
        v-for="tab in tabs"
        v-show="String(tab.part.id) === activeId"
        :id="`workbench-panel-${tab.part.id}`"
        :key="String(tab.part.id)"
        class="workbench-content"
        role="tabpanel"
        :aria-labelledby="`workbench-tab-${tab.part.id}`"
      >
        <WorkbenchLauncher
          v-if="tab.launcher"
          @open="emit('open-page', $event)"
        />
        <PluginViewFrame
          v-else-if="tab.page"
          :plugin-id="tab.page.plugin_name"
          :view-name="tab.page.name"
          target="chat_workbench"
          :session-id="sessionId"
        />
        <PluginViewCard
          v-else
          :part="tab.part"
          :is-dark="isDark"
          :action-handler="tab.action"
          workbench
        />
      </div>
    </aside>
  </Transition>
</template>

<script setup lang="ts">
import { nextTick, ref, watch } from "vue";
import "./chatPanelTransition.css";
import { useDisplay } from "vuetify";
import {
  File,
  Maximize2,
  Minimize2,
  PanelRightClose,
  Plus,
  X,
} from "@lucide/vue";
import { useModuleI18n } from "@/i18n/composables";
import type { WorkbenchTab, WorkbenchView } from "@/utils/chatViews";
import WorkbenchLauncher from "./WorkbenchLauncher.vue";
import PluginViewFrame from "@/components/plugins/PluginViewFrame.vue";
import PluginViewCard from "./message_list_comps/PluginViewCard.vue";

const props = withDefaults(
  defineProps<{
    tabs: WorkbenchTab[];
    activeId: string;
    isDark: boolean;
    headerTarget?: string;
    sessionId?: string;
    open?: boolean;
  }>(),
  { open: true },
);
const emit = defineEmits<{
  select: [id: string];
  "close-tab": [id: string];
  close: [];
  resize: [width: number];
  "new-tab": [];
  "open-page": [view: WorkbenchView];
}>();
const expanded = ref(false);
const resizing = ref(false);
const panel = ref<HTMLElement>();
let resizeStartX = 0;
let resizeStartWidth = 0;
let resizeMaxWidth = 0;

function startResize(event: PointerEvent) {
  if (event.button !== 0 || !panel.value) return;
  event.preventDefault();
  resizeStartX = event.clientX;
  resizeStartWidth = panel.value.getBoundingClientRect().width;
  resizeMaxWidth = Math.max(
    320,
    (panel.value.parentElement?.clientWidth || 640) - 320,
  );
  resizing.value = true;
  (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
}

function resizePanel(event: PointerEvent) {
  if (!resizing.value) return;
  emit(
    "resize",
    Math.round(
      Math.min(
        resizeMaxWidth,
        Math.max(320, resizeStartWidth + resizeStartX - event.clientX),
      ),
    ),
  );
}

function resizeByKeyboard(delta: number) {
  if (!panel.value) return;
  const max = Math.max(
    320,
    (panel.value.parentElement?.clientWidth || 640) - 320,
  );
  emit(
    "resize",
    Math.round(
      Math.min(
        max,
        Math.max(320, panel.value.getBoundingClientRect().width + delta),
      ),
    ),
  );
}
const { smAndDown } = useDisplay();
const { tm } = useModuleI18n("features/chat");
watch(() => props.activeId, async (id) => {
  await nextTick();
  document.getElementById(`workbench-tab-${id}`)?.scrollIntoView({ block: "nearest", inline: "nearest" });
});

async function navigateTabs(event: KeyboardEvent, id: string) {
  if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
  event.preventDefault();
  const index = props.tabs.findIndex((tab) => String(tab.part.id) === id);
  const next =
    event.key === "Home"
      ? 0
      : event.key === "End"
      ? props.tabs.length - 1
      : (index + (event.key === "ArrowRight" ? 1 : -1) + props.tabs.length) %
        props.tabs.length;
  const nextId = String(props.tabs[next].part.id);
  emit("select", nextId);
  await nextTick();
  document.getElementById(`workbench-tab-${nextId}`)?.focus();
}
</script>

<style scoped>
.chat-workbench {
  --chat-side-panel-width: var(
    --astrbot-workbench-width,
    clamp(360px, 44vw, 780px)
  );
  width: var(--chat-side-panel-width);
  height: 100%;
  position: relative;
  min-height: 0;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  border-left: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  background: var(--chat-page-bg, rgb(var(--v-theme-background)));
  color: rgb(var(--v-theme-on-surface));
}
.chat-workbench.expanded {
  position: fixed;
  inset: 0;
  width: 100%;
  height: 100dvh;
  z-index: 2400;
}
.workbench-header {
  display: flex;
  align-items: center;
  flex-shrink: 0;
  min-width: 0;
  height: var(--astrbot-toolbar-height, 42px);
  padding: 4px 8px;
  gap: 8px;
  color: rgb(var(--v-theme-on-surface));
  -webkit-app-region: no-drag;
}
.workbench-controls {
  display: flex;
  flex-shrink: 0;
  gap: 4px;
}
button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: inherit;
  cursor: pointer;
  border: 0;
  background: transparent;
  border-radius: var(--astrbot-radius-control);
}
button:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: -2px;
}
.workbench-controls button {
  width: 30px;
  height: 30px;
}
.workbench-controls button:hover,
.close-tab:hover {
  background: rgba(var(--v-theme-on-surface), 0.08);
}
.workbench-tabs {
  display: flex;
  gap: 4px;
  min-width: 0;
  flex: 1;
  overflow-x: auto;
}
.workbench-tab {
  display: flex;
  align-items: center;
  gap: 2px;
  min-width: 90px;
  max-width: 220px;
  flex-shrink: 0;
  border-radius: var(--astrbot-radius-control);
  padding: 0 4px;
  opacity: 0.65;
}
.workbench-tab.active {
  background: rgba(var(--v-theme-on-surface), 0.07);
  opacity: 1;
}
.workbench-tab [role="tab"] {
  gap: 8px;
  padding: 6px 5px;
  min-width: 0;
  font: inherit;
  font-size: 13px;
}
.workbench-tab [role="tab"] svg {
  flex-shrink: 0;
}
.workbench-tab [role="tab"] span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.close-tab {
  width: 24px;
  height: 24px;
  flex-shrink: 0;
}
.workbench-content {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
.workbench-resize-handle {
  position: absolute;
  inset: 0 auto 0 -3px;
  width: 7px;
  z-index: 2;
  cursor: col-resize;
  touch-action: none;
}
.workbench-resize-handle::after {
  content: "";
  position: absolute;
  inset: 0 2px;
  background: rgb(var(--v-theme-primary));
  opacity: 0;
  transition: opacity 150ms ease;
}
.workbench-resize-handle:hover::after,
.workbench-resize-handle:focus-visible::after,
.resizing .workbench-resize-handle::after {
  opacity: 0.5;
}
.resizing {
  user-select: none;
}
.resizing :deep(iframe) {
  pointer-events: none;
}
.chat-workbench.expanded.chat-panel-enter-active,
.chat-workbench.expanded.chat-panel-leave-active {
  transition: transform 320ms cubic-bezier(0.22, 1, 0.36, 1);
}
.chat-workbench.expanded.chat-panel-enter-from,
.chat-workbench.expanded.chat-panel-leave-to {
  margin-inline-end: 0;
  transform: translateX(100%);
}
@media (max-width: 959.98px) {
  .chat-workbench {
    position: fixed;
    inset: 0;
    width: 100%;
    height: 100dvh;
    z-index: 2400;
    border: 0;
  }
  .chat-workbench.chat-panel-enter-active,
  .chat-workbench.chat-panel-leave-active {
    transition: transform 320ms cubic-bezier(0.22, 1, 0.36, 1);
  }
  .chat-workbench.chat-panel-enter-from,
  .chat-workbench.chat-panel-leave-to {
    margin-inline-end: 0;
    transform: translateX(100%);
  }
}
@media (prefers-reduced-motion: reduce) {
  .chat-workbench.chat-panel-enter-active,
  .chat-workbench.chat-panel-leave-active,
  .workbench-resize-handle::after {
    transition: none;
  }
}
</style>
