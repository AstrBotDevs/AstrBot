<template>
  <div style="margin-top: 16px">
    <v-btn
      color="primary"
      variant="outlined"
      size="small"
      style="margin-bottom: 8px"
      @click="openDialog"
    >
      {{ t("features.settings.sidebar.customize.title") }}
    </v-btn>

    <v-dialog v-model="dialog" max-width="700px">
      <v-card>
        <v-card-title class="text-h3 pa-4 pb-0 pl-6 d-flex justify-space-between align-center">
          <span>{{ t("features.settings.sidebar.customize.title") }}</span>
          <v-btn icon="mdi-close" variant="text" @click="dialog = false" />
        </v-card-title>

        <v-card-text>
          <p class="text-body-2 mb-4">
            {{ t("features.settings.sidebar.customize.subtitle") }}
          </p>

          <v-row>
            <v-col cols="12" md="6">
              <div class="mb-2 font-weight-medium">
                {{ t("features.settings.sidebar.customize.mainItems") }}
              </div>
              <v-list
                density="compact"
                class="custom-list"
                @dragover.prevent
                @drop="handleDropToList($event, 'main')"
              >
                <v-list-item
                  v-for="(item, index) in mainItems"
                  :key="item.title"
                  class="mb-1 draggable-item"
                  draggable="true"
                  @dragstart="handleDragStart($event, 'main', index)"
                  @dragover.prevent
                  @drop.stop="handleDrop($event, 'main', index)"
                >
                  <template #prepend>
                    <v-icon :icon="item.icon" size="small" class="mr-2" />
                  </template>
                  <v-list-item-title>{{ t(item.title) }}</v-list-item-title>
                  <template #append>
                    <v-btn
                      icon="mdi-arrow-right"
                      variant="text"
                      size="x-small"
                      @click="moveToMore(index)"
                    />
                  </template>
                </v-list-item>
              </v-list>
            </v-col>

            <v-col cols="12" md="6">
              <div class="mb-2 font-weight-medium">
                {{ t("features.settings.sidebar.customize.moreItems") }}
              </div>
              <v-list
                density="compact"
                class="custom-list"
                @dragover.prevent
                @drop="handleDropToList($event, 'more')"
              >
                <v-list-item
                  v-for="(item, index) in moreItems"
                  :key="item.title"
                  class="mb-1 draggable-item"
                  draggable="true"
                  @dragstart="handleDragStart($event, 'more', index)"
                  @dragover.prevent
                  @drop.stop="handleDrop($event, 'more', index)"
                >
                  <template #prepend>
                    <v-icon :icon="item.icon" size="small" class="mr-2" />
                  </template>
                  <v-list-item-title>{{ t(item.title) }}</v-list-item-title>
                  <template #append>
                    <v-btn
                      icon="mdi-arrow-left"
                      variant="text"
                      size="x-small"
                      @click="moveToMain(index)"
                    />
                  </template>
                </v-list-item>
              </v-list>
            </v-col>
          </v-row>
        </v-card-text>

        <v-card-actions>
          <v-btn color="error" variant="text" @click="resetToDefault">
            {{ t("features.settings.sidebar.customize.reset") }}
          </v-btn>
          <v-spacer />
          <v-btn color="primary" @click="saveCustomization">
            {{ t("core.actions.save") }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useI18n } from "@/i18n/composables";
import sidebarItems, { type menu } from "@/layouts/full/vertical-sidebar/sidebarItem";
import {
  clearSidebarCustomization,
  getSidebarCustomization,
  resolveSidebarItems,
  setSidebarCustomization,
} from "@/utils/sidebarCustomization";

const { t } = useI18n();

const dialog = ref(false);
type SidebarItem = menu & { title: string };
type SidebarList = "main" | "more";
type DraggedItem = {
  type: SidebarList;
  index: number;
  item: SidebarItem;
};

const mainItems = ref<SidebarItem[]>([]);
const moreItems = ref<SidebarItem[]>([]);
const draggedItem = ref<DraggedItem | null>(null);

function initializeItems() {
  const customization = getSidebarCustomization();
  const { mainItems: resolvedMain, moreItems: resolvedMore } = resolveSidebarItems(sidebarItems, customization);
  const hasTitle = (item: menu): item is SidebarItem => typeof item.title === "string";
  mainItems.value = resolvedMain.filter(hasTitle);
  moreItems.value = resolvedMore.filter(hasTitle);
}

function openDialog() {
  initializeItems();
  dialog.value = true;
}

function getList(listType: SidebarList) {
  return listType === "main" ? mainItems.value : moreItems.value;
}

function handleDragStart(event: DragEvent, listType: SidebarList, index: number) {
  const item = getList(listType)[index];
  if (!item) return;
  draggedItem.value = { type: listType, index, item };
  if (event.dataTransfer) event.dataTransfer.effectAllowed = "move";
}

function handleDrop(event: DragEvent, targetListType: SidebarList, targetIndex?: number) {
  event.preventDefault();
  if (!draggedItem.value) return;

  const { type, index, item } = draggedItem.value;
  getList(type).splice(index, 1);
  const targetList = getList(targetListType);
  targetList.splice(targetIndex ?? targetList.length, 0, item);
  draggedItem.value = null;
}

function handleDropToList(event: DragEvent, targetListType: SidebarList) {
  handleDrop(event, targetListType);
}

function moveToMore(index: number) {
  const item = mainItems.value.splice(index, 1)[0];
  if (item) moreItems.value.push(item);
}

function moveToMain(index: number) {
  const item = moreItems.value.splice(index, 1)[0];
  if (item) mainItems.value.push(item);
}

function saveCustomization() {
  const config = {
    mainItems: mainItems.value.map((item) => item.title),
    moreItems: moreItems.value.map((item) => item.title),
  };

  setSidebarCustomization(config);

  // Notify the sidebar to reload
  window.dispatchEvent(new CustomEvent("sidebar-customization-changed"));

  dialog.value = false;
}

function resetToDefault() {
  clearSidebarCustomization();
  initializeItems();

  // Notify the sidebar to reload
  window.dispatchEvent(new CustomEvent("sidebar-customization-changed"));
}

onMounted(() => {
  initializeItems();
});
</script>

<style scoped>
.draggable-item {
  cursor: move;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 4px;
  background-color: rgba(var(--v-theme-surface));
  transition: all 0.2s;
}

.draggable-item:hover {
  background-color: rgba(var(--v-theme-primary), 0.1);
  border-color: rgba(var(--v-theme-primary), 0.3);
}

.custom-list {
  min-height: 200px;
  border: 1px dashed rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 4px;
  padding: 8px;
}
</style>
