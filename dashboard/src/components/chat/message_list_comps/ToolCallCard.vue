<template>
    <div class="tool-call-card" :class="{ 'is-dark': isDark, 'expanded': isExpanded }" :style="isDark ? {
        backgroundColor: 'rgba(40, 60, 100, 0.4)',
        borderColor: 'rgba(100, 140, 200, 0.4)'
    } : {}">
        <!-- Header -->
        <div class="tool-call-header" :class="{ 'is-dark': isDark }" @click="toggleExpanded">
            <v-icon size="small" class="tool-call-expand-icon" :class="{ 'expanded': isExpanded }">
                mdi-chevron-right
            </v-icon>
            <v-icon size="small" class="tool-call-icon">mdi-wrench-outline</v-icon>
            <div class="tool-call-info">
                <span class="tool-call-name">{{ toolCall.name }}</span>
            </div>
            <span class="tool-call-status"
                :class="{ 'status-running': !toolCall.finished_ts, 'status-finished': toolCall.finished_ts }">
                <template v-if="toolCall.finished_ts">
                    <v-icon size="x-small" class="status-icon">mdi-check-circle</v-icon>
                    {{ formatDuration(toolCall.finished_ts - toolCall.ts) }}
                </template>
                <template v-else>
                    <v-icon size="x-small" class="status-icon spinning">mdi-loading</v-icon>
                    {{ elapsedTime }}
                </template>
            </span>
        </div>

        <!-- Details -->
        <div v-if="isExpanded" class="tool-call-details" :style="isDark ? {
            borderTopColor: 'rgba(100, 140, 200, 0.3)',
            backgroundColor: 'rgba(30, 45, 70, 0.5)'
        } : {}">
            <!-- ID -->
            <div class="tool-call-detail-row">
                <span class="detail-label">ID:</span>
                <code class="detail-value" :style="isDark ? { backgroundColor: 'transparent' } : {}">
            {{ toolCall.id }}
        </code>
            </div>

            <!-- Args -->
            <div class="tool-call-detail-row">
                <span class="detail-label">Args:</span>
                <pre class="detail-value detail-json" :style="isDark ? { backgroundColor: 'transparent' } : {}">{{
                    JSON.stringify(toolCall.args, null, 2) }}</pre>
            </div>

            <!-- Result -->
            <div v-if="toolCall.result" class="tool-call-detail-row">
                <span class="detail-label">Result:</span>
                <pre class="detail-value detail-json detail-result"
                    :style="isDark ? { backgroundColor: 'transparent' } : {}">{{
            formattedResult }}</pre>
            </div>
        </div>
    </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue';

const props = defineProps({
    toolCall: {
        type: Object,
        required: true
    },
    isDark: {
        type: Boolean,
        default: false
    },
    initialExpanded: {
        type: Boolean,
        default: false
    }
});

const isExpanded = ref(props.initialExpanded);
const currentTime = ref(Date.now() / 1000);
let timer = null;

const elapsedTime = computed(() => {
    if (props.toolCall.finished_ts) return '';
    const elapsed = currentTime.value - props.toolCall.ts;
    return formatDuration(elapsed);
});

const formattedResult = computed(() => {
    if (!props.toolCall.result) return '';
    try {
        const parsed = JSON.parse(props.toolCall.result);
        return JSON.stringify(parsed, null, 2);
    } catch {
        return props.toolCall.result;
    }
});

const formatDuration = (seconds) => {
    if (seconds < 1) {
        return `${Math.round(seconds * 1000)}ms`;
    } else if (seconds < 60) {
        return `${seconds.toFixed(1)}s`;
    } else {
        const minutes = Math.floor(seconds / 60);
        const secs = Math.round(seconds % 60);
        return `${minutes}m ${secs}s`;
    }
};

const toggleExpanded = () => {
    isExpanded.value = !isExpanded.value;
};

const updateTime = () => {
    currentTime.value = Date.now() / 1000;
};

onMounted(() => {
    // Update time periodically if tool call is running
    if (!props.toolCall.finished_ts) {
        timer = setInterval(updateTime, 100);
    }
});

onUnmounted(() => {
    if (timer) {
        clearInterval(timer);
    }
});
</script>

<style scoped>
.tool-call-card {
    border-radius: 8px;
    overflow: hidden;
    background-color: #eff3f6;
    margin: 8px 0px;
    width: fit-content;
    min-width: 320px;
    max-width: 100%;
    transition: all 0.1s ease;
}

.tool-call-card.expanded {
    width: 100%;
}

.tool-call-header {
    display: flex;
    align-items: center;
    padding: 10px 12px;
    cursor: pointer;
    user-select: none;
    transition: background-color;
    gap: 8px;
}

.tool-call-header:hover {
    background-color: rgba(169, 194, 219, 0.15);
}

.tool-call-header.is-dark:hover {
    background-color: rgba(100, 150, 200, 0.2);
}

.tool-call-expand-icon {
    color: var(--v-theme-secondary);
    transition: transform 0.2s ease;
    flex-shrink: 0;
}

.tool-call-expand-icon.expanded {
    transform: rotate(90deg);
}

.tool-call-icon {
    color: var(--v-theme-secondary);
    flex-shrink: 0;
}

.tool-call-info {
    display: flex;
    flex-direction: column;
    gap: 2px;
    flex: 1;
    min-width: 0;
}

.tool-call-name {
    font-size: 13px;
    font-weight: 600;
    color: var(--v-theme-secondary);
}

.tool-call-status {
    margin-left: 8px;
    display: flex;
    align-items: center;
    gap: 4px;
    font-size: 12px;
    font-weight: 500;
    flex-shrink: 0;
}

.tool-call-status.status-running {
    color: #ff9800;
}

.tool-call-status.status-finished {
    color: #4caf50;
}

.tool-call-status .status-icon {
    font-size: 14px;
}

.tool-call-status .status-icon.spinning {
    animation: spin 1s linear infinite;
}

.tool-call-details {
    padding: 12px;
    background-color: rgba(255, 255, 255, 0.5);
    animation: fadeIn 0.2s ease-in-out;
}

.tool-call-detail-row {
    display: flex;
    flex-direction: column;
    margin-bottom: 8px;
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
    padding: 4px 8px;
    border-radius: 4px;
    word-break: break-all;
}

.detail-json {
    font-family: 'Fira Code', 'Consolas', monospace;
    white-space: pre-wrap;
    max-height: 200px;
    overflow-y: auto;
    margin: 0;
}

.detail-result {
    max-height: 300px;
    background-color: transparent;
}

.animate-fade-in {
    animation: fadeIn 0.2s ease-in-out;
}

@keyframes fadeIn {
    from {
        opacity: 0;
    }

    to {
        opacity: 1;
    }
}

@keyframes spin {
    from {
        transform: rotate(0deg);
    }

    to {
        transform: rotate(360deg);
    }
}
</style>
