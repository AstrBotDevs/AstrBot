import { ref, computed } from 'vue';
import axios from 'axios';
import { useRouter } from 'vue-router';

export interface Session {
    session_id: string;
    display_name: string | null;
    updated_at: string;
    platform_id: string;
    creator: string;
    is_group: number;
    created_at: string;
}

export function useSessions(chatboxMode: boolean = false) {
    const router = useRouter();
    const sessions = ref<Session[]>([]);
    const selectedSessions = ref<string[]>([]);
    const currSessionId = ref('');
    const pendingSessionId = ref<string | null>(null);

    // 编辑标题相关
    const editTitleDialog = ref(false);
    const editingTitle = ref('');
    const editingSessionId = ref('');

    const getCurrentSession = computed(() => {
        if (!currSessionId.value) return null;
        return sessions.value.find(s => s.session_id === currSessionId.value);
    });

    async function getSessions() {
        try {
            const response = await axios.get('/api/chat/sessions');
            sessions.value = response.data.data;

            // 处理待加载的会话
            if (pendingSessionId.value) {
                const session = sessions.value.find(s => s.session_id === pendingSessionId.value);
                if (session) {
                    selectedSessions.value = [pendingSessionId.value];
                    pendingSessionId.value = null;
                }
            } else if (currSessionId.value) {
                // 如果当前有选中的会话，确保它在列表中并被选中
                const session = sessions.value.find(s => s.session_id === currSessionId.value);
                if (session) {
                    selectedSessions.value = [currSessionId.value];
                }
            } else if (sessions.value.length > 0) {
                // 默认选择第一个会话
                const firstSession = sessions.value[0];
                selectedSessions.value = [firstSession.session_id];
            }
        } catch (err: any) {
            if (err.response?.status === 401) {
                router.push('/auth/login?redirect=/chatbox');
            }
            console.error(err);
        }
    }

    async function newSession() {
        try {
            const response = await axios.get('/api/chat/new_session');
            const sessionId = response.data.data.session_id;
            currSessionId.value = sessionId;

            // 更新 URL
            const basePath = chatboxMode ? '/chatbox' : '/chat';
            router.push(`${basePath}/${sessionId}`);
            
            await getSessions();
            
            // 确保新创建的会话被选中高亮
            selectedSessions.value = [sessionId];
            
            return sessionId;
        } catch (err) {
            console.error(err);
            throw err;
        }
    }

    async function deleteSession(sessionId: string) {
        try {
            await axios.get('/api/chat/delete_session?session_id=' + sessionId);
            await getSessions();
            currSessionId.value = '';
            selectedSessions.value = [];
        } catch (err) {
            console.error(err);
        }
    }

    function showEditTitleDialog(sessionId: string, title: string) {
        editingSessionId.value = sessionId;
        editingTitle.value = title || '';
        editTitleDialog.value = true;
    }

    async function saveTitle() {
        if (!editingSessionId.value) return;

        const trimmedTitle = editingTitle.value.trim();
        try {
            await axios.post('/api/chat/update_session_display_name', {
                session_id: editingSessionId.value,
                display_name: trimmedTitle
            });

            // 更新本地会话标题
            const session = sessions.value.find(s => s.session_id === editingSessionId.value);
            if (session) {
                session.display_name = trimmedTitle;
            }
            editTitleDialog.value = false;
        } catch (err) {
            console.error('重命名会话失败:', err);
        }
    }

    function updateSessionTitle(sessionId: string, title: string) {
        const session = sessions.value.find(s => s.session_id === sessionId);
        if (session) {
            session.display_name = title;
        }
    }

    function newChat(closeMobileSidebar?: () => void) {
        currSessionId.value = '';
        selectedSessions.value = [];
        
        const basePath = chatboxMode ? '/chatbox' : '/chat';
        router.push(basePath);
        
        if (closeMobileSidebar) {
            closeMobileSidebar();
        }
    }

    return {
        sessions,
        selectedSessions,
        currSessionId,
        pendingSessionId,
        editTitleDialog,
        editingTitle,
        editingSessionId,
        getCurrentSession,
        getSessions,
        newSession,
        deleteSession,
        showEditTitleDialog,
        saveTitle,
        updateSessionTitle,
        newChat
    };
}
