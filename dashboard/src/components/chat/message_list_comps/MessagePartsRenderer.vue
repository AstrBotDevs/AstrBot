<template>
    <template v-for="(renderPart, renderIndex) in getRenderParts(parts)" :key="renderPart.key">
        <!-- Grouped Tool Calls (consecutive tool_call parts) -->
        <div v-if="renderPart.type === 'tool_group'" class="tool-call-compact">
            <transition-group name="tool-call-item" tag="div" class="tool-call-items">
                <ToolCallItem v-for="(toolCall, tcIndex) in renderPart.toolCalls" :key="toolCall.id" :is-dark="isDark">
                    <template #label="{ expanded }">
                        <v-icon size="x-small" v-if="toolCall.name.includes('web_search') || toolCall.name.includes('tavily')">
                            mdi-web
                        </v-icon>
                        <v-icon size="x-small" v-else-if="toolCall.name === 'astrbot_execute_shell'">
                            mdi-console-line
                        </v-icon>
                        <v-icon size="x-small" v-else>
                            mdi-wrench
                        </v-icon>
                        {{ tm('actions.toolCallUsed', { name: toolCall.name }) }}
                        <span style="opacity: 0.6;">{{ toolCall.finished_ts ? formatDuration(toolCall.finished_ts -
                            toolCall.ts) : getElapsedTime(toolCall.ts) }}</span>
                        <v-icon size="x-small" class="tool-call-chevron" :class="{ rotated: expanded }">
                            mdi-chevron-right
                        </v-icon>
                    </template>
                    <template #details>
                        <div class="tool-call-detail-row">
                            <span class="detail-label">ID:</span>
                            <code class="detail-value">{{ toolCall.id }}</code>
                        </div>
                        <div class="tool-call-detail-row">
                            <span class="detail-label">Args:</span>
                            <pre class="detail-value detail-json">{{ formatToolArgs(toolCall.args) }}</pre>
                        </div>
                        <div v-if="toolCall.result" class="tool-call-detail-row">
                            <span class="detail-label">Result:</span>
                            <pre
                                class="detail-value detail-json detail-result">{{ formatToolResult(toolCall.result) }}</pre>
                        </div>
                    </template>
                </ToolCallItem>
            </transition-group>
        </div>

        <!-- iPython Tool Block -->
        <ToolCallItem v-else-if="renderPart.type === 'ipython'" :is-dark="isDark" style="margin: 8px 0 4px;">
            <template #label="{ expanded }">
                <v-icon size="x-small">
                    mdi-code-json
                </v-icon>
                <span class="ipython-label">{{ tm('actions.pythonCodeAnalysis') }}</span>
                <span style="opacity: 0.6;">{{ renderPart.toolCall.finished_ts ?
                    formatDuration(renderPart.toolCall.finished_ts -
                        renderPart.toolCall.ts) : getElapsedTime(renderPart.toolCall.ts) }}</span>
                <v-icon size="small" class="ipython-icon" :class="{ rotated: expanded }">
                    mdi-chevron-right
                </v-icon>
            </template>
            <template #details>
                <IPythonToolBlock :tool-call="renderPart.toolCall" :is-dark="isDark" :show-header="false"
                    :force-expanded="true" />
            </template>
        </ToolCallItem>

        <!-- Text (Markdown) -->
        <MarkdownRender
            v-else-if="renderPart.part.type === 'plain' && renderPart.part.text && renderPart.part.text.trim()"
            custom-id="message-list" :custom-html-tags="['ref']" :content="renderPart.part.text" :typewriter="false"
            class="markdown-content" :is-dark="isDark" :monacoOptions="{ theme: isDark ? 'vs-dark' : 'vs-light' }" />

        <!-- Image -->
        <div v-else-if="renderPart.part.type === 'image' && renderPart.part.embedded_url" class="embedded-images">
            <div class="embedded-image">
                <img :src="renderPart.part.embedded_url" class="bot-embedded-image"
                    @click="emitOpenImage(renderPart.part.embedded_url)" />
            </div>
        </div>

        <!-- Audio -->
        <div v-else-if="renderPart.part.type === 'record' && renderPart.part.embedded_url" class="embedded-audio">
            <audio controls class="audio-player">
                <source :src="renderPart.part.embedded_url" type="audio/wav">
                {{ t('messages.errors.browser.audioNotSupported') }}
            </audio>
        </div>

        <!-- Files -->
        <div v-else-if="renderPart.part.type === 'file' && renderPart.part.embedded_file" class="embedded-files">
            <div class="embedded-file">
                <a v-if="renderPart.part.embedded_file.url" :href="renderPart.part.embedded_file.url"
                    :download="renderPart.part.embedded_file.filename" class="file-link" :class="{ 'is-dark': isDark }"
                    :style="isDark ? {
                        backgroundColor: 'rgba(255, 255, 255, 0.05)',
                        borderColor: 'rgba(255, 255, 255, 0.1)',
                        color: 'var(--v-theme-secondary)'
                    } : {}">
                    <v-icon size="small" class="file-icon"
                        :style="isDark ? { color: 'var(--v-theme-secondary)' } : {}">mdi-file-document-outline</v-icon>
                    <span class="file-name">{{ renderPart.part.embedded_file.filename }}</span>
                </a>
                <a v-else @click="emitDownloadFile(renderPart.part.embedded_file)" class="file-link file-link-download"
                    :class="{ 'is-dark': isDark }" :style="isDark ? {
                        backgroundColor: 'rgba(255, 255, 255, 0.05)',
                        borderColor: 'rgba(255, 255, 255, 0.1)',
                        color: 'var(--v-theme-secondary)'
                    } : {}">
                    <v-icon size="small" class="file-icon"
                        :style="isDark ? { color: 'var(--v-theme-secondary)' } : {}">mdi-file-document-outline</v-icon>
                    <span class="file-name">{{ renderPart.part.embedded_file.filename }}</span>
                    <v-icon v-if="downloadingFiles?.has(renderPart.part.embedded_file.attachment_id)" size="small"
                        class="download-icon">mdi-loading mdi-spin</v-icon>
                    <v-icon v-else size="small" class="download-icon">mdi-download</v-icon>
                </a>
            </div>
        </div>
    </template>
