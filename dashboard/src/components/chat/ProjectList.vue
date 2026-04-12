<template>
  <div class="project-list-shell">
    <!-- 项目按钮 -->
    <div class="project-button-wrap">
      <v-btn block variant="text" class="project-btn" @click="toggleExpanded">
        <v-icon size="20" class="project-action-icon mr-2">
          mdi-folder-outline
        </v-icon>
        <span class="project-btn-title">{{ tm("project.title") }}</span>
        <v-spacer />
        <v-icon size="18" class="project-toggle-icon">
          {{ expanded ? "mdi-chevron-up" : "mdi-chevron-down" }}
        </v-icon>
      </v-btn>
    </div>

    <!-- 项目列表 -->
    <v-expand-transition>
      <div v-show="expanded" class="project-list-wrap">
        <button
          class="project-row create-project-item"
          type="button"
          @click="$emit('createProject')"
        >
          <span class="project-emoji">
            <v-icon size="18">mdi-plus</v-icon>
          </span>
          <span class="project-title">{{ tm("project.create") }}</span>
        </button>

        <button
          v-for="project in projects"
          :key="project.project_id"
          class="project-row project-item"
          :class="{ active: selectedProjectId === project.project_id }"
          type="button"
          @click="$emit('selectProject', project.project_id)"
        >
          <span class="project-emoji">{{ project.emoji || "📁" }}</span>
          <span class="project-title">{{ project.title }}</span>
          <span class="project-actions">
            <v-btn
              icon="mdi-pencil"
              size="x-small"
              variant="text"
              class="edit-project-btn"
              @click.stop="$emit('editProject', project)"
            />
            <v-btn
              icon="mdi-delete"
              size="x-small"
              variant="text"
              class="delete-project-btn"
              color="error"
              @click.stop="handleDeleteProject(project)"
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

export interface Project {
  project_id: string;
  title: string;
  emoji?: string;
  description?: string;
  created_at: string;
  updated_at: string;
}

interface Props {
  projects: Project[];
  initialExpanded?: boolean;
  selectedProjectId?: string | null;
}

const props = withDefaults(defineProps<Props>(), {
  initialExpanded: false,
  selectedProjectId: null,
});

const emit = defineEmits<{
  selectProject: [projectId: string];
  createProject: [];
  editProject: [project: Project];
  deleteProject: [projectId: string];
}>();

const { tm } = useModuleI18n("features/chat");

const confirmDialog = useConfirmDialog();

const expanded = ref(props.initialExpanded);

// 从 localStorage 读取项目展开状态
const savedProjectsExpandedState = localStorage.getItem("projectsExpanded");
if (savedProjectsExpandedState !== null) {
  expanded.value = JSON.parse(savedProjectsExpandedState);
}

function toggleExpanded() {
  expanded.value = !expanded.value;
  localStorage.setItem("projectsExpanded", JSON.stringify(expanded.value));
}

async function handleDeleteProject(project: Project) {
  const message = tm("project.confirmDelete", { title: project.title });
  if (await askForConfirmation(message, confirmDialog)) {
    emit("deleteProject", project.project_id);
  }
}
</script>

<style scoped>
.project-list-shell {
  margin-top: 6px;
}

.project-button-wrap {
  opacity: 0.6;
}

.project-btn {
  justify-content: flex-start;
  background-color: transparent !important;
  border-radius: 8px;
  padding: 8px 12px !important;
  text-transform: none;
  font-weight: 500;
}

.project-action-icon {
  color: currentcolor;
}

.project-btn-title {
  min-width: 0;
}

.project-toggle-icon {
  margin-left: 10px;
}

.project-list-wrap {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-top: 8px;
}

.project-row {
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

.project-row:hover,
.project-row.active {
  background: var(--chat-session-active-bg);
}

.project-item:hover .project-actions {
  opacity: 1;
  visibility: visible;
}

.project-emoji {
  width: 20px;
  flex: 0 0 20px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
}

.project-title {
  min-width: 0;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 14px;
  font-weight: 500;
}

.project-actions {
  display: flex;
  gap: 2px;
  opacity: 0;
  visibility: hidden;
  transition: all 0.2s ease;
}

.edit-project-btn,
.delete-project-btn {
  opacity: 0.7;
  transition: opacity 0.2s ease;
}

.edit-project-btn:hover,
.delete-project-btn:hover {
  opacity: 1;
}

.create-project-item {
  opacity: 0.7;
}

.create-project-item:hover {
  opacity: 1;
}
</style>
