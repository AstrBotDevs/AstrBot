<template>
    <div class="messages-container" ref="messageContainer">
        <!-- 聊天消息列表 -->
        <div class="message-list">
            <div class="message-item fade-in" v-for="(msg, index) in messages" :key="index">
                <!-- 用户消息 -->
                <div v-if="msg.content.type == 'user'" class="user-message">
                    <div class="message-bubble user-bubble" :class="{ 'has-audio': msg.content.audio_url }"
                        :style="{ backgroundColor: isDark ? '#2d2e30' : '#e7ebf4' }">
                        <pre
                            style="font-family: inherit; white-space: pre-wrap; word-wrap: break-word;">{{ msg.content.message }}</pre>

                        <!-- 图片附件 -->
                        <div class="image-attachments" v-if="msg.content.image_url && msg.content.image_url.length > 0">
                            <div v-for="(img, index) in msg.content.image_url" :key="index" class="image-attachment">
                                <img :src="img" class="attached-image" @click="$emit('openImagePreview', img)" />
                            </div>
                        </div>

                        <!-- 音频附件 -->
                        <div class="audio-attachment" v-if="msg.content.audio_url && msg.content.audio_url.length > 0">
                            <audio controls class="audio-player">
                                <source :src="msg.content.audio_url" type="audio/wav">
                                {{ t('messages.errors.browser.audioNotSupported') }}
                            </audio>
                        </div>
                    </div>
                </div>

                <!-- Bot Messages -->
                <div v-else class="bot-message">

                    <v-avatar class="bot-avatar" size="36">
                        <v-progress-circular :index="index" v-if="isStreaming && index === messages.length - 1" indeterminate size="28"
                            width="2"></v-progress-circular>
                        <v-icon v-else-if="messages[index - 1]?.content.type !== 'bot'" size="64" color="#8fb6d2">mdi-star-four-points-small</v-icon>
                    </v-avatar>
                    <div class="bot-message-content">
                        <div class="message-bubble bot-bubble">
                            <!-- Reasoning Block (Collapsible) -->
                            <div v-if="msg.content.reasoning && msg.content.reasoning.trim()" class="reasoning-container">
                                <div class="reasoning-header" @click="toggleReasoning(index)">
                                    <v-icon size="small" class="reasoning-icon">
                                        {{ isReasoningExpanded(index) ? 'mdi-chevron-down' : 'mdi-chevron-right' }}
                                    </v-icon>
                                    <span class="reasoning-label">{{ tm('reasoning.thinking') }}</span>
                                </div>
                                <div v-if="isReasoningExpanded(index)" class="reasoning-content">
                                    <div v-html="md.render(msg.content.reasoning)" class="markdown-content reasoning-text"></div>
                                </div>
                            </div>
                            
                            <!-- Text -->
                            <div v-if="msg.content.message && msg.content.message.trim()"
                                v-html="md.render(msg.content.message)" class="markdown-content"></div>

                            <!-- Image -->
                            <div class="embedded-images"
                                v-if="msg.content.embedded_images && msg.content.embedded_images.length > 0">
                                <div v-for="(img, imgIndex) in msg.content.embedded_images" :key="imgIndex"
                                    class="embedded-image">
                                    <img :src="img" class="bot-embedded-image"
                                        @click="$emit('openImagePreview', img)" />
                                </div>
                            </div>

                            <!-- Audio -->
                            <div class="embedded-audio" v-if="msg.content.embedded_audio">
                                <audio controls class="audio-player">
                                    <source :src="msg.content.embedded_audio" type="audio/wav">
                                    {{ t('messages.errors.browser.audioNotSupported') }}
                                </audio>
                            </div>
                        </div>
                        <div class="message-actions">
                            <v-btn :icon="getCopyIcon(index)" size="small" variant="text" class="copy-message-btn"
                                :class="{ 'copy-success': isCopySuccess(index) }"
                                @click="copyBotMessage(msg.content.message, index)" :title="t('core.common.copy')" />
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
</template>

