<template>
    <div class="multi-chat-view">
        <div class="multi-chat-header">
            <v-btn icon="mdi-close" variant="text" @click="exitMultiMode" />
            <span class="multi-chat-title">{{ tm('multiChat.multiMode') }}</span>
        </div>
        
        <div 
            class="chat-container-wrapper" 
            ref="containerRef"
            @scroll="handleScroll"
        >
            <div class="chat-panels-track">
                <div 
                    v-for="(sessionId, index) in sessionIds" 
                    :key="sessionId"
                    class="chat-panel"
                    :style="{ 
                        zIndex: index + 1,
                        left: `${index * 16}px`
                    }"
                    :ref="el => { if (el) panelRefs[index] = el }"
                >
                    <div class="chat-panel-inner" :class="{ 'panel-stacked': shouldShowShadow(index) }">
                        <div class="session-header">
                            <span class="session-title">
                                {{ getSessionTitle(sessionId) }}
                            </span>
                        </div>
                        
                        <div class="message-list-container">
                            <MessageList 
                                :messages="sessionMessages[sessionId] || []" 
                                :isDark="isDark"
                                :isStreaming="activeSessionId === sessionId && (isStreaming || isConvRunning)"
                                :isLoadingMessages="loadingSessionIds.has(sessionId)"
                                @openImagePreview="(url) => $emit('openImagePreview', url)"
                                @replyMessage="(msg, idx) => handleReplyMessage(sessionId, msg, idx)"
                                @replyWithText="(data) => handleReplyWithText(sessionId, data)"
                                :ref="el => { if (el) messageListRefs[index] = el }"
                            />
                        </div>
                        
                        <ChatInput
                            v-model:prompt="prompts[sessionId]"
                            :stagedImagesUrl="stagedImages[sessionId] || []"
                            :stagedAudioUrl="stagedAudios[sessionId] || ''"
                            :stagedFiles="stagedFiles[sessionId] || []"
                            :disabled="isStreaming && activeSessionId === sessionId"
                            :enableStreaming="enableStreaming"
                            :isRecording="isRecording && activeSessionId === sessionId"
                            :session-id="sessionId"
                            :current-session="getSession(sessionId)"
                            :replyTo="replyToMap[sessionId]"
                            @send="handleSendMessage(sessionId)"
                            @toggleStreaming="$emit('toggleStreaming')"
                            @removeImage="(idx) => removeImage(sessionId, idx)"
                            @removeAudio="removeAudio(sessionId)"
                            @removeFile="(idx) => removeFile(sessionId, idx)"
                            @startRecording="handleStartRecording(sessionId)"
                            @stopRecording="handleStopRecording(sessionId)"
                            @pasteImage="(file) => handlePasteImage(sessionId, file)"
                            @fileSelect="(files) => handleFileSelect(sessionId, files)"
                            @clearReply="clearReply(sessionId)"
                        />
                    </div>
                </div>
            </div>
        </div>
    </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onBeforeUnmount, nextTick } from 'vue';
import { useModuleI18n } from '@/i18n/composables';
import MessageList from '@/components/chat/MessageList.vue';
import ChatInput from '@/components/chat/ChatInput.vue';
import type { Session } from '@/composables/useSessions';

interface Props {
    sessionIds: string[];
    sessions: Session[];
    isDark: boolean;
    isStreaming: boolean;
    isConvRunning: boolean;
    enableStreaming: boolean;
    isRecording: boolean;
    getSessionMessages?: (sessionId: string) => Promise<any[]>;
}

const props = withDefaults(defineProps<Props>(), {
    getSessionMessages: undefined
});

const emit = defineEmits<{
    exitMultiMode: [];
    openImagePreview: [url: string];
    sendMessage: [sessionId: string, data: any];
    toggleStreaming: [];
    startRecording: [sessionId: string];
    stopRecording: [sessionId: string];
    pasteImage: [sessionId: string, event: ClipboardEvent];
    fileSelect: [sessionId: string, files: FileList];
}>();

const { tm } = useModuleI18n('features/chat');

// 状态管理
const currentIndex = ref(0);
const scrollLeft = ref(0);
const containerRef = ref<HTMLElement | null>(null);
const panelRefs = reactive<any[]>([]);
const messageListRefs = reactive<any[]>([]);

