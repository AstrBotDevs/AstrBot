<template>
  <div>
    <div class="project-section-header">
      <v-btn
        variant="text"
        class="project-btn"
        prepend-icon="mdi-folder-outline"
        @click="toggleExpanded"
      >
        {{ tm("project.title") }}
        <template #append>
          <v-icon size="small">
            {{ expanded ? "mdi-chevron-up" : "mdi-chevron-down" }}
          </v-icon>
        </template>
      </v-btn>
      <v-btn
        icon="mdi-plus"
        size="x-small"
        variant="text"
        :title="tm('project.create')"
        @click="$emit('createProject')"
      />
    </div>

    <v-expand-transition>
      <div v-show="expanded" class="project-list-wrap">
        <v-list
          density="compact"
          nav
          class="project-list"
          style="background-color: transparent"
        >
          <template v-for="project in projects" :key="project.project_id">
            <v-list-item
              rounded="lg"
              class="project-item"
              :class="{ active: selectedProjectId === project.project_id }"
              @click="handleProjectClick(project)"
            >
              <template #prepend>
                <span class="project-emoji">{{ project.emoji || "📁" }}</span>
              </template>
              <v-list-item-title class="project-title">
                {{ project.title }}
              </v-list-item-title>
              <template #append>
                <div class="project-actions" @click.stop>
                  <v-btn
                    icon="mdi-pencil"
                    size="x-small"
                    variant="text"
                    class="project-action-btn"
                    :title="tm('project.edit')"
                    @click="$emit('editProject', project)"
                  />
                  <v-btn
                    icon="mdi-delete"
                    size="x-small"
                    variant="text"
                    class="project-action-btn"
                    color="error"
                    :title="tm('actions.deleteChat')"
                    @click="handleDeleteProject(project)"
                  />
                  <v-btn
                    :icon="
                      isProjectExpanded(project.project_id)
                        ? 'mdi-chevron-up'
                        : 'mdi-chevron-down'
                    "
                    size="x-small"
                    variant="text"
                    class="project-action-btn"
                    @click="toggleProject(project.project_id)"
                  />
                </div>
              </template>
            </v-list-item>

            <v-expand-transition>
              <div
                v-show="isProjectExpanded(project.project_id)"
                class="project-session-list"
              >
                <div
                  v-if="loadingProjectIds.includes(project.project_id)"
                  class="project-session-empty"
                >
                  {{ tm("project.loadingSessions") }}
                </div>
                <template
                  v-else-if="projectSessionList(project.project_id).length"
                >
                  <div
                    v-for="session in projectSessionList(project.project_id)"
                    :key="session.session_id"
                    class="project-session-item"
                    :class="{ active: activeSessionId === session.session_id }"
                    role="button"
                    tabindex="0"
                    @click="$emit('selectSession', session.session_id)"
                    @keydown.enter="$emit('selectSession', session.session_id)"
                    @keydown.space.prevent="
                      $emit('selectSession', session.session_id)
                    "
                  >
                    <span class="project-session-title">
                      {{ sessionTitle(session) }}
                    </span>
                    <v-progress-circular
                      v-if="sessionRunning(session.session_id)"
                      class="project-session-progress"
                      indeterminate
                      size="14"
                      width="2"
                    />
                    <span class="project-session-actions" @click.stop>
                      <v-btn
                        icon="mdi-pencil"
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
                      />
                      <v-btn
                        icon="mdi-delete"
                        size="x-small"
                        variant="text"
                        class="project-action-btn"
                        color="error"
                        :title="tm('actions.deleteChat')"
                        @click="handleDeleteSession(project.project_id, session)"
                      />
                    </span>
                  </div>
                </template>
                <div v-else class="project-session-empty">
                  {{ tm("project.noSessions") }}
                </div>
              </div>
            </v-expand-transition>
          </template>
        </v-list>
      </div>
    </v-expand-transition>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from "vue";
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
  projectSessions?: Record<string, ProjectSession[]>;
  loadingProjectIds?: string[];
  selectedProjectId?: string | null;
  activeSessionId?: string | null;
  isSessionRunning?: (sessionId: string) => boolean;
  initialExpanded?: boolean;
}

const props = withDefaults(defineProps<Props>(), {
  projectSessions: () => ({}),
  loadingProjectIds: () => [],
  selectedProjectId: null,
  activeSessionId: null,
  initialExpanded: false,
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

const expanded = ref(readProjectsExpanded());
const expandedProjectIds = ref<Set<string>>(readExpandedProjectIds());

watch(
  () => props.selectedProjectId,
  (projectId) => {
    if (projectId) setProjectExpanded(projectId, true);
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

function readProjectsExpanded() {
  const savedState = localStorage.getItem("projectsExpanded");
  if (savedState === null) return props.initialExpanded;
  try {
    return Boolean(JSON.parse(savedState));
  } catch {
    return props.initialExpanded;
  }
}

function readExpandedProjectIds() {
  try {
    const raw = localStorage.getItem("chat.projectExpandedIds");
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    return new Set(
      Array.isArray(parsed)
        ? parsed.filter((item): item is string => typeof item === "string")
        : [],
    );
  } catch {
    return new Set<string>();
  }
}

function toggleExpanded() {
  expanded.value = !expanded.value;
  localStorage.setItem("projectsExpanded", JSON.stringify(expanded.value));
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

function setProjectExpanded(projectId: string, nextExpanded: boolean) {
  if (isProjectExpanded(projectId) === nextExpanded) return;
  const next = new Set(expandedProjectIds.value);
  if (nextExpanded) next.add(projectId);
  else next.delete(projectId);
  expandedProjectIds.value = next;
  persistExpandedProjectIds();
  emit("toggleProject", projectId, nextExpanded);
}

function toggleProject(projectId: string) {
  setProjectExpanded(projectId, !isProjectExpanded(projectId));
}

function handleProjectClick(project: Project) {
  setProjectExpanded(project.project_id, true);
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
.project-section-header {
  display: flex;
  align-items: center;
  padding: 0 8px;
  opacity: 0.7;
}

.project-btn {
  flex: 1;
  justify-content: flex-start;
  background-color: transparent !important;
  border-radius: 20px;
  padding: 8px !important;
  text-transform: none;
}

.project-list-wrap {
  padding: 0 8px;
}

.project-item,
.project-session-item {
  border-radius: 16px !important;
  margin-bottom: 2px;
}

.project-item {
  padding: 4px 8px !important;
}

.project-item:hover,
.project-item.active,
.project-session-item:hover,
.project-session-item.active {
  background-color: rgba(103, 58, 183, 0.08);
}

.project-emoji {
  font-size: 16px;
  margin-right: 6px;
}

.project-title,
.project-session-title {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  font-weight: 500;
}

.project-actions,
.project-session-actions {
  display: flex;
  align-items: center;
  gap: 2px;
  opacity: 0;
  visibility: hidden;
  transition: opacity 0.2s ease;
}

.project-item:hover .project-actions,
.project-session-item:hover .project-session-actions,
.project-session-item:focus-within .project-session-actions {
  opacity: 1;
  visibility: visible;
}

.project-action-btn {
  opacity: 0.75;
}

.project-action-btn:hover {
  opacity: 1;
}

.project-session-list {
  padding: 0 0 4px 24px;
}

.project-session-item {
  min-height: 30px;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 4px 4px 12px;
  cursor: pointer;
}

.project-session-title {
  flex: 1;
}

.project-session-progress {
  flex: 0 0 auto;
}

.project-session-empty {
  padding: 5px 12px;
  color: rgba(var(--v-theme-on-surface), 0.56);
  font-size: 12px;
}
</style>