<script>
import { useI18n, useModuleI18n } from '@/i18n/composables';
import MarkdownIt from 'markdown-it';
import hljs from 'highlight.js';
import 'highlight.js/styles/github.css';

const md = new MarkdownIt({
    html: false,
    breaks: true,
    linkify: true,
    highlight: function (code, lang) {
        if (lang && hljs.getLanguage(lang)) {
            try {
                return hljs.highlight(code, { language: lang }).value;
            } catch (err) {
                console.error('Highlight error:', err);
            }
        }
        return hljs.highlightAuto(code).value;
    }
});

export default {
    name: 'MessageList',
    props: {
        messages: {
            type: Array,
            required: true
        },
        isDark: {
            type: Boolean,
            default: false
        },
        isStreaming: {
            type: Boolean,
            default: false
        }
    },
    emits: ['openImagePreview'],
    setup() {
        const { t } = useI18n();
        const { tm } = useModuleI18n('features/chat');

        return {
            t,
            tm,
            md
        };
    },
    data() {
        return {
            copiedMessages: new Set(),
            isUserNearBottom: true,
            scrollThreshold: 1,
            scrollTimer: null,
            expandedReasoning: new Set(), // Track which reasoning blocks are expanded
        };
    },
    mounted() {
        this.initCodeCopyButtons();
        this.initImageClickEvents();
        this.addScrollListener();
        this.scrollToBottom();
    },
    updated() {
        this.initCodeCopyButtons();
        this.initImageClickEvents();
        if (this.isUserNearBottom) {
            this.scrollToBottom();
        }
    },
    methods: {
        // Toggle reasoning expansion state
        toggleReasoning(messageIndex) {
            if (this.expandedReasoning.has(messageIndex)) {
                this.expandedReasoning.delete(messageIndex);
            } else {
                this.expandedReasoning.add(messageIndex);
            }
            // Force reactivity
            this.expandedReasoning = new Set(this.expandedReasoning);
        },

        // Check if reasoning is expanded
        isReasoningExpanded(messageIndex) {
            return this.expandedReasoning.has(messageIndex);
        },

        // 复制代码到剪贴板
        copyCodeToClipboard(code) {
            navigator.clipboard.writeText(code).then(() => {
                console.log('代码已复制到剪贴板');
            }).catch(err => {
                console.error('复制失败:', err);
                // 如果现代API失败，使用传统方法
                const textArea = document.createElement('textarea');
                textArea.value = code;
                document.body.appendChild(textArea);
                textArea.select();
                try {
                    document.execCommand('copy');
                    console.log('代码已复制到剪贴板 (fallback)');
                } catch (fallbackErr) {
                    console.error('复制失败 (fallback):', fallbackErr);
                }
                document.body.removeChild(textArea);
            });
        },

        // 复制bot消息到剪贴板
        copyBotMessage(message, messageIndex) {
            // 获取对应的消息对象
            const msgObj = this.messages[messageIndex].content;
            let textToCopy = '';

            // 如果有文本消息，添加到复制内容中
            if (message && message.trim()) {
                // 移除HTML标签，获取纯文本
                const tempDiv = document.createElement('div');
                tempDiv.innerHTML = message;
                textToCopy = tempDiv.textContent || tempDiv.innerText || message;
            }

            // 如果有内嵌图片，添加说明
            if (msgObj && msgObj.embedded_images && msgObj.embedded_images.length > 0) {
                if (textToCopy) textToCopy += '\n\n';
                textToCopy += `[包含 ${msgObj.embedded_images.length} 张图片]`;
            }

            // 如果有内嵌音频，添加说明
            if (msgObj && msgObj.embedded_audio) {
                if (textToCopy) textToCopy += '\n\n';
                textToCopy += '[包含音频内容]';
            }

            // 如果没有任何内容，使用默认文本
            if (!textToCopy.trim()) {
                textToCopy = '[媒体内容]';
            }

            navigator.clipboard.writeText(textToCopy).then(() => {
                console.log('消息已复制到剪贴板');
                this.showCopySuccess(messageIndex);
            }).catch(err => {
                console.error('复制失败:', err);
                // 如果现代API失败，使用传统方法
                const textArea = document.createElement('textarea');
                textArea.value = textToCopy;
                document.body.appendChild(textArea);
                textArea.select();
                try {
                    document.execCommand('copy');
                    console.log('消息已复制到剪贴板 (fallback)');
                    this.showCopySuccess(messageIndex);
                } catch (fallbackErr) {
                    console.error('复制失败 (fallback):', fallbackErr);
                }
                document.body.removeChild(textArea);
            });
        },

        // 显示复制成功提示
        showCopySuccess(messageIndex) {
            this.copiedMessages.add(messageIndex);

            // 2秒后移除成功状态
            setTimeout(() => {
                this.copiedMessages.delete(messageIndex);
            }, 2000);
        },

        // 获取复制按钮图标
        getCopyIcon(messageIndex) {
            return this.copiedMessages.has(messageIndex) ? 'mdi-check' : 'mdi-content-copy';
        },

        // 检查是否为复制成功状态
        isCopySuccess(messageIndex) {
            return this.copiedMessages.has(messageIndex);
        },

        // 获取复制图标SVG
        getCopyIconSvg() {
            return '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>';
        },

        // 获取成功图标SVG
        getSuccessIconSvg() {
            return '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20,6 9,17 4,12"></polyline></svg>';
        },

        // 初始化代码块复制按钮
        initCodeCopyButtons() {
            this.$nextTick(() => {
                const codeBlocks = this.$refs.messageContainer?.querySelectorAll('pre code') || [];
                codeBlocks.forEach((codeBlock, index) => {
                    const pre = codeBlock.parentElement;
                    if (pre && !pre.querySelector('.copy-code-btn')) {
                        const button = document.createElement('button');
                        button.className = 'copy-code-btn';
                        button.innerHTML = this.getCopyIconSvg();
                        button.title = '复制代码';
                        button.addEventListener('click', () => {
                            this.copyCodeToClipboard(codeBlock.textContent);
                            // 显示复制成功提示
                            button.innerHTML = this.getSuccessIconSvg();
                            button.style.color = '#4caf50';
                            setTimeout(() => {
                                button.innerHTML = this.getCopyIconSvg();
                                button.style.color = '';
                            }, 2000);
                        });
                        pre.style.position = 'relative';
                        pre.appendChild(button);
                    }
                });
            });
        },

        initImageClickEvents() {
            this.$nextTick(() => {
                // 查找所有动态生成的图片（在markdown-content中）
                const images = document.querySelectorAll('.markdown-content img');
                images.forEach((img) => {
                    if (!img.hasAttribute('data-click-enabled')) {
                        img.style.cursor = 'pointer';
                        img.setAttribute('data-click-enabled', 'true');
                        img.onclick = () => this.$emit('openImagePreview', img.src);
                    }
                });
            });
        },

        scrollToBottom() {
            this.$nextTick(() => {
                const container = this.$refs.messageContainer;
                if (container) {
                    container.scrollTop = container.scrollHeight;
                    this.isUserNearBottom = true; // 程序滚动到底部后标记用户在底部
                }
            });
        },

        // 添加滚动事件监听器
        addScrollListener() {
            const container = this.$refs.messageContainer;
            if (container) {
                container.addEventListener('scroll', this.throttledHandleScroll);
            }
        },

        // 节流处理滚动事件
        throttledHandleScroll() {
            if (this.scrollTimer) return;

            this.scrollTimer = setTimeout(() => {
                this.handleScroll();
                this.scrollTimer = null;
            }, 50); // 50ms 节流
        },

        // 处理滚动事件
        handleScroll() {
            const container = this.$refs.messageContainer;
            if (container) {
                const { scrollTop, scrollHeight, clientHeight } = container;
                const distanceFromBottom = scrollHeight - (scrollTop + clientHeight);

                // 判断用户是否在底部附近
                this.isUserNearBottom = distanceFromBottom <= this.scrollThreshold;
            }
        },

        // 组件销毁时移除监听器
        beforeUnmount() {
            const container = this.$refs.messageContainer;
            if (container) {
                container.removeEventListener('scroll', this.throttledHandleScroll);
            }
            // 清理定时器
            if (this.scrollTimer) {
                clearTimeout(this.scrollTimer);
                this.scrollTimer = null;
            }
        }
    }
}
</script>

