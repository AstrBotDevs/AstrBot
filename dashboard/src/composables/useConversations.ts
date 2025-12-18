import { ref, computed } from 'vue';
import axios from 'axios';
import { useRouter } from 'vue-router';

export interface Conversation {
    cid: string;
    title: string;
    updated_at: number;
}

export function useConversations(chatboxMode: boolean = false) {
    const router = useRouter();
    const conversations = ref<Conversation[]>([]);
    const selectedConversations = ref<string[]>([]);
    const currCid = ref('');
    const pendingCid = ref<string | null>(null);

    // 编辑标题相关
    const editTitleDialog = ref(false);
    const editingTitle = ref('');
    const editingCid = ref('');

    const getCurrentConversation = computed(() => {
        if (!currCid.value) return null;
        return conversations.value.find(c => c.cid === currCid.value);
    });

    async function getConversations() {
        try {
            const response = await axios.get('/api/chat/conversations');
            conversations.value = response.data.data;

            // 处理待加载的会话
            if (pendingCid.value) {
                const conversation = conversations.value.find(c => c.cid === pendingCid.value);
                if (conversation) {
                    selectedConversations.value = [pendingCid.value];
                    pendingCid.value = null;
                }
            } else if (!currCid.value && conversations.value.length > 0) {
                // 默认选择第一个会话
                const firstConversation = conversations.value[0];
                selectedConversations.value = [firstConversation.cid];
            }
        } catch (err: any) {
            if (err.response?.status === 401) {
                router.push('/auth/login?redirect=/chatbox');
            }
            console.error(err);
        }
    }

    async function newConversation() {
        try {
            const response = await axios.get('/api/chat/new_conversation');
            const cid = response.data.data.conversation_id;
            currCid.value = cid;

            // 更新 URL
            const basePath = chatboxMode ? '/chatbox' : '/chat';
            router.push(`${basePath}/${cid}`);
            
            await getConversations();
            return cid;
        } catch (err) {
            console.error(err);
            throw err;
        }
    }

    async function deleteConversation(cid: string) {
        try {
            await axios.get('/api/chat/delete_conversation?conversation_id=' + cid);
            await getConversations();
            currCid.value = '';
            selectedConversations.value = [];
        } catch (err) {
            console.error(err);
        }
    }

    function showEditTitleDialog(cid: string, title: string) {
        editingCid.value = cid;
        editingTitle.value = title || '';
        editTitleDialog.value = true;
    }

    async function saveTitle() {
        if (!editingCid.value) return;

        const trimmedTitle = editingTitle.value.trim();
        try {
            await axios.post('/api/chat/rename_conversation', {
                conversation_id: editingCid.value,
                title: trimmedTitle
            });

            // 更新本地会话标题
            const conversation = conversations.value.find(c => c.cid === editingCid.value);
            if (conversation) {
                conversation.title = trimmedTitle;
            }
            editTitleDialog.value = false;
        } catch (err) {
            console.error('重命名对话失败:', err);
        }
    }

    function updateConversationTitle(cid: string, title: string) {
        const conversation = conversations.value.find(c => c.cid === cid);
        if (conversation) {
            conversation.title = title;
        }
    }

    function newChat(closeMobileSidebar?: () => void) {
        currCid.value = '';
        selectedConversations.value = [];
        
        const basePath = chatboxMode ? '/chatbox' : '/chat';
        router.push(basePath);
        
        if (closeMobileSidebar) {
            closeMobileSidebar();
        }
    }

    return {
        conversations,
        selectedConversations,
        currCid,
        pendingCid,
        editTitleDialog,
        editingTitle,
        editingCid,
        getCurrentConversation,
        getConversations,
        newConversation,
        deleteConversation,
        showEditTitleDialog,
        saveTitle,
        updateConversationTitle,
        newChat
    };
}
