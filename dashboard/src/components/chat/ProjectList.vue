<template>
  <section class="sidebar-section project-list-shell">
    <div class="sidebar-section-header">
      <span>{{ tm("project.title") }}</span>
      <v-btn
        icon
        size="x-small"
        variant="text"
        class="section-action-btn"
        :title="tm('project.create')"
        @click="$emit('createProject')"
      >
        <Plus :size="18" />
      </v-btn>
    </div>

    <div class="project-list-wrap">
      <div v-for="project in projects" :key="project.project_id">
        <div
          class="project-row project-item"
          :class="{ active: selectedProjectId === project.project_id }"
          role="button"
          tabindex="0"
          @click="handleProjectClick(project)"
          @keydown.enter="handleProjectClick(project)"
          @keydown.space.prevent="handleProjectClick(project)"
        >
          <span class="project-emoji">{{ project.emoji || "📁" }}</span>
          <span class="project-title-wrap">
            <span class="project-title">{{ project.title }}</span>
            <ChevronDown
              v-if="isProjectExpanded(project.project_id)"
              :size="16"
              class="project-chevron"
            />
            <ChevronRight v-else :size="16" class="project-chevron" />
          </span>
          <span class="project-actions" @click.stop>
            <v-btn
              icon
              size="x-small"
              variant="text"
              class="project-action-btn"
              :title="tm('project.edit')"
              @click="$emit('editProject', project)"
            >
              <Pencil :size="15" />
            </v-btn>
            <v-btn
              icon
              size="x-small"
              variant="text"
              class="project-action-btn"
              :title="tm('actions.deleteChat')"
              @click="handleDeleteProject(project)"
            >
              <Trash2 :size="15" />
            </v-btn>
          </span>
        </div>

        <Transition name="project-session-fade">
          <div
            v-if="isProjectExpanded(project.project_id)"
            class="project-session-list"
          >
            <div
              v-if="loadingProjectIds.includes(project.project_id)"
              class="project-session-empty"
            >
              {{ tm("project.loadingSessions") }}
            </div>
            <template v-else-if="projectSessionList(project.project_id).length">
              <div
                v-for="session in projectSessionList(project.project_id)"
                :key="session.session_id"
                class="project-session-row"
                :class="{ active: activeSessionId === session.session_id }"
                role="button"
                tabindex="0"
                @click="$emit('selectSession', session.session_id)"
                @keydown.enter="$emit('selectSession', session.session_id)"
                @keydown.space.prevent="$emit('selectSession', session.session_id)"
              >
                <span class="project-session-title">
                  {{ sessionTitle(session) }}
                </span>
                <span class="project-session-actions" @click.stop>
                  <v-btn
                    icon
                    size="x-small"
                    variant="text"
                    class="project-action-btn"
                    :title="tm('conversation.editDisplayName')"
                    @click="
                      $emit(
                        'editSessionTitle',
                        session.session_id,
                        session.display_name || '',
                      )
                    "
                  >
                    <Pencil :size="15" />
                  </v-btn>
                  <v-btn
                    icon
                    size="x-small"
                    variant="text"
                    class="project-action-btn"
                    :title="tm('actions.deleteChat')"
                    @click="handleDeleteSession(project.project_id, session)"
                  >
                    <Trash2 :size="15" />
                  </v-btn>
                </span>
                <v-progress-circular
                  v-if="sessionRunning(session.session_id)"
                  class="project-session-progress"
                  indeterminate
                  size="14"
                  width="2"
                />
              </div>
            </template>
            <div v-else class="project-session-empty">
              {{ tm("project.noSessions") }}
            </div>
          </div>
        </Transition>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ref, watch } from "vue";
import {
  ChevronDown,
  ChevronRight,
  Pencil,
  Plus,
  Trash2,
} from "@lucide/vue";
import { useModuleI18n } from "@/i18n/composables";
import { askForConfirmation, useConfirmDialog } from "@/utils/confirmDialog";