// 每个会话的独立状态
const sessionMessages = reactive<Record<string, any[]>>({});
const prompts = reactive<Record<string, string>>({});
const stagedImages = reactive<Record<string, string[]>>({});
const stagedAudios = reactive<Record<string, string>>({});
const stagedFiles = reactive<Record<string, any[]>>({});
const replyToMap = reactive<Record<string, any>>({});
const loadingSessionIds = reactive(new Set<string>());
const activeSessionId = ref('');

// 计算属性 - 每个面板宽度为650px和视口宽度的最小值
const panelWidth = computed(() => {
    if (!containerRef.value) {
        return Math.min(650, window.innerWidth);
    }
    return Math.min(650, containerRef.value.offsetWidth);
});

// 计算面板是否应该显示阴影
function shouldShowShadow(index: number): boolean {
    if (index === 0) return false;
    // 当面板已经开始固定时（滚动超过它的位置）
    const threshold = (index - 0.98) * panelWidth.value;
    return scrollLeft.value >= threshold;
}

// 初始化所有会话的状态
onMounted(async () => {
    props.sessionIds.forEach(sessionId => {
        if (!prompts[sessionId]) prompts[sessionId] = '';
        if (!stagedImages[sessionId]) stagedImages[sessionId] = [];
        if (!stagedAudios[sessionId]) stagedAudios[sessionId] = '';
        if (!stagedFiles[sessionId]) stagedFiles[sessionId] = [];
        if (!sessionMessages[sessionId]) sessionMessages[sessionId] = [];
    });
    
    // 加载初始会话消息
    if (props.sessionIds.length > 0) {
        activeSessionId.value = props.sessionIds[0];
        // 并行加载前两个会话的消息
        const loadPromises = props.sessionIds.slice(0, 2).map(id => loadSessionMessages(id));
        await Promise.all(loadPromises);
    }
});

// 辅助函数
let scrollTimeout: number | null = null;

// 滚动处理
function handleScroll() {
    if (!containerRef.value) return;
    
    // 实时更新滚动位置
    scrollLeft.value = containerRef.value.scrollLeft;
    
    // 清除之前的定时器
    if (scrollTimeout) {
        clearTimeout(scrollTimeout);
    }
    
    // 使用防抖，滚动停止150ms后才更新currentIndex用于预加载
    scrollTimeout = window.setTimeout(() => {
        if (!containerRef.value) return;
        
        const scrollLeft = containerRef.value.scrollLeft;
        const newIndex = Math.round(scrollLeft / panelWidth.value);
        
        if (newIndex >= 0 && newIndex < props.sessionIds.length && newIndex !== currentIndex.value) {
            currentIndex.value = newIndex;
            activeSessionId.value = props.sessionIds[newIndex];
            preloadAdjacentSessions();
        }
    }, 150);
}

// 预加载相邻会话
function preloadAdjacentSessions() {
    const indicesToLoad = [
        currentIndex.value - 1,
        currentIndex.value,
        currentIndex.value + 1
    ].filter(i => i >= 0 && i < props.sessionIds.length);
    
    indicesToLoad.forEach(i => {
        const sessionId = props.sessionIds[i];
        if (!sessionMessages[sessionId] || sessionMessages[sessionId].length === 0) {
            loadSessionMessages(sessionId);
        }
    });
}

async function loadSessionMessages(sessionId: string) {
    if (loadingSessionIds.has(sessionId)) return;
    
    loadingSessionIds.add(sessionId);
    
    try {
        if (props.getSessionMessages) {
            const messages = await props.getSessionMessages(sessionId);
            sessionMessages[sessionId] = messages || [];
        }
    } catch (error) {
        console.error(`加载会话 ${sessionId} 消息失败:`, error);
        sessionMessages[sessionId] = [];
    } finally {
        loadingSessionIds.delete(sessionId);
    }
}

function getSessionTitle(sessionId: string): string {
    const session = props.sessions.find(s => s.session_id === sessionId);
    return session?.display_name || tm('conversation.newConversation');
}

function getSession(sessionId: string): Session | null {
    return props.sessions.find(s => s.session_id === sessionId) || null;
}

