import { ref } from 'vue';
import axios from 'axios';
import type { Project } from '@/components/chat/ProjectList.vue';

export function useProjects() {
    const projects = ref<Project[]>([]);
    const selectedProjectId = ref<string | null>(null);

    async function getProjects() {
        try {
            const res = await axios.get('/api/chatui_project/list');
            if (res.data.status === 'ok') {
                projects.value = res.data.data || [];
                
            }
        } catch (error) {
            console.error('Failed to fetch projects:', error);
        }
    }

    async function createProject(title: string, emoji?: string, description?: string) {
        try {
            const res = await axios.post('/api/chatui_project/create', {
                title,
                emoji: emoji || '📁',
                description
            });
            if (res.data.status === 'ok') {
                await getProjects();
                return res.data.data;
            }
        } catch (error) {
            console.error('Failed to create project:', error);
        }
    }

    async function updateProject(projectId: string, title?: string, emoji?: string, description?: string) {
        try {
            const res = await axios.post('/api/chatui_project/update', {
                project_id: projectId,
                title,
                emoji,
                description
            });
            if (res.data.status === 'ok') {
                await getProjects();
            }
        } catch (error) {
            console.error('Failed to update project:', error);
        }
    }

    async function deleteProject(projectId: string) {
        try {
            const res = await axios.get('/api/chatui_project/delete', { 
                params: { project_id: projectId }
            });
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
            const res = await axios.post('/api/chatui_project/add_session', {
                session_id: sessionId,
                project_id: projectId
            });
            return res.data.status === 'ok';
        } catch (error) {
            console.error('Failed to add session to project:', error);
            return false;
        }
    }

    async function removeSessionFromProject(sessionId: string) {
        try {
            const res = await axios.post('/api/chatui_project/remove_session', {
                session_id: sessionId
            });
            return res.data.status === 'ok';
        } catch (error) {
            console.error('Failed to remove session from project:', error);
            return false;
        }
    }

    async function getProjectSessions(projectId: string) {
        try {
            const res = await axios.get('/api/chatui_project/get_sessions', { 
                params: { project_id: projectId }
            });
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
