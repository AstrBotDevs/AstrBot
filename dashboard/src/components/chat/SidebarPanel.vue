<template>
  <div
    class="sidebar-panel"
    :class="{ 'sidebar-collapsed': sidebarCollapsed }"
    :style="{ 'background-color': isDark ? (sidebarCollapsed ? '#1e1e1e' : '#2d2d2d') : (sidebarCollapsed ? '#ffffff' : '#f5f5f5') }"
    @mouseenter="handleSidebarMouseEnter"
    @mouseleave="handleSidebarMouseLeave"
  >
    <div style="display: flex; align-items: center; justify-content: center; padding: 16px; padding-bottom: 0px;" v-if="chatboxMode">
      <img width="50" src="@/assets/images/astrbot_logo_mini.webp" alt="AstrBot Logo" />
  <span v-if="!sidebarCollapsed" style="font-weight: 1000; font-size: 26px; margin-left: 8px;">AstrBot</span>
    </div>

    <div class="sidebar-collapse-btn-container">
      <v-btn icon class="sidebar-collapse-btn" @click="toggleSidebar" variant="text" color="deep-purple">
        <v-icon>{{ (sidebarCollapsed || (!sidebarCollapsed && sidebarHoverExpanded)) ? 'mdi-chevron-right' : 'mdi-chevron-left' }}</v-icon>
      </v-btn>
    </div>

    <div style="padding: 16px; padding-top: 8px;">
      <v-btn
        block
        variant="text"
        class="new-chat-btn"
        @click="$emit('new')"
        :disabled="!currCid"
        v-if="!sidebarCollapsed"
        prepend-icon="mdi-plus"
        style="background-color: transparent !important; border-radius: 4px;"
      >{{ tm('actions.newChat') }}</v-btn>
      <v-btn icon="mdi-plus" rounded="lg" @click="$emit('new')" :disabled="!currCid" v-if="sidebarCollapsed" elevation="0"></v-btn>
    </div>

    <div v-if="!sidebarCollapsed">
      <v-divider class="mx-4"></v-divider>
    </div>

    <div style="overflow-y: auto; flex-grow: 1;" :class="{ 'fade-in': sidebarHoverExpanded }" v-if="!sidebarCollapsed">
      <v-card v-if="conversations.length > 0" flat style="background-color: transparent;">
        <v-list density="compact" nav class="conversation-list" style="background-color: transparent;" v-model:selected="innerSelected" @update:selected="onSelected">
          <v-list-item v-for="(item, i) in conversations" :key="item.cid" :value="item.cid" rounded="lg" class="conversation-item" active-color="secondary">
            <v-list-item-title v-if="!sidebarCollapsed" class="conversation-title">{{ item.title || tm('conversation.newConversation') }}</v-list-item-title>
            <v-list-item-subtitle v-if="!sidebarCollapsed" class="timestamp">{{ formatDate(item.updated_at) }}</v-list-item-subtitle>

            <template v-if="!sidebarCollapsed" #append>
              <div class="conversation-actions">
                <v-btn icon="mdi-pencil" size="x-small" variant="text" class="edit-title-btn" @click.stop="$emit('edit-title', { cid: item.cid, title: item.title })" />
                <v-btn icon="mdi-delete" size="x-small" variant="text" class="delete-conversation-btn" color="error" @click.stop="$emit('delete', item.cid)" />
              </div>
            </template>
          </v-list-item>
        </v-list>
      </v-card>

      <v-fade-transition>
        <div class="no-conversations" v-if="conversations.length === 0">
          <v-icon icon="mdi-message-text-outline" size="large" color="grey-lighten-1"></v-icon>
          <div class="no-conversations-text" v-if="!sidebarCollapsed || sidebarHoverExpanded">{{ tm('conversation.noHistory') }}</div>
        </div>
      </v-fade-transition>
    </div>
  </div>
</template>

<script>
import { ref, watch, onUnmounted } from 'vue';
import { useCustomizerStore } from '@/stores/customizer';
import { useI18n, useModuleI18n } from '@/i18n/composables';
import { useSidebarState } from '@/composables/chat/useSidebarState';
import { formatTimestampSeconds } from '@/composables/chat/useDateFormat';

export default {
  name: 'SidebarPanel',
  props: {
    chatboxMode: { type: Boolean, default: false },
    conversations: { type: Array, required: true },
    selected: { type: Array, default: () => [] },
    currCid: { type: String, default: '' },
    isDark: { type: Boolean, default: null },
  },
  emits: ['update:selected', 'new', 'edit-title', 'delete'],
  setup(props, { emit }) {
    const { t } = useI18n();
    const { tm } = useModuleI18n('features/chat');
    const customizer = useCustomizerStore();
    const isDark = props.isDark ?? customizer.darkTheme;

    const {
      sidebarCollapsed,
      sidebarHovered,
      sidebarHoverExpanded,
      sidebarHoverTimer,
      sidebarHoverDelay,
      toggleSidebar,
      handleSidebarMouseEnter,
      handleSidebarMouseLeave,
      dispose,
    } = useSidebarState();

    const innerSelected = ref(props.selected);
    watch(() => props.selected, (val) => { innerSelected.value = val; });

    function onSelected(val) {
      emit('update:selected', val);
    }

    onUnmounted(() => dispose());

    function formatDate(ts) {
      // Sidebar 简化显示：当天仅显示时/分，否则显示月/日 时:分
      if (!ts) return '';
      const date = new Date(ts * 1000);
      const now = new Date();
      const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
      if (date.getTime() < todayStart) {
        return new Intl.DateTimeFormat(undefined, { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).format(date);
      }
      return new Intl.DateTimeFormat(undefined, { hour: '2-digit', minute: '2-digit' }).format(date);
    }

    return {
      t, tm, isDark,
      sidebarCollapsed,
      sidebarHovered,
      sidebarHoverExpanded,
      sidebarHoverTimer,
      sidebarHoverDelay,
      toggleSidebar,
      handleSidebarMouseEnter,
      handleSidebarMouseLeave,
      innerSelected, onSelected, formatDate
    };
  }
}
</script>
