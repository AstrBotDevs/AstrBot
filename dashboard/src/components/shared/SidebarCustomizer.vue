<template>
  <div style="margin-top: 16px;">
    <v-btn 
      color="primary" 
      variant="outlined"
      size="small"
      @click="openDialog"
      style="margin-bottom: 8px;"
    >
      {{ t('features.settings.sidebar.customize.title') }}
    </v-btn>

    <v-dialog v-model="dialog" max-width="700px">
      <v-card>
        <v-card-title class="d-flex justify-space-between align-center">
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
                <v-list-item
                  v-for="(item, index) in mainItems"
                  :key="item.title"
                  class="mb-1 draggable-item"
                  draggable="true"
                  @dragstart="handleDragStart($event, 'main', index)"
                  @dragover.prevent
                  @drop.stop="handleDrop($event, 'main', index)"
                >
                  <template v-slot:prepend>
                    <v-icon :icon="item.icon" size="small" class="mr-2"></v-icon>
                  </template>
                  <v-list-item-title>{{ t(item.title) }}</v-list-item-title>
                  <template v-slot:append>
                    <v-btn
                      icon="mdi-arrow-right"
                      variant="text"
                      size="x-small"
                      @click="moveToMore(index)"
                    ></v-btn>
                  </template>
                </v-list-item>
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
                <v-list-item
                  v-for="(item, index) in moreItems"
                  :key="item.title"
                  class="mb-1 draggable-item"
                  draggable="true"
                  @dragstart="handleDragStart($event, 'more', index)"
                  @dragover.prevent
                  @drop.stop="handleDrop($event, 'more', index)"
                >
                  <template v-slot:prepend>
                    <v-icon :icon="item.icon" size="small" class="mr-2"></v-icon>
                  </template>
                  <v-list-item-title>{{ t(item.title) }}</v-list-item-title>
                  <template v-slot:append>
                    <v-btn
                      icon="mdi-arrow-left"
                      variant="text"
                      size="x-small"
                      @click="moveToMain(index)"
                    ></v-btn>
                  </template>
                </v-list-item>
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
import { ref, onMounted } from 'vue';
import { useI18n } from '@/i18n/composables';
import sidebarItems from '@/layouts/full/vertical-sidebar/sidebarItem';
import { 
  getSidebarCustomization, 
  setSidebarCustomization, 
  clearSidebarCustomization,
  resolveSidebarItems
} from '@/utils/sidebarCustomization';

const { t } = useI18n();

const dialog = ref(false);
const mainItems = ref([]);
const moreItems = ref([]);
const draggedItem = ref(null);

function initializeItems() {
  const customization = getSidebarCustomization();
  const { mainItems: resolvedMain, moreItems: resolvedMore } = resolveSidebarItems(
    sidebarItems,
    customization
  );
  mainItems.value = resolvedMain;
  moreItems.value = resolvedMore;
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
  
  // Add to target
  if (targetListType === 'main') {
    mainItems.value.splice(targetIndex, 0, item);
  } else {
    moreItems.value.splice(targetIndex, 0, item);
  }
  
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

function moveToMore(index) {
  const item = mainItems.value.splice(index, 1)[0];
  moreItems.value.push(item);
}

function moveToMain(index) {
  const item = moreItems.value.splice(index, 1)[0];
  mainItems.value.push(item);
}

function saveCustomization() {
  const config = {
    mainItems: mainItems.value.map(item => item.title),
    moreItems: moreItems.value.map(item => item.title)
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
</style>