<style scoped>
/* 基础动画 */
@keyframes fadeIn {
    from {
        opacity: 0;
        transform: translateY(0);
    }

    to {
        opacity: 1;
        transform: translateY(0);
    }
}

.messages-container {
    height: 100%;
    max-height: 100%;
    overflow-y: auto;
    padding: 16px;
    display: flex;
    flex-direction: column;
    flex: 1;
    min-height: 0;
}

/* 消息列表样式 */
.message-list {
    max-width: 900px;
    margin: 0 auto;
    width: 100%;
}

.message-item {
    margin-bottom: 24px;
    animation: fadeIn 0.3s ease-out;
}

.user-message {
    display: flex;
    justify-content: flex-end;
    align-items: flex-start;
    gap: 12px;
}

.bot-message {
    display: flex;
    justify-content: flex-start;
    align-items: flex-start;
    gap: 12px;
}

.bot-message-content {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    max-width: 80%;
    position: relative;
}

.message-actions {
    display: flex;
    gap: 4px;
    opacity: 0;
    transition: opacity 0.2s ease;
    margin-left: 8px;
}

.bot-message:hover .message-actions {
    opacity: 1;
}

.copy-message-btn {
    opacity: 0.6;
    transition: all 0.2s ease;
    color: var(--v-theme-secondary);
}

