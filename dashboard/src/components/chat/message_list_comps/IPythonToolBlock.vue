<template>
    <div class="mb-3 mt-1.5">
        <div class="ipython-header" :class="{ 'expanded': isExpanded }" @click="toggleExpanded">
            <span class="ipython-label">
                {{ tm('actions.pythonCodeAnalysis') }}
            </span>
            <v-icon size="small" class="ipython-icon" :class="{ 'rotated': isExpanded }">
                mdi-chevron-right
            </v-icon>
        </div>
        <div v-if="isExpanded" class="py-3 animate-fade-in">
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
import { createHighlighter } from 'shiki';

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
        return shikiHighlighter.value.codeToHtml(code.value, {
            lang: 'python',
            theme: props.isDark ? 'min-dark' : 'github-light'
        });
    } catch (err) {
        console.error('Failed to highlight code:', err);
        return `<pre><code>${code.value}</code></pre>`;
    }
});

const toggleExpanded = () => {
    isExpanded.value = !isExpanded.value;
};

onMounted(async () => {
    try {
        shikiHighlighter.value = await createHighlighter({
            themes: ['min-dark', 'github-light'],
            langs: ['python']
        });
        shikiReady.value = true;
    } catch (err) {
        console.error('Failed to initialize Shiki:', err);
    }
});
</script>

<style scoped>
.mb-3 {
    margin-bottom: 12px;
}

.mt-1\.5 {
    margin-top: 6px;
}

.ipython-header {
    display: inline-flex;
    align-items: center;
    cursor: pointer;
    user-select: none;
    border-radius: 20px;
    opacity: 0.7;
    transition: opacity;
}

.ipython-header:hover,
.ipython-header.expanded {
    opacity: 1;
}

.ipython-label {
    font-size: 16px;
}

.ipython-icon {
    margin-left: 6px;
    transition: transform 0.2s ease;
}

.ipython-icon.rotated {
    transform: rotate(90deg);
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
    background-color: transparent;
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
</style>
