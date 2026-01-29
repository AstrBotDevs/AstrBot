<template>
    <div class="tool-call-item">
        <div class="tool-call-line" role="button" tabindex="0"
            @click="toggleExpanded"
            @keydown.enter="toggleExpanded"
            @keydown.space.prevent="toggleExpanded">
            <slot name="label" :expanded="isExpanded" />
        </div>
        <transition name="tool-call-fade">
            <div v-if="isExpanded" class="tool-call-inline-details" :class="{ 'is-dark': isDark }">
                <slot name="details" />
            </div>
        </transition>
    </div>
</template>

<script setup>
import { ref } from 'vue';

const props = defineProps({
    isDark: {
        type: Boolean,
        default: false
    }
});

const isExpanded = ref(false);

const toggleExpanded = () => {
    isExpanded.value = !isExpanded.value;
};
</script>

<style scoped>
.tool-call-line {
    font-size: 14px;
    color: var(--v-theme-secondaryText);
    opacity: 0.85;
    cursor: pointer;
    user-select: none;
    transition: color 0.2s ease, opacity 0.2s ease;
    display: inline-flex;
    align-items: center;
    gap: 6px;
}

.tool-call-line:hover {
    color: var(--v-theme-secondary);
    opacity: 1;
}

.tool-call-inline-details {
    margin-top: 6px;
    padding: 8px 10px;
    border-left: 2px solid var(--v-theme-border);
    border-radius: 6px;
    background-color: rgba(0, 0, 0, 0.02);
}

.tool-call-inline-details.is-dark {
    background-color: rgba(255, 255, 255, 0.04);
    border-left-color: rgba(255, 255, 255, 0.15);
}

.tool-call-fade-enter-active,
.tool-call-fade-leave-active {
    transition: opacity 0.1s ease;
}

.tool-call-fade-enter-from,
.tool-call-fade-leave-to {
    opacity: 0;
}
</style>