.copy-message-btn:hover {
    opacity: 1;
    background-color: rgba(103, 58, 183, 0.1);
}

.copy-message-btn.copy-success {
    color: #4caf50;
    opacity: 1;
}

.copy-message-btn.copy-success:hover {
    color: #4caf50;
    background-color: rgba(76, 175, 80, 0.1);
}

.message-bubble {
    padding: 2px 16px;
    border-radius: 12px;
}

.user-bubble {
    color: var(--v-theme-primaryText);
    padding: 12px 18px;
    font-size: 15px;
    max-width: 60%;
    border-radius: 1.5rem;
}

.bot-bubble {
    border: 1px solid var(--v-theme-border);
    color: var(--v-theme-primaryText);
    font-size: 15px;
    max-width: 100%;
}

.user-avatar,
.bot-avatar {
    align-self: flex-start;
    margin-top: 6px;
}

/* 附件样式 */
.image-attachments {
    display: flex;
    gap: 8px;
    margin-top: 8px;
    flex-wrap: wrap;
}

.image-attachment {
    position: relative;
    display: inline-block;
}

.attached-image {
    width: 120px;
    height: 120px;
    object-fit: cover;
    border-radius: 12px;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
    transition: transform 0.2s ease;
}

.audio-attachment {
    margin-top: 8px;
    min-width: 250px;
}

/* 包含音频的消息气泡最小宽度 */
.message-bubble.has-audio {
    min-width: 280px;
}

.audio-player {
    width: 100%;
    height: 36px;
    border-radius: 18px;
}

.embedded-images {
    margin-top: 8px;
    display: flex;
    flex-direction: column;
    gap: 8px;
}

.embedded-image {
    display: flex;
    justify-content: flex-start;
}