export interface Project {
  project_id: string;
  title: string;
  emoji?: string;
  description?: string;
  workspace_type?: "session" | "project" | "custom";
  workspace_path?: string | null;
  resolved_workspace_path?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProjectSession {
  session_id: string;
  display_name?: string | null;
  updated_at: string;
}

interface Props {
  projects: Project[];
  projectSessions: Record<string, ProjectSession[]>;
  loadingProjectIds: string[];
  selectedProjectId?: string | null;
  activeSessionId?: string | null;
  isSessionRunning?: (sessionId: string) => boolean;
}

const props = withDefaults(defineProps<Props>(), {
  selectedProjectId: null,
  activeSessionId: null,
});

const emit = defineEmits<{
  selectProject: [projectId: string];
  createProject: [];
  editProject: [project: Project];
  deleteProject: [projectId: string];
  toggleProject: [projectId: string, expanded: boolean];
  selectSession: [sessionId: string];
  editSessionTitle: [sessionId: string, title: string];
  deleteSession: [sessionId: string, projectId: string];
}>();

const { tm } = useModuleI18n("features/chat");
const confirmDialog = useConfirmDialog();

const expandedProjectIds = ref<Set<string>>(readExpandedProjectIds());

watch(
  () => props.selectedProjectId,
  (projectId) => {
    if (projectId) {
      setProjectExpanded(projectId, true);
    }
  },
);

watch(
  () => props.projects.map((project) => project.project_id).join(","),
  () => {
    const validProjectIds = new Set(
      props.projects.map((project) => project.project_id),
    );
    expandedProjectIds.value.forEach((projectId) => {
      if (validProjectIds.has(projectId)) {
        emit("toggleProject", projectId, true);
      }
    });
  },
  { immediate: true },
);

function readExpandedProjectIds() {
  try {
    const raw = localStorage.getItem("chat.projectExpandedIds");
    const parsed = raw ? JSON.parse(raw) : [];
    return new Set(Array.isArray(parsed) ? parsed.filter(Boolean) : []);
  } catch {
    return new Set<string>();
  }
}

function persistExpandedProjectIds() {
  localStorage.setItem(
    "chat.projectExpandedIds",
    JSON.stringify([...expandedProjectIds.value]),
  );
}

function isProjectExpanded(projectId: string) {
  return expandedProjectIds.value.has(projectId);
}

function setProjectExpanded(projectId: string, expanded: boolean) {
  const next = new Set(expandedProjectIds.value);
  if (expanded) {
    next.add(projectId);
  } else {
    next.delete(projectId);
  }
  expandedProjectIds.value = next;
  persistExpandedProjectIds();
  emit("toggleProject", projectId, expanded);
}

function handleProjectClick(project: Project) {
  const nextExpanded = !isProjectExpanded(project.project_id);
  setProjectExpanded(project.project_id, nextExpanded);
  emit("selectProject", project.project_id);
}

function projectSessionList(projectId: string) {
  return props.projectSessions[projectId] || [];
}

function sessionRunning(sessionId: string) {
  return props.isSessionRunning?.(sessionId) || false;
}

function sessionTitle(session: ProjectSession) {
  return session.display_name?.trim() || tm("conversation.newConversation");
}

async function handleDeleteProject(project: Project) {
  const message = tm("project.confirmDelete", { title: project.title });
  if (await askForConfirmation(message, confirmDialog)) {
    emit("deleteProject", project.project_id);
  }
}

async function handleDeleteSession(projectId: string, session: ProjectSession) {
  const message = tm("conversation.confirmDelete", {
    name: sessionTitle(session),
  });
  if (await askForConfirmation(message, confirmDialog)) {
    emit("deleteSession", session.session_id, projectId);
  }
}

</script>

<style scoped>
.project-list-shell {
  margin-top: 2px;
}

.sidebar-section-header {
  min-height: 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 10px 4px;
  color: var(--chat-section-label);
  font-size: 12px;
  font-weight: 500;
}

.section-action-btn,
.project-action-btn {
  color: var(--chat-muted);
}

.section-action-btn :deep(svg),
.project-action-btn :deep(svg),
.project-chevron {
  flex: 0 0 auto;
  stroke-width: 2;
}

.section-action-btn {
  width: 36px;
  height: 36px;
  min-width: 36px;
}

.section-action-btn:hover,
.project-action-btn:hover {
  color: rgb(var(--v-theme-on-surface));
}

.project-list-wrap,
.project-session-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.project-row,
.project-session-row {
  width: 100%;
  min-height: 30px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: inherit;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 56px 4px 10px;
  position: relative;
  box-sizing: border-box;
  cursor: pointer;
  text-align: left;
}

.project-row:hover,
.project-row.active,
.project-session-row:hover,
.project-session-row.active {
  background: var(--chat-session-active-bg);
}

.project-emoji {
  width: 18px;
  flex: 0 0 18px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 15px;
}

.project-title-wrap {
  min-width: 0;
  flex: 1;
  display: inline-flex;
  align-items: center;
  gap: 3px;
}

.project-title,
.project-session-title {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 14px;
  font-weight: 500;
}

.project-title {
  flex: 0 1 auto;
}

.project-session-title {
  flex: 1;
}

.project-chevron {
  flex: 0 0 auto;
  color: var(--chat-muted);
}

.project-actions,
.project-session-actions {
  display: flex;
  align-items: center;
  gap: 2px;
  flex-shrink: 0;
  opacity: 0;
  pointer-events: none;
  position: absolute;
  right: 0;
  top: 50%;
  transform: translateY(-50%);
  visibility: hidden;
}

.project-row:hover .project-actions,
.project-row:focus-within .project-actions,
.project-session-row:hover .project-session-actions,
.project-session-row:focus-within .project-session-actions {
  opacity: 1;
  pointer-events: auto;
  visibility: visible;
}

.project-session-list {
  padding: 2px 0 4px 26px;
}

.project-session-fade-enter-active {
  transition: opacity 0.1s ease-out;
}

.project-session-fade-leave-active {
  transition: opacity 0.08s ease-in;
}

.project-session-fade-enter-from,
.project-session-fade-leave-to {
  opacity: 0;
}

.project-session-progress {
  position: absolute;
  right: 4px;
  top: 50%;
  transform: translateY(-50%);
  flex-shrink: 0;
  transition:
    opacity 0.14s ease,
    visibility 0.14s ease;
}

.project-session-row:hover .project-session-progress,
.project-session-row:focus-within .project-session-progress {
  opacity: 0;
  visibility: hidden;
}

.project-session-empty {
  padding: 5px 10px;
  color: var(--chat-muted);
  font-size: 13px;
}
</style>
