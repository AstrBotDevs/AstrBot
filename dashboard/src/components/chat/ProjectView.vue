<template>
  <div class="project-sessions-container fade-in">
    <div class="project-header">
      <div class="project-header-info">
        <span class="project-header-emoji">{{ project?.emoji || '📁' }}</span>
        <h2 class="project-header-title">{{ project?.title }}</h2>
      </div>
      <p v-if="project?.description" class="project-header-description">
        {{ project.description }}
      </p>
    </div>

    <v-card flat class="project-sessions-list">
      <v-list v-if="sessions.length > 0">
        <v-list-item
          v-for="session in sessions"
          :key="session.session_id"
          class="project-session-item"
          rounded="md"
          @click="$emit('selectSession', session.session_id)"
        >
          <v-list-item-title>
            {{ session.display_name || tm('conversation.newConversation') }}
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
                @click.stop="handleDeleteSession(session)"
              />
            </div>
          </template>
        </v-list-item>
      </v-list>
      <div v-else class="no-sessions-in-project">
        <v-icon
          icon="mdi-message-outline"
          size="large"
          color="on-surface-variant"
        ></v-icon>
        <p>{{ tm('project.noSessions') }}</p>
      </div>
    </v-card>

    <div class="project-input-slot">
      <slot></slot>
    </div>

    <v-card flat class="project-workspace-card">
      <div class="workspace-toolbar">
        <v-icon size="18">mdi-folder-open-outline</v-icon>
        <span class="workspace-title">{{ tm('workspace.title') }}</span>
        <span class="workspace-path">{{ workspacePath || '/' }}</span>
        <v-spacer />
        <v-btn
          icon="mdi-refresh"
          size="small"
          variant="text"
          :aria-label="tm('workspace.refresh')"
          :title="tm('workspace.refresh')"
          @click="loadWorkspace"
        />
      </div>
      <v-list density="compact" class="workspace-list">
        <v-list-item
          v-for="entry in workspaceEntries"
          :key="entry.path"
          :title="entry.name"
          :subtitle="
            entry.type === 'file'
              ? formatSize(entry.size)
              : tm('workspace.directory')
          "
          @click="openWorkspaceEntry(entry)"
        >
          <template #prepend>
            <v-icon>{{
              entry.type === 'directory'
                ? 'mdi-folder-outline'
                : 'mdi-file-outline'
            }}</v-icon>
          </template>
        </v-list-item>
        <v-list-item
          v-if="!workspaceEntries.length"
          :title="tm('workspace.empty')"
        />
      </v-list>
      <pre
        v-if="workspacePreview && !workspacePreview.binary"
        class="workspace-preview"
        >{{ workspacePreview.content }}</pre>
      <div v-else-if="workspacePreview?.binary" class="workspace-binary">
        {{
          tm('workspace.binaryFile', {
            size: formatSize(workspacePreview.size),
          })
        }}
      </div>
    </v-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from 'vue';
import { useModuleI18n } from '@/i18n/composables';
import { chatApi } from '@/api/v1/chat';
import type { Project } from '@/components/chat/ProjectList.vue';
import { askForConfirmation, useConfirmDialog } from '@/utils/confirmDialog';

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

const { tm } = useModuleI18n('features/chat');

interface WorkspaceEntry {
  name: string;
  path: string;
  type: 'directory' | 'file';
  size: number;
  readable: boolean;
}

const workspacePath = ref('');
const workspaceEntries = ref<WorkspaceEntry[]>([]);
const workspacePreview = ref<{
  content?: string;
  size: number;
  binary: boolean;
} | null>(null);

async function loadWorkspace() {
  if (!props.project?.project_id) return;
  const response = await chatApi.listProjectWorkspaceFiles(
    props.project.project_id,
    workspacePath.value,
  );
  if (response.data.status === 'ok') {
    workspaceEntries.value = response.data.data?.entries || [];
  }
}

async function openWorkspaceEntry(entry: WorkspaceEntry) {
  if (!props.project?.project_id) return;
  workspacePreview.value = null;
  if (entry.type === 'directory') {
    workspacePath.value = entry.path;
    await loadWorkspace();
    return;
  }
  if (entry.readable) {
    const response = await chatApi.previewProjectWorkspaceFile(
      props.project.project_id,
      entry.path,
    );
    if (response.data.status === 'ok') {
      workspacePreview.value = response.data.data || null;
    }
  }
}

function formatSize(size: number): string {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KiB`;
  return `${(size / 1024 / 1024).toFixed(1)} MiB`;
}

watch(
  () => props.project?.project_id,
  () => {
    workspacePath.value = '';
    workspacePreview.value = null;
    void loadWorkspace();
  },
);
onMounted(() => void loadWorkspace());

const confirmDialog = useConfirmDialog();

function formatDate(dateString: string): string {
  return new Date(dateString).toLocaleString();
}

async function handleDeleteSession(session: Session) {
  const sessionTitle =
    session.display_name || tm('conversation.newConversation');
  const message = tm('conversation.confirmDelete', { name: sessionTitle });
  if (await askForConfirmation(message, confirmDialog)) {
    emit('deleteSession', session.session_id);
  }
}
</script>

<style scoped>
.project-sessions-container {
  height: 100%;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 32px;
  overflow: hidden;
}

.project-header {
  flex: 0 0 auto;
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
  color: var(--v-theme-on-surface-variant);
  margin: 0;
}

.project-input-slot {
  flex: 0 0 auto;
  width: 100%;
  padding-top: 18px;
}

.project-sessions-list {
  flex: 1;
  min-height: 0;
  width: 100%;
  max-width: 680px;
  overflow-y: auto;
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

.project-workspace-card {
  flex: 0 0 auto;
  width: 100%;
  max-width: 680px;
  margin-top: 16px;
}

.workspace-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
}

.workspace-path {
  font-family: monospace;
  font-size: 12px;
}

.workspace-list {
  max-height: 220px;
  overflow-y: auto;
}

.workspace-preview {
  max-height: 260px;
  overflow: auto;
  padding: 12px;
  white-space: pre-wrap;
  font-size: 12px;
  background: rgba(0, 0, 0, 0.04);
}

.workspace-binary {
  padding: 12px;
  opacity: 0.7;
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

@media (max-width: 760px) {
  .project-sessions-container {
    padding: 24px 14px 12px;
  }
}
</style>
