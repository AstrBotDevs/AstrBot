<template>
  <div class="project-sessions-container fade-in">
    <section class="project-header">
      <div class="project-title-row">
        <span class="project-header-emoji" aria-hidden="true">
          {{ project?.emoji || "📁" }}
        </span>
        <div class="project-title-copy">
          <h2 class="project-header-title">{{ project?.title }}</h2>
          <p class="project-header-description" v-if="project?.description">
            {{ project.description }}
          </p>
        </div>
      </div>
      <div
        v-if="workspaceSummary"
        class="project-workspace-summary"
        :title="workspaceSummary"
      >
        <FolderCog :size="15" />
        <span>{{ workspaceSummary }}</span>
      </div>
    </section>

    <div class="project-input-slot">
      <slot></slot>
    </div>

    <section class="project-sessions-list">
      <div v-if="sessions.length > 0" class="project-session-list">
        <button
          v-for="session in sessions"
          :key="session.session_id"
          type="button"
          @click="$emit('selectSession', session.session_id)"
          class="project-session-item"
        >
          <span class="project-session-copy">
            <span class="project-session-title">
              {{ session.display_name || tm("conversation.newConversation") }}
            </span>
            <span class="project-session-time">
              {{ formatDate(session.updated_at) }}
            </span>
          </span>
          <span class="session-actions">
            <button
              type="button"
              class="project-session-action"
              :title="tm('conversation.editDisplayName')"
              @click.stop="
                $emit(
                  'editSessionTitle',
                  session.session_id,
                  session.display_name ?? '',
                )
              "
            >
              <Pencil :size="17" />
            </button>
            <button
              type="button"
              class="project-session-action delete-session-btn"
              :title="tm('actions.deleteChat')"
              @click.stop="handleDeleteSession(session)"
            >
              <Trash2 :size="17" />
            </button>
          </span>
        </button>
      </div>
      <div v-else class="no-sessions-in-project">
        <MessageSquare :size="22" />
        <p>{{ tm("project.noSessions") }}</p>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { FolderCog, MessageSquare, Pencil, Trash2 } from "@lucide/vue";
import { useModuleI18n } from "@/i18n/composables";
import type { Project } from "@/components/chat/ProjectList.vue";
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
  if (workspaceType === "project") {
    return path
      ? `${tm("project.workspace.project")} · ${path}`
      : tm("project.workspace.project");
  }
  return path
    ? `${tm("project.workspace.custom")} · ${path}`
    : tm("project.workspace.custom");
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
  padding: clamp(44px, 8vh, 88px) 32px 48px;
  overflow-y: auto;
}

.project-header {
  width: var(--chat-content-width, 76%);
  max-width: var(--chat-content-max-width, 760px);
  margin: 0 auto 18px;
}

.project-title-row {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.project-header-emoji {
  flex: 0 0 auto;
  font-size: 28px;
  line-height: 1;
}

.project-title-copy {
  min-width: 0;
}

.project-header-title {
  margin: 0;
  overflow: hidden;
  color: rgb(var(--v-theme-on-surface));
  font-size: 28px;
  font-weight: 750;
  line-height: 1.12;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.project-header-description {
  margin: 5px 0 0;
  color: rgba(var(--v-theme-on-surface), 0.56);
  font-size: 14px;
  line-height: 1.45;
}

.project-workspace-summary {
  display: flex;
  align-items: center;
  gap: 8px;
  max-width: 100%;
  margin-top: 12px;
  color: rgba(var(--v-theme-on-surface), 0.52);
  font-size: 12px;
  line-height: 18px;
}

.project-workspace-summary svg {
  flex: 0 0 auto;
  stroke-width: 2;
}

.project-workspace-summary span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.project-input-slot {
  width: 100%;
  margin-bottom: 30px;
}

.project-sessions-list {
  width: var(--chat-content-width, 76%);
  max-width: var(--chat-content-max-width, 760px);
  background-color: transparent !important;
}

.project-session-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.project-session-item {
  width: 100%;
  min-height: 54px;
  border: 0;
  border-radius: 10px;
  background: transparent !important;
  color: rgb(var(--v-theme-on-surface));
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 8px 10px 8px 0;
  cursor: pointer;
  text-align: left;
}

.project-session-item:hover {
  background-color: rgba(var(--v-theme-on-surface), 0.04) !important;
}

.project-session-item:hover .session-actions {
  opacity: 1;
  visibility: visible;
}

.project-session-copy {
  min-width: 0;
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 2px;
}

.project-session-title {
  overflow: hidden;
  font-size: 15px;
  font-weight: 520;
  line-height: 20px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.project-session-time {
  color: rgba(var(--v-theme-on-surface), 0.52);
  font-size: 13px;
  line-height: 18px;
}

.session-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  flex: 0 0 auto;
  opacity: 0;
  transition: opacity 0.14s ease;
  visibility: hidden;
}

.project-session-action {
  width: 32px;
  height: 32px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: rgba(var(--v-theme-on-surface), 0.72);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}

.project-session-action:hover {
  background: rgba(var(--v-theme-on-surface), 0.06);
  color: rgb(var(--v-theme-on-surface));
}

.delete-session-btn {
  color: rgb(var(--v-theme-error));
}

.no-sessions-in-project {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 24px 0;
  color: rgba(var(--v-theme-on-surface), 0.52);
}

.no-sessions-in-project p {
  margin: 8px 0 0;
  font-size: 14px;
}

@media (max-width: 768px) {
  .project-sessions-container {
    padding: 28px 14px 32px;
  }

  .project-header,
  .project-sessions-list {
    width: calc(100% - 20px);
    max-width: 100%;
  }

  .project-header-title {
    font-size: 24px;
  }

  .session-actions {
    opacity: 1;
    visibility: visible;
  }
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
