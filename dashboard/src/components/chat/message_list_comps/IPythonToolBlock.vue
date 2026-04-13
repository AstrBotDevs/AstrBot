<template>
    <div class="ipython-tool-block" :class="{ compact: !showHeader }">
        <div v-if="displayExpanded" class="py-3 animate-fade-in">
            <!-- Code Section -->
            <div class="code-section">
                <div v-if="shikiReady && code" class="code-highlighted"
                    v-html="highlightedCode"></div>
                <pre v-else class="code-fallback"
                    :class="{ 'dark-theme': isDark }">{{ code || 'No code available' }}</pre>
            </div>

            <!-- Result Section -->
            <div v-if="result" class="result-section">
                <div class="result-label">
                    {{ tm('ipython.output') }}:
                </div>
                <pre class="result-content"
                    :class="{ 'dark-theme': isDark }">{{ formattedResult }}</pre>
            </div>
        </div>
    </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue';
import { useModuleI18n } from '@/i18n/composables';
import { ensureShikiLanguages, escapeHtml, renderShikiCode } from '@/utils/shiki';

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
    },
    showHeader: {
        type: Boolean,
        default: true
    },
    forceExpanded: {
        type: Boolean,
        default: null
    }
});

const { tm } = useModuleI18n('features/chat');
const isExpanded = ref(props.initialExpanded);
const shikiHighlighter = ref(null);
const shikiReady = ref(false);

const code = computed(() => {
    try {
        if (props.toolCall.args && props.toolCall.args.code) {
            return props.toolCall.args.code;
        }
    } catch (err) {
        console.error('Failed to get iPython code:', err);
    }
    return null;
});

const result = computed(() => props.toolCall.result);

const formattedResult = computed(() => {
    if (!result.value) return '';
    try {
        const parsed = JSON.parse(result.value);
        return JSON.stringify(parsed, null, 2);
    } catch {
        return result.value;
    }
});

const highlightedCode = computed(() => {
    if (!shikiReady.value || !shikiHighlighter.value || !code.value) {
        return '';
    }
    try {
        return renderShikiCode(
            shikiHighlighter.value,
            code.value,
            'python',
            props.isDark ? 'dark' : 'light'
        );
    } catch (err) {
        console.error('Failed to highlight code:', err);
        return `<pre><code>${escapeHtml(code.value)}</code></pre>`;
    }
});

const displayExpanded = computed(() => {
    if (props.forceExpanded === null) {
        return isExpanded.value;
    }
    return props.forceExpanded;
});

onMounted(async () => {
    try {
        shikiHighlighter.value = await ensureShikiLanguages(['python']);
        shikiReady.value = true;
    } catch (err) {
        console.error('Failed to initialize Shiki:', err);
    }
});
</script>

<style scoped>
.ipython-tool-block {
    margin-bottom: 12px;
    margin-top: 6px;
}

.ipython-tool-block.compact {
    margin: 0;
}

.py-3 {
    padding-top: 12px;
    padding-bottom: 12px;
}

.code-section {
    margin-bottom: 12px;
}

.code-highlighted {
    border-radius: 6px;
    overflow: hidden;
    font-size: 14px;
    line-height: 1.5;
    overflow-x: auto;
}

:deep(.code-highlighted pre.shiki) {
    margin: 0;
    padding: 16px;
    border-radius: 6px;
    overflow: auto;
}

:deep(.code-highlighted pre.shiki code) {
    display: block;
    padding: 0;
    background: transparent;
    border-radius: 0;
}

.code-fallback {
    margin: 0;
    padding: 12px;
    border-radius: 6px;
    overflow-x: auto;
    font-size: 13px;
    line-height: 1.5;
    background-color: #f5f5f5;
}

.code-fallback.dark-theme {
    background-color: rgb(var(--v-theme-codeBg));
}

.result-section {
    margin-top: 12px;
}

.result-label {
    font-size: 12px;
    font-weight: 600;
    color: var(--v-theme-secondaryText);
    margin-bottom: 6px;
    opacity: 0.8;
}

.result-content {
    margin: 0;
    padding: 12px;
    border-radius: 6px;
    overflow-x: auto;
    font-size: 13px;
    line-height: 1.5;
    background-color: #f5f5f5;
    max-height: 300px;
    overflow-y: auto;
}

.result-content.dark-theme {
    background-color: rgb(var(--v-theme-codeBg));
}

.animate-fade-in {
    animation: fadeIn 0.2s ease-in-out;
}

:deep(.code-highlighted pre) {
    background-color: transparent !important;
}

@keyframes fadeIn {
    from {
        opacity: 0;
    }

    to {
        opacity: 1;
    }
}
</style>
