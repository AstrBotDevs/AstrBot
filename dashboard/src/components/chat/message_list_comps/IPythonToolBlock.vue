<template>
    <div class="ipython-tool-block" :class="{ compact: !showHeader }">
        <div v-if="displayExpanded" class="py-3 animate-fade-in">
            <!-- Code Section (matches ToolResultView result-code style) -->
            <div class="code-section">
                <div
                    v-if="shikiReady && code"
                    class="code-highlighted code-result-shiki"
                    v-html="highlightedCode"
                ></div>
                <pre v-else class="code-fallback">{{ code || 'No code available' }}</pre>
            </div>

            <!-- Result Section (matches ToolResultView result-code style) -->
            <div v-if="result" class="result-section">
                <div class="result-label">
                    {{ tm('ipython.output') }}:
                </div>
                <pre class="result-content">{{ formattedResult }}</pre>
                <div v-if="resultNotice" class="result-suffix">{{ resultNotice }}</div>
            </div>
        </div>
    </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue';
import { useModuleI18n } from '@/i18n/composables';
import { ensureShikiLanguages, escapeHtml, renderShikiCode } from '@/utils/shiki';
import { findSystemNoticeIndex } from '@/utils/systemNotice';

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
    let text = result.value;
    const idx = findSystemNoticeIndex(text);
    if (idx >= 0) {
        text = text.slice(0, idx).trim();
    }
    try {
        const parsed = JSON.parse(text);
        return JSON.stringify(parsed, null, 2);
    } catch {
        return text;
    }
});

const resultNotice = computed(() => {
    if (!result.value) return null;
    const idx = findSystemNoticeIndex(result.value);
    if (idx < 0) return null;
    return result.value.slice(idx).trim();
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
    font-size: inherit;
    line-height: inherit;
}

.ipython-tool-block.compact {
    margin: 0;
}

.py-3 {
    padding-top: 12px;
    padding-bottom: 12px;
}

/* ── Code section (matches ToolResultView .result-code) ──────── */

.code-section {
    margin-bottom: 8px;
}

/* Fallback (non-Shiki) code block */
.code-fallback {
    margin: 0;
    padding: 8px 10px;
    border-radius: 4px;
    overflow-x: auto;
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    font-size: 11.5px;
    line-height: 1.55;
    background: rgba(var(--v-theme-on-surface), 0.04);
    white-space: pre-wrap;
    word-break: break-all;
    max-height: 300px;
    overflow-y: auto;
}

/* Shiki highlighted code — mirrors ToolResultView .result-code-shiki */
.code-result-shiki {
    padding: 0;
    border-radius: 4px;
    overflow: hidden;
}

:deep(.code-result-shiki pre.shiki) {
    margin: 0;
    padding: 8px 10px;
    border-radius: 4px;
    overflow: auto;
    max-height: 300px;
    font-size: 11.5px;
    line-height: 1.55;
    tab-size: 4;
}

:deep(.code-result-shiki pre.shiki code) {
    display: block;
    padding: 0;
    background: transparent;
    font-family: inherit;
    font-size: inherit;
    line-height: inherit;
}

/* ── Result section ─────────────────────────────────────────── */

.result-section {
    margin-top: 8px;
}

.result-label {
    font-size: 11px;
    font-weight: 600;
    color: rgba(var(--v-theme-on-surface), 0.55);
    margin-bottom: 4px;
    opacity: 0.8;
}

.result-content {
    margin: 0;
    padding: 8px 10px;
    border-radius: 4px;
    overflow-x: auto;
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    font-size: 11.5px;
    line-height: 1.55;
    background: rgba(var(--v-theme-on-surface), 0.04);
    white-space: pre-wrap;
    word-break: break-all;
    max-height: 300px;
    overflow-y: auto;
}

/* ── System notice suffix ───────────────────────────────────── */
.result-suffix {
    margin-top: 6px;
    padding: 4px 8px;
    border-radius: 4px;
    background: rgba(var(--v-theme-on-surface), 0.03);
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    font-size: 11px;
    line-height: 1.55;
    color: rgba(var(--v-theme-on-surface), 0.55);
    white-space: pre-wrap;
    word-break: break-word;
}

.animate-fade-in {
    animation: fadeIn 0.2s ease-in-out;
}

@keyframes fadeIn {
    from { opacity: 0; }
    to { opacity: 1; }
}
</style>