.bot-embedded-image {
    max-width: 80%;
    width: auto;
    height: auto;
    border-radius: 8px;
    box-shadow: 0 0 10px rgba(0, 0, 0, 0.1);
    cursor: pointer;
    transition: transform 0.2s ease;
}

.bot-embedded-image:hover {
    transform: scale(1.02);
}

.embedded-audio {
    width: 300px;
    margin-top: 8px;
}

.embedded-audio .audio-player {
    width: 100%;
    max-width: 300px;
}

/* 动画类 */
.fade-in {
    animation: fadeIn 0.3s ease-in-out;
}

/* Reasoning 区块样式 */
.reasoning-container {
    margin-bottom: 12px;
    margin-top: 6px;
    border: 1px solid var(--v-theme-border);
    border-radius: 8px;
    overflow: hidden;
    width: fit-content;
}

.v-theme--dark .reasoning-container {
    background-color: rgba(103, 58, 183, 0.08);
}

.reasoning-header {
    display: inline-flex;
    align-items: center;
    padding: 8px 8px;
    cursor: pointer;
    user-select: none;
    transition: background-color 0.2s ease;
    border-radius: 8px;
}

.reasoning-header:hover {
    background-color: rgba(103, 58, 183, 0.08);
}

.v-theme--dark .reasoning-header:hover {
    background-color: rgba(103, 58, 183, 0.15);
}

.reasoning-icon {
    margin-right: 6px;
    color: var(--v-theme-secondary);
    transition: transform 0.2s ease;
}

.reasoning-label {
    font-size: 13px;
    font-weight: 500;
    color: var(--v-theme-secondary);
    letter-spacing: 0.3px;
}

.reasoning-content {
    padding: 0px 12px;
    border-top: 1px solid var(--v-theme-border);
    color: gray;
    animation: fadeIn 0.2s ease-in-out;
    font-style: italic;
}

.reasoning-text {
    font-size: 14px;
    line-height: 1.6;
    color: var(--v-theme-secondaryText);
}

.v-theme--dark .reasoning-text {
    opacity: 0.85;
}
</style>

<style>
/* Markdown内容样式 - 需要全局样式 */
.markdown-content {
    font-family: inherit;
    line-height: 1.6;
}

.markdown-content h1,
.markdown-content h2,
.markdown-content h3,
.markdown-content h4,
.markdown-content h5,
.markdown-content h6 {
    margin-top: 16px;
    margin-bottom: 10px;
    font-weight: 600;
    color: var(--v-theme-primaryText);
}

.markdown-content h1 {
    font-size: 1.8em;
    border-bottom: 1px solid var(--v-theme-border);
    padding-bottom: 6px;
}

.markdown-content h2 {
    font-size: 1.5em;
}

.markdown-content h3 {
    font-size: 1.3em;
}

.markdown-content li {
    margin-left: 16px;
    margin-bottom: 4px;
}

.markdown-content p {
    margin-top: .5rem;
    margin-bottom: .5rem;
}

.markdown-content pre {
    background-color: var(--v-theme-surface);
    padding: 12px;
    border-radius: 6px;
    overflow-x: auto;
    margin: 12px 0;
    position: relative;
}

.markdown-content code {
    background-color: rgb(var(--v-theme-codeBg));
    padding: 2px 4px;
    border-radius: 4px;
    font-family: 'Fira Code', monospace;
    font-size: 0.9em;
    color: var(--v-theme-code);
}

/* 代码块中的code标签样式 */
.markdown-content pre code {
    background-color: transparent;
    padding: 0;
    border-radius: 0;
    font-family: 'Fira Code', 'Consolas', 'Monaco', 'Courier New', monospace;
    font-size: 0.85em;
    color: inherit;
    display: block;
    overflow-x: auto;
    line-height: 1.5;
}

/* 自定义代码高亮样式 */
.markdown-content pre {
    border: 1px solid var(--v-theme-border);
    background-color: rgb(var(--v-theme-preBg));
    border-radius: 16px;
    padding: 16px;
}

