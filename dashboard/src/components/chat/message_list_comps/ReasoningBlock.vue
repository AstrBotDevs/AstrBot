<template>
    <div class="mb-3 mt-1.5 border border-gray-200 dark:border-gray-700 rounded-2xl overflow-hidden w-fit"
        :class="{ 'dark:bg-purple-900/8': isDark, 'bg-purple-50/50': !isDark }">
        <div class="inline-flex items-center px-2 py-2 cursor-pointer select-none rounded-2xl transition-colors hover:bg-purple-50/80 dark:hover:bg-purple-900/15"
            @click="toggleExpanded">
            <v-icon size="small" class="mr-1.5 text-purple-600 dark:text-purple-400 transition-transform"
                :class="{ 'rotate-90': isExpanded }">
                mdi-chevron-right
            </v-icon>
            <span class="text-sm font-medium text-purple-600 dark:text-purple-400 tracking-wide">
                {{ tm('reasoning.thinking') }}
            </span>
        </div>
        <div v-if="isExpanded" class="px-3 border-t border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-400 animate-fade-in italic">
            <MarkdownRender :content="reasoning" class="reasoning-text markdown-content text-sm leading-relaxed"
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

.reasoning-text {
    font-size: 14px;
    line-height: 1.6;
    color: var(--v-theme-secondaryText);
}
</style>
