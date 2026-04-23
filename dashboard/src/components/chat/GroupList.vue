<template>
  <div class="group-list-shell">
    <div class="group-button-wrap">
      <v-btn block variant="text" class="group-btn" @click="toggleExpanded">
        <v-icon size="20" class="group-action-icon mr-2">
          mdi-forum
        </v-icon>
        <span class="group-btn-title">{{ tm("group.title") }}</span>
        <v-spacer />
        <v-icon size="18" class="group-toggle-icon">
          {{ expanded ? "mdi-chevron-up" : "mdi-chevron-down" }}
        </v-icon>
      </v-btn>
    </div>

    <v-expand-transition>
      <div v-show="expanded" class="group-list-wrap">
        <button
          class="group-row create-group-item"
          type="button"
          @click="$emit('createGroup')"
        >
          <span class="group-icon">
            <v-icon size="18">mdi-plus</v-icon>
          </span>
          <span class="group-title">{{ tm("group.create") }}</span>
        </button>

        <button
          v-for="session in sessions"
          :key="session.session_id"
          class="group-row group-item"
          :class="{ active: selectedSessionId === session.session_id }"
          type="button"
          @click="$emit('selectSession', session.session_id)"
        >
          <span class="group-icon">
            <img :src="defaultGroupAvatar" alt="" />
          </span>
          <span class="group-title">{{ sessionTitle(session) }}</span>
          <span class="group-actions">
            <v-btn
              icon="mdi-pencil"
              size="x-small"
              variant="text"
              class="edit-group-btn"
              @click.stop="$emit('editSessionTitle', session)"
            />
            <v-btn
              icon="mdi-delete"
              size="x-small"
              variant="text"
              class="delete-group-btn"
              color="error"
              @click.stop="handleDeleteSession(session)"
            />
          </span>
        </button>
      </div>
    </v-expand-transition>
  </div>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { useModuleI18n } from "@/i18n/composables";
import { askForConfirmation, useConfirmDialog } from "@/utils/confirmDialog";
import type { Session } from "@/composables/useSessions";
import defaultGroupAvatar from "@/assets/images/chatui-group-default-avatar.png";

const props = withDefaults(
  defineProps<{
    sessions: Session[];
    selectedSessionId?: string | null;
    initialExpanded?: boolean;
  }>(),
  {
    selectedSessionId: null,
    initialExpanded: false,
  },
);

const emit = defineEmits<{
  createGroup: [];
  selectSession: [sessionId: string];
  editSessionTitle: [session: Session];
  deleteSession: [session: Session];
}>();

const { tm } = useModuleI18n("features/chat");
const confirmDialog = useConfirmDialog();
const expanded = ref(props.initialExpanded);

const savedGroupsExpandedState = localStorage.getItem("groupsExpanded");
if (savedGroupsExpandedState !== null) {
  expanded.value = JSON.parse(savedGroupsExpandedState);
}

function toggleExpanded() {
  expanded.value = !expanded.value;
  localStorage.setItem("groupsExpanded", JSON.stringify(expanded.value));
}

function sessionTitle(session: Session) {
  return session.display_name?.trim() || tm("group.defaultName");
}

async function handleDeleteSession(session: Session) {
  const message = tm("conversation.confirmDelete", {
    name: sessionTitle(session),
  });
  if (await askForConfirmation(message, confirmDialog)) {
    emit("deleteSession", session);
  }
}
</script>

<style scoped>
.group-list-shell {
  margin-top: 6px;
}

.group-button-wrap {
  opacity: 0.6;
}

.group-btn {
  justify-content: flex-start;
  background-color: transparent !important;
  border-radius: 8px;
  padding: 8px 12px !important;
  text-transform: none;
  font-weight: 500;
}

.group-action-icon {
  color: currentcolor;
}

.group-btn-title {
  min-width: 0;
}

.group-toggle-icon {
  margin-left: 10px;
}

.group-list-wrap {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-top: 8px;
}

.group-row {
  width: 100%;
  min-height: 38px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: inherit;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  cursor: pointer;
  text-align: left;
}

.group-row:hover,
.group-row.active {
  background: var(--chat-session-active-bg);
}

.group-item:hover .group-actions {
  opacity: 1;
  visibility: visible;
}

.group-icon {
  width: 20px;
  flex: 0 0 20px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.group-icon img {
  width: 20px;
  height: 20px;
  border-radius: 6px;
  object-fit: cover;
}

.group-title {
  min-width: 0;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 14px;
  font-weight: 500;
}

.group-actions {
  display: flex;
  gap: 2px;
  opacity: 0;
  visibility: hidden;
  transition: all 0.2s ease;
}

.edit-group-btn,
.delete-group-btn {
  opacity: 0.7;
  transition: opacity 0.2s ease;
}

.edit-group-btn:hover,
.delete-group-btn:hover {
  opacity: 1;
}

.create-group-item {
  opacity: 0.7;
}

.create-group-item:hover {
  opacity: 1;
}
</style>