/* 确保highlight.js的样式正确应用 */
.markdown-content pre code.hljs {
    background: transparent !important;
    color: inherit;
}

/* 亮色主题下的代码高亮 */
.v-theme--light .markdown-content pre {
    background-color: #f6f8fa;
}

/* 暗色主题下的代码块样式 */
.v-theme--dark .markdown-content pre {
    background-color: #0d1117 !important;
    border-color: rgba(255, 255, 255, 0.1);
}

.v-theme--dark .markdown-content pre code {
    color: #e6edf3 !important;
}

/* 暗色主题下的highlight.js样式覆盖 */
.v-theme--dark .hljs {
    background: #0d1117 !important;
    color: #e6edf3 !important;
}

.v-theme--dark .hljs-keyword,
.v-theme--dark .hljs-selector-tag,
.v-theme--dark .hljs-built_in,
.v-theme--dark .hljs-name,
.v-theme--dark .hljs-tag {
    color: #ff7b72 !important;
}

.v-theme--dark .hljs-string,
.v-theme--dark .hljs-title,
.v-theme--dark .hljs-section,
.v-theme--dark .hljs-attribute,
.v-theme--dark .hljs-literal,
.v-theme--dark .hljs-template-tag,
.v-theme--dark .hljs-template-variable,
.v-theme--dark .hljs-type,
.v-theme--dark .hljs-addition {
    color: #a5d6ff !important;
}

.v-theme--dark .hljs-comment,
.v-theme--dark .hljs-quote,
.v-theme--dark .hljs-deletion,
.v-theme--dark .hljs-meta {
    color: #8b949e !important;
}

.v-theme--dark .hljs-number,
.v-theme--dark .hljs-regexp,
.v-theme--dark .hljs-symbol,
.v-theme--dark .hljs-variable,
.v-theme--dark .hljs-template-variable,
.v-theme--dark .hljs-link,
.v-theme--dark .hljs-selector-attr,
.v-theme--dark .hljs-selector-pseudo {
    color: #79c0ff !important;
}

.v-theme--dark .hljs-function,
.v-theme--dark .hljs-class,
.v-theme--dark .hljs-title.class_ {
    color: #d2a8ff !important;
}

/* 复制按钮样式 */
.copy-code-btn {
    position: absolute;
    top: 8px;
    right: 8px;
    background: rgba(255, 255, 255, 0.9);
    border: 1px solid rgba(0, 0, 0, 0.1);
    border-radius: 4px;
    padding: 6px;
    cursor: pointer;
    opacity: 0;
    transition: all 0.2s ease;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #666;
    font-size: 12px;
    z-index: 10;
    backdrop-filter: blur(4px);
}

.copy-code-btn:hover {
    background: rgba(255, 255, 255, 1);
    color: #333;
    transform: scale(1.05);
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
}

.copy-code-btn:active {
    transform: scale(0.95);
}

.markdown-content pre:hover .copy-code-btn {
    opacity: 1;
}

.v-theme--dark .copy-code-btn {
    background: rgba(45, 45, 45, 0.9);
    border-color: rgba(255, 255, 255, 0.15);
    color: #ccc;
}

.v-theme--dark .copy-code-btn:hover {
    background: rgba(45, 45, 45, 1);
    color: #fff;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
}

.markdown-content img {
    max-width: 100%;
    border-radius: 8px;
    margin: 10px 0;
}

.markdown-content blockquote {
    border-left: 4px solid var(--v-theme-secondary);
    padding-left: 16px;
    color: var(--v-theme-secondaryText);
    margin: 16px 0;
}

.markdown-content table {
    border-collapse: collapse;
    width: 100%;
    margin: 16px 0;
}

.markdown-content th,
.markdown-content td {
    border: 1px solid var(--v-theme-background);
    padding: 8px 12px;
    text-align: left;
}

.markdown-content th {
    background-color: var(--v-theme-containerBg);
}
</style>