</template>

<script setup>
import { useI18n, useModuleI18n } from '@/i18n/composables';
import { MarkdownRender } from 'markstream-vue';
import IPythonToolBlock from './IPythonToolBlock.vue';
import ToolCallItem from './ToolCallItem.vue';

const props = defineProps({
    parts: {
        type: Array,
        required: true
    },
    isDark: {
        type: Boolean,
        default: false
    },
    currentTime: {
        type: Number,
        default: 0
    },
    downloadingFiles: {
        type: Object,
        default: () => new Set()
    }
});

const emit = defineEmits(['open-image-preview', 'download-file']);
const { t } = useI18n();
const { tm } = useModuleI18n('features/chat');

const emitOpenImage = (url) => {
    emit('open-image-preview', url);
};

const emitDownloadFile = (file) => {
    emit('download-file', file);
};

const formatDuration = (seconds) => {
    if (seconds < 1) {
        return `${Math.round(seconds * 1000)}ms`;
    }
    if (seconds < 60) {
        return `${seconds.toFixed(1)}s`;
    }
    const minutes = Math.floor(seconds / 60);
    const secs = Math.round(seconds % 60);
    return `${minutes}m ${secs}s`;
};

const getElapsedTime = (startTs) => {
    const elapsed = props.currentTime - startTs;
    return formatDuration(elapsed);
};

const formatToolResult = (result) => {
    if (!result) return '';
    if (typeof result === 'string') {
        try {
            const parsed = JSON.parse(result);
            return JSON.stringify(parsed, null, 2);
        } catch {
            return result;
        }
    }
    return JSON.stringify(result, null, 2);
};

const formatToolArgs = (args) => {
    if (!args) return '';
    if (typeof args === 'string') {
        try {
            const parsed = JSON.parse(args);
            return JSON.stringify(parsed, null, 2);
        } catch {
            return args;
        }
    }
    return JSON.stringify(args, null, 2);
};

const isIPythonTool = (toolCall) => {
    return toolCall.name === 'astrbot_execute_ipython' || toolCall.name === 'astrbot_execute_python';
};

const getRenderParts = (messageParts) => {
    if (!Array.isArray(messageParts)) return [];
    const rendered = [];
    let pendingToolCalls = [];
    let groupIndex = 0;

    const flushPending = (endIndex) => {
        if (!pendingToolCalls.length) return;
        rendered.push({
            type: 'tool_group',
            toolCalls: pendingToolCalls,
            key: `tool-group-${groupIndex}-${endIndex}`
        });
        pendingToolCalls = [];
        groupIndex += 1;
    };

    messageParts.forEach((part, idx) => {
        if (part?.type === 'tool_call' && Array.isArray(part.tool_calls) && part.tool_calls.length) {
            part.tool_calls.forEach((toolCall, tcIndex) => {
                if (isIPythonTool(toolCall)) {
                    flushPending(idx - 1);
                    rendered.push({
                        type: 'ipython',
                        toolCall,
                        key: `ipython-${idx}-${tcIndex}`
                    });
                    return;
                }

                pendingToolCalls.push(toolCall);
            });
            return;
        }

        flushPending(idx - 1);
        rendered.push({
            type: 'part',
            part,
            key: `part-${idx}`
        });
    });

    flushPending(messageParts.length - 1);
    return rendered;
};
</script>

<style scoped>
.tool-call-compact {
    display: flex;
    flex-direction: column;
    gap: 8px;
    margin: 8px 0 4px;
}

.tool-call-group-title {
    font-size: 13px;
    color: var(--v-theme-secondaryText);
    opacity: 0.7;
}

.tool-call-items {
    display: flex;
    flex-direction: column;
    gap: 8px;
}

.tool-call-detail-row {
    display: flex;
    flex-direction: column;
    margin-bottom: 6px;
}

.tool-call-detail-row:last-child {
    margin-bottom: 0;
}

.detail-label {
    font-size: 11px;
    font-weight: 600;
    color: var(--v-theme-secondaryText);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 4px;
}

.detail-value {
    font-size: 12px;
    color: var(--v-theme-primaryText);
    background-color: transparent;
    padding: 2px 6px;
    border-radius: 4px;
    word-break: break-word;
}

.detail-json {
    font-family: 'Fira Code', 'Consolas', monospace;
    white-space: pre-wrap;
    max-height: 220px;
    overflow-y: auto;
    margin: 0;
}

.detail-result {
    max-height: 320px;
    background-color: transparent;
}

.tool-call-item-enter-active,
.tool-call-item-leave-active {
    transition: all 0.2s ease;
}

.tool-call-item-enter-from,
.tool-call-item-leave-to {
    opacity: 0;
    transform: translateY(-4px);
}

.ipython-icon,
.tool-call-chevron {
    margin-left: 6px;
    transition: transform 0.2s ease;
}

.ipython-icon.rotated {
    transform: rotate(90deg);
}

.tool-call-chevron.rotated {
    transform: rotate(90deg);
}
</style>
