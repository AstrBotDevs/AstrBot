import { reactive, ref } from 'vue';
import { chatApi } from '@/api/v1';
import type { Project } from '@/components/chat/ProjectList.vue';
import type { Session } from '@/composables/useSessions';

export interface ProjectSessionsPagination {
    page: number;
    hasMore: boolean;
    loading: boolean;
    error: boolean;
    append: boolean;
}

type WorkspaceType = 'session' | 'project' | 'custom';

function projectErrorMessage(error: unknown, fallback: string) {
    const responseMessage = (error as any)?.response?.data?.message;
    if (typeof responseMessage === 'string' && responseMessage.trim()) {
        return responseMessage;
    }
    const message = (error as Error)?.message;
    return message || fallback;
}

export function useProjects() {
    const projects = ref<Project[]>([]);
    const selectedProjectId = ref<string | null>(null);
    const projectSessionsById = ref<Record<string, Session[]>>({});
    const projectSessionsPagination = reactive<Record<string, ProjectSessionsPagination>>({});
    const sessionsRequestIds: Record<string, number> = {};

    async function getProjects() {
        try {
            const res = await chatApi.listProjects();
            if (res.data.status === 'ok') {
                projects.value = res.data.data || [];
                
            }
        } catch (error) {
            console.error('Failed to fetch projects:', error);
        }
    }

    async function createProject(
        title: string,
        emoji?: string,
        description?: string,
        workspaceType: WorkspaceType = 'project',
        workspacePath?: string
    ) {
        try {
            const res = await chatApi.createProject({
                title,
                emoji: emoji || '📁',
                description,
                workspace_type: workspaceType,
                workspace_path: workspacePath
            });
            if (res.data.status === 'ok') {
                await getProjects();
                return res.data.data;
            }
            throw new Error(res.data.message || 'Failed to create project');
        } catch (error) {
            console.error('Failed to create project:', error);
            throw new Error(projectErrorMessage(error, 'Failed to create project'));
        }
    }

    async function updateProject(
        projectId: string,
        title?: string,
        emoji?: string,
        description?: string,
        workspaceType?: WorkspaceType,
        workspacePath?: string
    ) {
        try {
            const res = await chatApi.updateProject(projectId, {
                title,
                emoji,
                description,
                workspace_type: workspaceType,
                workspace_path: workspacePath
            });
            if (res.data.status === 'ok') {
                await getProjects();
                return;
            }
            throw new Error(res.data.message || 'Failed to update project');
        } catch (error) {
            console.error('Failed to update project:', error);
            throw new Error(projectErrorMessage(error, 'Failed to update project'));
        }
    }

    async function deleteProject(projectId: string) {
        try {
            const res = await chatApi.deleteProject(projectId);
            if (res.data.status === 'ok') {
                sessionsRequestIds[projectId] = (sessionsRequestIds[projectId] || 0) + 1;
                delete projectSessionsById.value[projectId];
                delete projectSessionsPagination[projectId];
                await getProjects();
                if (selectedProjectId.value === projectId) {
                    selectedProjectId.value = null;
                }
            }
        } catch (error) {
            console.error('Failed to delete project:', error);
        }
    }

    async function addSessionToProject(sessionId: string, projectId: string) {
        try {
            const res = await chatApi.addProjectSession(projectId, sessionId);
            return res.data.status === 'ok';
        } catch (error) {
            console.error('Failed to add session to project:', error);
            return false;
        }
    }

    async function removeSessionFromProject(sessionId: string) {
        try {
            const res = await chatApi.removeProjectSession(sessionId);
            return res.data.status === 'ok';
        } catch (error) {
            console.error('Failed to remove session from project:', error);
            return false;
        }
    }

    async function getProjectSessions(projectId: string, append = false) {
        projectSessionsPagination[projectId] ??= {
            page: 0, hasMore: false, loading: false, error: false, append: false,
        };
        const pagination = projectSessionsPagination[projectId];
        if (append && (pagination.loading || !pagination.hasMore)) return;
        const requestId = sessionsRequestIds[projectId] = (sessionsRequestIds[projectId] || 0) + 1;
        const lastPage = append ? pagination.page + 1 : Math.max(1, pagination.page);
        const loaded: Session[] = append ? [...(projectSessionsById.value[projectId] || [])] : [];
        pagination.loading = true;
        pagination.error = false;
        pagination.append = append;
        try {
            // Refresh the loaded range after mutations, as in the regular session sidebar.
            for (let page = append ? lastPage : 1; page <= lastPage; page++) {
                const res = await chatApi.listProjectSessions(projectId, { page, page_size: 30 });
                if (requestId !== sessionsRequestIds[projectId]) return;
                if (res.data.status !== 'ok') {
                    throw new Error(res.data.message || 'Failed to load project sessions');
                }
                const payload = res.data.data;
                loaded.push(...payload.sessions);
                const hasMore = page * payload.page_size < payload.total;
                if (page === lastPage || !hasMore) {
                    projectSessionsById.value[projectId] = [...new Map(loaded.map(session => [session.session_id, session])).values()];
                    pagination.page = page;
                    pagination.hasMore = hasMore;
                    break;
                }
            }
        } catch (error) {
            if (requestId !== sessionsRequestIds[projectId]) return;
            pagination.error = true;
            console.error('Failed to fetch project sessions:', error);
        } finally {
            if (requestId === sessionsRequestIds[projectId]) pagination.loading = false;
        }
    }

    return {
        projects,
        selectedProjectId,
        projectSessionsById,
        projectSessionsPagination,
        getProjects,
        createProject,
        updateProject,
        deleteProject,
        addSessionToProject,
        removeSessionFromProject,
        getProjectSessions
    };
}
