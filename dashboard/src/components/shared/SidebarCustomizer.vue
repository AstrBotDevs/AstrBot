<template>
  <div style="margin-top: 16px;">
    <v-btn 
      color="primary" 
      variant="tonal"
      size="small"
      @click="openDialog"
      style="margin-bottom: 8px;"
    >
      {{ t('features.settings.sidebar.customize.title') }}
    </v-btn>

    <v-dialog v-model="dialog" max-width="700px">
      <v-card>
        <v-card-title class="text-h3 pa-4 pb-0 pl-6 d-flex justify-space-between align-center">
          <span>{{ t('features.settings.sidebar.customize.title') }}</span>
          <v-btn
            icon="mdi-close"
            variant="text"
            @click="dialog = false"
          ></v-btn>
        </v-card-title>
        
        <v-card-text>
          <p class="text-body-2 mb-4">{{ t('features.settings.sidebar.customize.subtitle') }}</p>
          
          <v-row>
            <v-col cols="12" md="6">
              <div class="mb-2 font-weight-medium">{{ t('features.settings.sidebar.customize.mainItems') }}</div>
              <v-list 
                density="compact"
                class="custom-list"
                @dragover.prevent
                @drop="handleDropToList($event, 'main')"
              >
                <template v-for="group in customizerGroups" :key="group.key">
                  <div class="customizer-group-header">
                    <span>{{ t(group.labelKey) }}</span>
                  </div>
                  <template v-for="item in itemsByGroup(mainItems, group.key)" :key="item.title">
                    <v-list-item
                      class="mb-1 draggable-item"
                      draggable="true"
                      @dragstart="handleDragStart($event, 'main', indexOfItem(mainItems, item))"
                      @dragover.prevent
                      @drop.stop="handleDrop($event, 'main', indexOfItem(mainItems, item))"
                    >
                      <template v-slot:prepend>
                        <v-icon v-if="typeof item.icon === 'string'" :icon="item.icon" size="small" class="mr-2" />
                        <component :is="item.icon" v-else-if="item.icon" :size="18" class="mr-2" />
                      </template>
                      <v-list-item-title>{{ t(item.title) }}</v-list-item-title>
                      <template v-slot:append>
                        <v-btn
                          v-if="subDefByLabelKey.has(item.title)"
                          icon="mdi-arrow-down"
                          variant="text"
                          size="x-small"
                          @click="demoteSubItem(item.title)"
                        ></v-btn>
                        <v-btn
                          v-if="getSubItems(item.title)"
                          :icon="expandedParents[item.title] ? 'mdi-chevron-down' : 'mdi-chevron-right'"
                          variant="text"
                          size="x-small"
                          @click="toggleParentExpanded(item.title)"
                        ></v-btn>
                        <v-btn
                          icon="mdi-arrow-right"
                          variant="text"
                          size="x-small"
                          @click="moveToMore(indexOfItem(mainItems, item))"
                        ></v-btn>
                      </template>
                    </v-list-item>
                    <v-list
                      v-if="expandedParents[item.title] && getSubItems(item.title)"
                      density="compact"
                      class="custom-sub-list"
                      @dragover.prevent
                      @drop="handleSubDrop($event, getSubItems(item.title).length - 1)"
                    >
                      <v-list-item
                        v-for="(sub, subIndex) in getSubItems(item.title)"
                        :key="sub.value"
                        class="mb-1 draggable-item sub-item"
                        draggable="true"
                        @dragstart="handleSubDragStart($event, item.title, subIndex)"
                        @dragover.prevent
                        @drop.stop="handleSubDrop($event, subIndex)"
                      >
                        <template v-slot:prepend>
                          <v-icon v-if="typeof sub.icon === 'string'" :icon="sub.icon" size="small" class="mr-2" />
                          <component :is="sub.icon" v-else-if="sub.icon" :size="16" class="mr-2" />
                        </template>
                        <v-list-item-title class="sub-item-title">{{ t(sub.labelKey) }}</v-list-item-title>
                        <template v-slot:append>
                          <v-btn
                            v-if="canPromoteSub(sub.value)"
                            icon="mdi-arrow-up"
                            variant="text"
                            size="x-small"
                            @click="promoteSubItem(item.title, sub.value)"
                          ></v-btn>
                        </template>
                      </v-list-item>
                    </v-list>
                  </template>
                  <template v-if="group.key === EXTENSION_GROUP_KEY">
                    <template v-for="entry in extensionPluginEntries" :key="entry.key">
                      <v-list-item class="mb-1 static-item">
                        <template v-slot:prepend>
                          <v-icon v-if="typeof entry.icon === 'string'" :icon="entry.icon" size="small" class="mr-2" />
                          <component :is="entry.icon" v-else-if="entry.icon" :size="18" class="mr-2" />
                        </template>
                        <v-list-item-title>{{ entryTitle(entry) }}</v-list-item-title>
                        <template v-slot:append>
                          <v-tooltip :text="t('features.settings.sidebar.customize.pluginHint')" location="left">
                            <template v-slot:activator="{ props: tooltipProps }">
                              <v-icon v-bind="tooltipProps" icon="mdi-information-outline" size="small" />
                            </template>
                          </v-tooltip>
                        </template>
                      </v-list-item>
                    </template>
                  </template>
                </template>
              </v-list>
            </v-col>
            
            <v-col cols="12" md="6">
              <div class="mb-2 font-weight-medium">{{ t('features.settings.sidebar.customize.moreItems') }}</div>
              <v-list 
                density="compact"
                class="custom-list"
                @dragover.prevent
                @drop="handleDropToList($event, 'more')"
              >
                <template v-for="group in customizerGroups" :key="group.key">
                  <div class="customizer-group-header">
                    <span>{{ t(group.labelKey) }}</span>
                  </div>
                  <template v-for="item in itemsByGroup(moreItems, group.key)" :key="item.title">
                    <v-list-item
                      class="mb-1 draggable-item"
                      draggable="true"
                      @dragstart="handleDragStart($event, 'more', indexOfItem(moreItems, item))"
                      @dragover.prevent
                      @drop.stop="handleDrop($event, 'more', indexOfItem(moreItems, item))"
                    >
                      <template v-slot:prepend>
                        <v-icon v-if="typeof item.icon === 'string'" :icon="item.icon" size="small" class="mr-2" />
                        <component :is="item.icon" v-else-if="item.icon" :size="18" class="mr-2" />
                      </template>
                      <v-list-item-title>{{ t(item.title) }}</v-list-item-title>
                      <template v-slot:append>
                        <v-btn
                          v-if="subDefByLabelKey.has(item.title)"
                          icon="mdi-arrow-down"
                          variant="text"
                          size="x-small"
                          @click="demoteSubItem(item.title)"
                        ></v-btn>
                        <v-btn
                          v-if="getSubItems(item.title)"
                          :icon="expandedParents[item.title] ? 'mdi-chevron-down' : 'mdi-chevron-right'"
                          variant="text"
                          size="x-small"
                          @click="toggleParentExpanded(item.title)"
                        ></v-btn>
                        <v-btn
                          icon="mdi-arrow-left"
                          variant="text"
                          size="x-small"
                          @click="moveToMain(indexOfItem(moreItems, item))"
                        ></v-btn>
                      </template>
                    </v-list-item>
                    <v-list
                      v-if="expandedParents[item.title] && getSubItems(item.title)"
                      density="compact"
                      class="custom-sub-list"
                      @dragover.prevent
                      @drop="handleSubDrop($event, getSubItems(item.title).length - 1)"
                    >
                      <v-list-item
                        v-for="(sub, subIndex) in getSubItems(item.title)"
                        :key="sub.value"
                        class="mb-1 draggable-item sub-item"
                        draggable="true"
                        @dragstart="handleSubDragStart($event, item.title, subIndex)"
                        @dragover.prevent
                        @drop.stop="handleSubDrop($event, subIndex)"
                      >
                        <template v-slot:prepend>
                          <v-icon v-if="typeof sub.icon === 'string'" :icon="sub.icon" size="small" class="mr-2" />
                          <component :is="sub.icon" v-else-if="sub.icon" :size="16" class="mr-2" />
                        </template>
                        <v-list-item-title class="sub-item-title">{{ t(sub.labelKey) }}</v-list-item-title>
                        <template v-slot:append>
                          <v-btn
                            v-if="canPromoteSub(sub.value)"
                            icon="mdi-arrow-up"
                            variant="text"
                            size="x-small"
                            @click="promoteSubItem(item.title, sub.value)"
                          ></v-btn>
                        </template>
                      </v-list-item>
                    </v-list>
                  </template>
                </template>
              </v-list>
            </v-col>
          </v-row>
        </v-card-text>
        
        <v-card-actions>
          <v-btn
            color="error"
            variant="text"
            @click="resetToDefault"
          >
            {{ t('features.settings.sidebar.customize.reset') }}
          </v-btn>
          <v-spacer></v-spacer>
          <v-btn
            color="primary"
            variant="tonal"
            @click="saveCustomization"
          >
            {{ t('core.actions.save') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue';
import { useI18n } from '@/i18n/composables';
import sidebarItems, {
  SYSTEM_GROUP_KEY,
  EXTENSION_GROUP_KEY
} from '@/layouts/full/vertical-sidebar/sidebarItem';
import { usePluginSidebarItems } from '@/composables/usePluginSidebarItems';
import { 
  getSidebarCustomization, 
  setSidebarCustomization, 
  clearSidebarCustomization,
  resolveSidebarItems
} from '@/utils/sidebarCustomization';
import { SIDEBAR_SUB_ITEMS, findSubRouteDef, getSubRoutePath } from '@/utils/sidebarSubItems';

const { t } = useI18n();

// Sub-route definition lookup by labelKey, for promoted (first-level) items.
const subDefByLabelKey = new Map();
Object.entries(SIDEBAR_SUB_ITEMS).forEach(([parentTitle, subs]) => {
  subs.forEach((sub) => subDefByLabelKey.set(sub.labelKey, { ...sub, parentTitle }));
});

const dialog = ref(false);
const mainItems = ref([]);
const moreItems = ref([]);
const draggedItem = ref(null);
// Ordered sub-route values per parent title (only for parents in SIDEBAR_SUB_ITEMS).
const subItemOrder = ref({});
// Expanded/collapsed state per parent title; sub-route lists are collapsed by default.
const expandedParents = ref({});
const draggedSubItem = ref(null);

// The customizer renders both lists grouped under the same headers as the
// real sidebar, so extension entries stay visibly separated from system ones.
const customizerGroups = [
  { key: SYSTEM_GROUP_KEY, labelKey: 'core.navigation.groups.system' },
  { key: EXTENSION_GROUP_KEY, labelKey: 'core.navigation.groups.extension' }
];

// Map every first-level item title to the group header it sits under in the
// default sidebar, so the customizer can render items under their group.
const itemGroupByTitle = new Map();
{
  let currentGroup = SYSTEM_GROUP_KEY;
  sidebarItems.forEach((item) => {
    if (item.header) {
      currentGroup = item.header;
      return;
    }
    itemGroupByTitle.set(item.title, currentGroup);
  });
}

function itemsByGroup(list, groupKey) {
  return list.filter((item) => {
    let group = itemGroupByTitle.get(item.title);
    // Promoted sub-routes are not part of the default item map; they render
    // in the same group as their parent item.
    if (group === undefined) {
      const def = subDefByLabelKey.get(item.title);
      if (def) group = itemGroupByTitle.get(def.parentTitle);
    }
    return group === groupKey;
  });
}

function indexOfItem(list, item) {
  return list.findIndex((it) => it.title === item.title);
}

// Dynamic plugin entries appended to the extension group. They are read-only
// in the customizer because they are generated from the extension pages.
const { pluginItems, pluginGroups } = usePluginSidebarItems();
const extensionPluginEntries = computed(() => {
  if (localStorage.getItem('sidebar_group_by_plugin') === '1') {
    return (pluginGroups.value ?? []).map((group) => ({
      key: `group-${group.title}`,
      title: group.title,
      icon: group.icon,
      isRawTitle: true
    }));
  }
  return (pluginItems.value?.children ?? []).map((child) => ({
    key: `page-${child.to ?? child.title}`,
    title: child.title,
    icon: child.icon,
    isRawTitle: true
  }));
});

// Raw plugin titles are display names, not i18n keys.
function entryTitle(entry) {
  return entry.isRawTitle ? entry.title : t(entry.title);
}

function toggleParentExpanded(parentTitle) {
  expandedParents.value[parentTitle] = !expandedParents.value[parentTitle];
}

function getSubItems(parentTitle) {
  const defaults = SIDEBAR_SUB_ITEMS[parentTitle];
  if (!defaults) return null;
  const order = subItemOrder.value[parentTitle] || defaults.map((item) => item.value);
  if (order.length === 0) return null;
  const byValue = new Map(defaults.map((item) => [item.value, item]));
  return order.map((value) => byValue.get(value)).filter(Boolean);
}

// A sub-route can be lifted to a first-level item only when its parent hosts
// real routes (data/extension); providers tabs have no route to point at.
function canPromoteSub(value) {
  const def = findSubRouteDef(value);
  return def ? Boolean(getSubRoutePath(def.parentTitle, def.value)) : false;
}

// Lift a sub-route out of its parent's list into the first-level list that
// hosts the parent, right after it. The item can then be dragged anywhere.
function promoteSubItem(parentTitle, value) {
  const order = subItemOrder.value[parentTitle];
  if (order) {
    const idx = order.indexOf(value);
    if (idx >= 0) order.splice(idx, 1);
  }
  const def = SIDEBAR_SUB_ITEMS[parentTitle].find((s) => s.value === value);
  if (!def) return;
  const promotedItem = { title: def.labelKey, icon: def.icon };
  const target = mainItems.value.some((it) => it.title === parentTitle)
    ? mainItems.value
    : moreItems.value;
  const parentIdx = target.findIndex((it) => it.title === parentTitle);
  if (parentIdx >= 0) target.splice(parentIdx + 1, 0, promotedItem);
  else target.push(promotedItem);
}

// Move a promoted sub-route back under its parent's list (appended last).
function demoteSubItem(labelKey) {
  const info = subDefByLabelKey.get(labelKey);
  if (!info) return;
  const idxMain = mainItems.value.findIndex((it) => it.title === labelKey);
  if (idxMain >= 0) mainItems.value.splice(idxMain, 1);
  const idxMore = moreItems.value.findIndex((it) => it.title === labelKey);
  if (idxMore >= 0) moreItems.value.splice(idxMore, 1);
  const order = subItemOrder.value[info.parentTitle];
  if (order && !order.includes(info.value)) order.push(info.value);
}

function initializeItems() {
  const customization = getSidebarCustomization();
  const { mainItems: resolvedMain, moreItems: resolvedMore } = resolveSidebarItems(
    sidebarItems,
    customization
  );
  mainItems.value = resolvedMain;
  moreItems.value = resolvedMore;

  const promoted = new Set(customization?.promotedSubRoutes ?? []);
  const nextOrder = {};
  Object.keys(SIDEBAR_SUB_ITEMS).forEach((parentTitle) => {
    const custom = customization?.subItems?.[parentTitle];
    const order =
      Array.isArray(custom) && custom.length > 0
        ? [...custom]
        : SIDEBAR_SUB_ITEMS[parentTitle].map((item) => item.value);
    nextOrder[parentTitle] = order.filter((value) => !promoted.has(value));
  });
  subItemOrder.value = nextOrder;
  // Start collapsed whenever the dialog opens.
  expandedParents.value = {};

  // Resolved lists already carry promoted sub-routes at their stored position
  // (resolveSidebarItems keeps labelKey titles). For storage written before
  // that change, fall back to placing them right after their parent.
  (customization?.promotedSubRoutes ?? []).forEach((value) => {
    const def = findSubRouteDef(value);
    if (!def) return;
    const labelKey = def.labelKey;
    const inLists =
      mainItems.value.some((it) => it.title === labelKey) ||
      moreItems.value.some((it) => it.title === labelKey);
    if (inLists) return;
    const item = { title: def.labelKey, icon: def.icon };
    const target = mainItems.value.some((it) => it.title === def.parentTitle)
      ? mainItems.value
      : moreItems.value;
    const parentIdx = target.findIndex((it) => it.title === def.parentTitle);
    if (parentIdx >= 0) target.splice(parentIdx + 1, 0, item);
    else target.push(item);
  });
}

function openDialog() {
  initializeItems();
  dialog.value = true;
}

function handleDragStart(event, listType, index) {
  draggedItem.value = {
    type: listType,
    index: index,
    item: listType === 'main' ? mainItems.value[index] : moreItems.value[index]
  };
  event.dataTransfer.effectAllowed = 'move';
}

function handleDrop(event, targetListType, targetIndex) {
  event.preventDefault();
  
  if (!draggedItem.value) return;
  
  const sourceListType = draggedItem.value.type;
  const sourceIndex = draggedItem.value.index;
  const item = draggedItem.value.item;
  
  // Remove from source
  if (sourceListType === 'main') {
    mainItems.value.splice(sourceIndex, 1);
  } else {
    moreItems.value.splice(sourceIndex, 1);
  }

  // Insert at the drop position. targetIndex was resolved before the source
  // removal, so when dragging within the same list the removal shifts it
  // down by one.
  const target = targetListType === 'main' ? mainItems.value : moreItems.value;
  let insertAt = targetIndex;
  if (sourceListType === targetListType && sourceIndex < insertAt) insertAt -= 1;
  insertAt = Math.max(0, Math.min(insertAt, target.length));
  target.splice(insertAt, 0, item);
  
  draggedItem.value = null;
}

function handleDropToList(event, targetListType) {
  event.preventDefault();
  
  if (!draggedItem.value) return;
  
  const sourceListType = draggedItem.value.type;
  const sourceIndex = draggedItem.value.index;
  const item = draggedItem.value.item;
  
  // Remove from source
  if (sourceListType === 'main') {
    mainItems.value.splice(sourceIndex, 1);
  } else {
    moreItems.value.splice(sourceIndex, 1);
  }
  
  // Add to target list at the end
  if (targetListType === 'main') {
    mainItems.value.push(item);
  } else {
    moreItems.value.push(item);
  }
  
  draggedItem.value = null;
}

function handleSubDragStart(event, parentTitle, index) {
  draggedSubItem.value = { parentTitle, index };
  event.dataTransfer.effectAllowed = 'move';
}

function handleSubDrop(event, targetIndex) {
  event.preventDefault();

  if (!draggedSubItem.value) return;

  const { parentTitle, index: fromIndex } = draggedSubItem.value;
  const order = subItemOrder.value[parentTitle];
  if (!order || fromIndex === targetIndex) {
    draggedSubItem.value = null;
    return;
  }

  const [moved] = order.splice(fromIndex, 1);
  order.splice(targetIndex, 0, moved);
  draggedSubItem.value = null;
}

function moveToMore(index) {
  const item = mainItems.value.splice(index, 1)[0];
  moreItems.value.push(item);
}

function moveToMain(index) {
  const item = moreItems.value.splice(index, 1)[0];
  mainItems.value.push(item);
}

function saveCustomization() {
  // Promoted sub-routes stay in the lists at their dragged position; the
  // separate promotedSubRoutes array is just an ordered marker for them.
  const mainTitles = [];
  const moreTitles = [];
  const promotedSubRoutes = [];
  [mainItems.value, moreItems.value].forEach((list, listIndex) => {
    list.forEach((item) => {
      const info = subDefByLabelKey.get(item.title);
      if (info) promotedSubRoutes.push(info.value);
      if (listIndex === 0) mainTitles.push(item.title);
      else moreTitles.push(item.title);
    });
  });
  const promotedSet = new Set(promotedSubRoutes);
  const subItems = {};
  Object.keys(subItemOrder.value).forEach((parentTitle) => {
    subItems[parentTitle] = subItemOrder.value[parentTitle].filter(
      (value) => !promotedSet.has(value)
    );
  });

  const config = {
    mainItems: mainTitles,
    moreItems: moreTitles,
    subItems,
    promotedSubRoutes
  };

  setSidebarCustomization(config);

  // Notify the sidebar to reload
  window.dispatchEvent(new CustomEvent('sidebar-customization-changed'));

  dialog.value = false;
}

function resetToDefault() {
  clearSidebarCustomization();
  initializeItems();
  
  // Notify the sidebar to reload
  window.dispatchEvent(new CustomEvent('sidebar-customization-changed'));
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

/* Group headers mirror the sidebar section headers (e.g. 系统 / 扩展功能). */
.customizer-group-header {
  display: flex;
  align-items: center;
  padding: 6px 4px 4px;
  margin-top: 4px;
  font-size: 0.8125rem;
  font-weight: 500;
  color: rgba(var(--v-theme-on-surface), 0.6);
  letter-spacing: 0.02em;
}

/* Dynamic plugin entries are not customizable, show them as read-only. */
.static-item {
  opacity: 0.85;
  background: rgba(var(--v-theme-on-surface), 0.03);
  cursor: default;
}

/* Nested sub-route lists (e.g. the four /data tabs) sit indented under their
   parent item and stay inside the parent's column. */
.custom-sub-list {
  min-height: 0;
  margin-bottom: 6px;
  padding: 0 0 2px 22px;
  border: 0;
  border-left: 2px dashed rgba(var(--v-border-color), var(--v-border-opacity));
}

.sub-item {
  background: rgba(var(--v-theme-on-surface), 0.035);
}

.sub-item:hover {
  background: rgba(var(--v-theme-primary), 0.08);
}

.sub-item-title {
  font-size: 0.8125rem;
}
</style>
