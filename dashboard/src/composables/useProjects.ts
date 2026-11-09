import { ref } from 'vue';
import { chatApi } from '@/api/v1';
import type { Project } from '@/components/chat/ProjectList.vue';

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

    async function getProjectSessions(projectId: string) {
        try {
            const res = await chatApi.listProjectSessions(projectId);
            if (res.data.status === 'ok') {
                return res.data.data || [];
            }
            return [];
        } catch (error) {
            console.error('Failed to fetch project sessions:', error);
            return [];
        }
    }

    return {
        projects,
        selectedProjectId,
        getProjects,
        createProject,
        updateProject,
        deleteProject,
        addSessionToProject,
        removeSessionFromProject,
        getProjectSessions
    };
}
