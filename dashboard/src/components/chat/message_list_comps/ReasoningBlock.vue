<template>
    <div class="reasoning-block" :class="{ 'reasoning-block--dark': isDark }">
        <div class="reasoning-header" @click="toggleExpanded">
            <v-icon size="small" class="reasoning-icon" :class="{ 'rotate-90': isExpanded }">
                mdi-chevron-right
            </v-icon>
            <span class="reasoning-title">
                {{ tm('reasoning.thinking') }}
            </span>
        </div>
        <div v-if="isExpanded" class="reasoning-content animate-fade-in">
            <MarkdownRender :content="reasoning" class="reasoning-text markdown-content"
                :typewriter="false" :is-dark="isDark" :style="isDark ? { opacity: '0.85' } : {}" />
        </div>
    </div>
</template>

<script setup>
import { ref } from 'vue';
import { useModuleI18n } from '@/i18n/composables';
import { MarkdownRender } from 'markstream-vue';

const props = defineProps({
    reasoning: {
        type: String,
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

const toggleExpanded = () => {
    isExpanded.value = !isExpanded.value;
};
</script>

<style scoped>


/* Reasoning 区块样式 */
.reasoning-container {
    margin-bottom: 12px;
    margin-top: 6px;
    border: 1px solid var(--v-theme-border);
    border-radius: 20px;
    overflow: hidden;
    width: fit-content;
}

.reasoning-header {
    display: inline-flex;
    align-items: center;
    padding: 8px 8px;
    cursor: pointer;
    user-select: none;
    transition: background-color 0.2s ease;
    border-radius: 20px;
}

.reasoning-header:hover {
    background-color: rgba(103, 58, 183, 0.08);
}

.reasoning-header.is-dark:hover {
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

.rotate-90 {
    transform: rotate(90deg);
}

</style>