// 消息处理
function handleReplyMessage(sessionId: string, msg: any, index: number) {
    const messageId = msg.id;
    if (!messageId) return;
    
    let messageContent = '';
    if (typeof msg.content.message === 'string') {
        messageContent = msg.content.message;
    } else if (Array.isArray(msg.content.message)) {
        const textParts = msg.content.message
            .filter((part: any) => part.type === 'plain' && part.text)
            .map((part: any) => part.text);
        messageContent = textParts.join('');
    }
    
    if (messageContent.length > 100) {
        messageContent = messageContent.substring(0, 100) + '...';
    }
    
    replyToMap[sessionId] = {
        messageId,
        selectedText: messageContent || '[媒体内容]'
    };
}

function handleReplyWithText(sessionId: string, replyData: any) {
    const { messageId, selectedText } = replyData;
    if (!messageId) return;
    
    replyToMap[sessionId] = {
        messageId,
        selectedText
    };
}

function clearReply(sessionId: string) {
    delete replyToMap[sessionId];
}

function handleSendMessage(sessionId: string) {
    const data = {
        prompt: prompts[sessionId],
        stagedImages: stagedImages[sessionId],
        stagedAudios: stagedAudios[sessionId],
        stagedFiles: stagedFiles[sessionId],
        replyTo: replyToMap[sessionId]
    };
    
    emit('sendMessage', sessionId, data);
    
    // 清空输入
    prompts[sessionId] = '';
    stagedImages[sessionId] = [];
    stagedAudios[sessionId] = '';
    stagedFiles[sessionId] = [];
    clearReply(sessionId);
}

function removeImage(sessionId: string, index: number) {
    stagedImages[sessionId].splice(index, 1);
}

function removeAudio(sessionId: string) {
    stagedAudios[sessionId] = '';
}

function removeFile(sessionId: string, index: number) {
    stagedFiles[sessionId].splice(index, 1);
}

function handleStartRecording(sessionId: string) {
    activeSessionId.value = sessionId;
    emit('startRecording', sessionId);
}

function handleStopRecording(sessionId: string) {
    emit('stopRecording', sessionId);
}

function handlePasteImage(sessionId: string, event: ClipboardEvent) {
    emit('pasteImage', sessionId, event);
}

function handleFileSelect(sessionId: string, files: FileList) {
    emit('fileSelect', sessionId, files);
}

function exitMultiMode() {
    emit('exitMultiMode');
}

onBeforeUnmount(() => {
    // 清理定时器
    if (scrollTimeout) {
        clearTimeout(scrollTimeout);
    }
});
</script>

<style scoped>
.multi-chat-view {
    width: 100%;
    height: 100%;
    display: flex;
    flex-direction: column;
    overflow: hidden;
}

.multi-chat-header {
    display: flex;
    align-items: center;
    padding: 12px 16px;
    border-bottom: 1px solid var(--v-theme-border);
    flex-shrink: 0;
}

.multi-chat-title {
    font-size: 16px;
    font-weight: 500;
    margin-left: 8px;
}

.session-indicator {
    font-size: 14px;
    opacity: 0.7;
}

.chat-container-wrapper {
    flex: 1;
    overflow-x: auto;
    overflow-y: hidden;
    -webkit-overflow-scrolling: touch;
}

.chat-panels-track {
    display: flex;
    height: 100%;
    width: fit-content;
}

.chat-panel {
    position: sticky;
    flex-shrink: 0;
    width: min(650px, 100vw);
    height: 100%;
    background: rgb(var(--v-theme-surface));
}

.chat-panel-inner {
    width: 100%;
    height: 100%;
    display: flex;
    flex-direction: column;
    background: rgb(var(--v-theme-surface));
    border-right: 1px solid var(--v-theme-border);
    transition: box-shadow 0.3s ease;
}

.chat-panel-inner.panel-stacked {
    box-shadow: -4px 0 12px rgba(0, 0, 0, 0.10);
}

.session-header {
    padding: 12px 16px;
    border-bottom: 1px solid var(--v-theme-border);
    flex-shrink: 0;
}

.session-title {
    font-size: 14px;
    font-weight: 500;
}

.message-list-container {
    flex: 1;
    overflow: hidden;
    position: relative;
}

/* 隐藏滚动条但保持功能 */
.chat-container-wrapper::-webkit-scrollbar {
    display: none;
}

.chat-container-wrapper {
    -ms-overflow-style: none;
    scrollbar-width: none;
}
</style>
