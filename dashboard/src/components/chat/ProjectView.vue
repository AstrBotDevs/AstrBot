<template>
  <div class="project-sessions-container fade-in">
    <div class="project-header">
      <div class="project-header-info">
        <span class="project-header-emoji">{{ project?.emoji || "📁" }}</span>
        <h2 class="project-header-title">
          {{ project?.title }}
        </h2>
      </div>
      <p v-if="project?.description" class="project-header-description">
        {{ project.description }}
      </p>
      <div
        v-if="workspaceSummary"
        class="project-workspace-summary"
        :title="workspaceSummary"
      >
        <v-icon icon="mdi-folder-cog-outline" size="15" />
        <span>{{ workspaceSummary }}</span>
      </div>
    </div>

    <div class="project-input-slot">
      <slot />
    </div>

    <v-card flat class="project-sessions-list">
      <v-list v-if="sessions.length > 0">
        <v-list-item
          v-for="session in sessions"
          :key="session.session_id"
          class="project-session-item"
          rounded="lg"
          @click="$emit('selectSession', session.session_id)"
        >
          <v-list-item-title>
            {{ session.display_name || tm("conversation.newConversation") }}
          </v-list-item-title>
          <v-list-item-subtitle>
            {{ formatDate(session.updated_at) }}
          </v-list-item-subtitle>
          <template #append>
            <div class="session-actions">
              <v-btn
                icon="mdi-pencil"
                size="x-small"
                variant="text"
                class="edit-session-btn"
                :title="tm('conversation.editDisplayName')"
                @click.stop="
                  $emit(
                    'editSessionTitle',
                    session.session_id,
                    session.display_name ?? '',
                  )
                "
              />
              <v-btn
                icon="mdi-delete"
                size="x-small"
                variant="text"
                class="delete-session-btn"
                color="error"
                :title="tm('actions.deleteChat')"
                @click.stop="handleDeleteSession(session)"
              />
            </div>
          </template>
        </v-list-item>
      </v-list>
      <div v-else class="no-sessions-in-project">
        <v-icon
          icon="mdi-message-off-outline"
          size="large"
          color="grey-lighten-1"
        />
        <p>{{ tm("project.noSessions") }}</p>
      </div>
    </v-card>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import type { Project } from "@/components/chat/ProjectList.vue";
import { useModuleI18n } from "@/i18n/composables";
import { askForConfirmation, useConfirmDialog } from "@/utils/confirmDialog";

interface Session {
  session_id: string;
  display_name?: string | null;
  updated_at: string;
}

interface Props {
  project?: Project | null;
  sessions: Session[];
}

const props = defineProps<Props>();

const emit = defineEmits<{
  selectSession: [sessionId: string];
  editSessionTitle: [sessionId: string, title: string];
  deleteSession: [sessionId: string];
}>();

const { tm } = useModuleI18n("features/chat");
const confirmDialog = useConfirmDialog();

const workspaceSummary = computed(() => {
  const project = props.project;
  if (!project) return "";

  const workspaceType = project.workspace_type || "session";
  if (workspaceType === "session") {
    return tm("project.workspace.session");
  }

  const path = project.resolved_workspace_path || project.workspace_path || "";
  const label = tm(`project.workspace.${workspaceType}`);
  return path ? `${label} · ${path}` : label;
});

function formatDate(dateString: string): string {
  return new Date(dateString).toLocaleString();
}

async function handleDeleteSession(session: Session) {
  const sessionTitle =
    session.display_name || tm("conversation.newConversation");
  const message = tm("conversation.confirmDelete", { name: sessionTitle });
  if (await askForConfirmation(message, confirmDialog)) {
    emit("deleteSession", session.session_id);
  }
}
</script>

<style scoped>
.project-sessions-container {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 32px;
  overflow-y: auto;
}

.project-header {
  text-align: center;
  margin-bottom: 32px;
  max-width: 600px;
}

.project-header-info {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  margin-bottom: 12px;
}

.project-header-emoji {
  font-size: 48px;
}

.project-header-title {
  font-size: 32px;
  font-weight: 600;
}

.project-header-description {
  font-size: 14px;
  color: var(--v-theme-secondaryText);
  margin: 0;
}

.project-workspace-summary {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  max-width: 100%;
  margin-top: 12px;
  color: rgba(var(--v-theme-on-surface), 0.52);
  font-size: 12px;
}

.project-workspace-summary span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.project-input-slot {
  width: 100%;
  max-width: 800px;
  margin-bottom: 24px;
}

.project-sessions-list {
  width: 100%;
  max-width: 680px;
  background-color: transparent !important;
}

.project-session-item {
  margin-bottom: 8px;
  border-radius: 12px !important;
  cursor: pointer;
}

.project-session-item:hover {
  background-color: rgba(103, 58, 183, 0.05);
}

.project-session-item:hover .session-actions {
  opacity: 1;
  visibility: visible;
}

.session-actions {
  display: flex;
  gap: 2px;
  opacity: 1;
}

.no-sessions-in-project {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 48px;
  opacity: 0.6;
}

.no-sessions-in-project p {
  margin-top: 12px;
  font-size: 14px;
}

.fade-in {
  animation: fadeIn 0.3s ease-in-out;
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(10px);
  }

  to {
    opacity: 1;
    transform: translateY(0);
  }
}
</style>
