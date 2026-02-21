import { ref, computed } from 'vue';
import axios from 'axios';
import { useRouter } from 'vue-router';
import { buildWebchatUmoDetails, getStoredSelectedChatConfigId } from '@/utils/chatConfigBinding';

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

    // TODO: Remove debug log
    console.warn('[useSessions] composable initialized', { chatboxMode });

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
            // TODO: Remove debug log
            console.warn('[useSessions] newSession() entered', { chatboxMode });

            const selectedConfigId = getStoredSelectedChatConfigId();
            // TODO: Remove debug log
            console.warn('[useSessions] Stored chat selected config', { selectedConfigId });
            const response = await axios.get('/api/chat/new_session');
            const sessionId = response.data.data.session_id;
            const platformId = response.data.data.platform_id;

            // TODO: Remove debug log
            console.warn('[useSessions] New session created', { sessionId, platformId });
            currSessionId.value = sessionId;

            if (selectedConfigId && selectedConfigId !== 'default' && platformId === 'webchat') {
                const umoDetails = buildWebchatUmoDetails(sessionId, false);

                // TODO: Remove debug log
                console.warn('[useSessions] Binding config to new session', {
                    sessionId,
                    selectedConfigId,
                    umo: umoDetails.umo,
                    username: umoDetails.username
                });

                try {
                    const updateRes = await axios.post('/api/config/umo_abconf_route/update', {
                        umo: umoDetails.umo,
                        conf_id: selectedConfigId
                    });

                    // TODO: Remove debug log
                    console.warn('[useSessions] Route update response', {
                        status: updateRes.status,
                        data: updateRes.data
                    });

                    try {
                        const routesRes = await axios.get('/api/config/umo_abconf_routes');
                        const routing = routesRes.data?.data?.routing || {};
                        // TODO: Remove debug log
                        console.warn('[useSessions] Routing table check', {
                            umo: umoDetails.umo,
                            boundConfId: routing[umoDetails.umo],
                            totalEntries: Object.keys(routing).length
                        });
                    } catch (err) {
                        const axiosErr = err as any;
                        // TODO: Remove debug log
                        console.warn('[useSessions] Failed to fetch routing table after update', {
                            message: axiosErr?.message,
                            status: axiosErr?.response?.status,
                            data: axiosErr?.response?.data
                        });
                    }
                } catch (err) {
                    const axiosErr = err as any;
                    // TODO: Remove debug log
                    console.error('[useSessions] Failed to bind config to session', {
                        sessionId,
                        selectedConfigId,
                        message: axiosErr?.message,
                        status: axiosErr?.response?.status,
                        data: axiosErr?.response?.data
                    });
                }
            } else {
                // TODO: Remove debug log
                console.warn('[useSessions] Skip binding config to new session', {
                    sessionId,
                    selectedConfigId,
                    platformId
                });
            }

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
