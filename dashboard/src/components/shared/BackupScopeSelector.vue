<template>
    <div class="d-flex flex-column ga-3">
        <v-card
            v-for="group in groupStates"
            :key="group.id"
            variant="outlined"
            class="scope-group"
            :class="{ 'scope-group--selected': group.selected > 0 && !disabled }"
        >
            <div class="d-flex align-center pl-2">
                <v-checkbox-btn
                    :model-value="group.allSelected"
                    :indeterminate="group.selected > 0 && !group.allSelected"
                    :disabled="disabled || !group.selectable.length"
                    :aria-label="t(`features.settings.backup.groups.${group.id}.title`)"
                    color="primary"
                    density="default"
                    class="flex-grow-0"
                    @update:model-value="toggleGroup(group)"
                />
                <button
                    type="button"
                    class="scope-heading d-flex align-center flex-grow-1 text-left py-4 pr-4 pl-2 ga-3"
                    :aria-expanded="expanded.includes(group.id)"
                    @click="expanded = expanded.includes(group.id) ? expanded.filter(id => id !== group.id) : [...expanded, group.id]"
                >
                    <span class="flex-grow-1">
                        <span class="d-flex align-center flex-wrap ga-2 mb-1">
                            <span class="scope-title">
                                {{ t(`features.settings.backup.groups.${group.id}.title`) }}
                            </span>
                            <span class="scope-count" :class="group.selected > 0 && !disabled ? 'text-primary' : 'text-medium-emphasis'">
                                {{ t('features.settings.backup.scope.selectedCount', { selected: group.selected, total: group.selectable.length }) }}
                            </span>
                        </span>
                        <span class="scope-description d-block text-medium-emphasis">
                            {{ t(`features.settings.backup.groups.${group.id}.description`) }}
                        </span>
                    </span>
                    <v-icon :icon="expanded.includes(group.id) ? 'mdi-chevron-up' : 'mdi-chevron-down'" size="small" class="text-medium-emphasis" />
                </button>
            </div>
            <v-expand-transition>
                <div v-show="expanded.includes(group.id)">
                    <v-divider />
                    <div class="scope-details px-2 py-1">
                        <v-checkbox
                            v-for="component in group.components"
                            :key="component"
                            :model-value="modelValue"
                            :value="component"
                            :disabled="disabled || !group.selectable.includes(component)"
                            color="primary"
                            density="default"
                            hide-details
                            class="scope-item"
                            @update:model-value="$emit('update:modelValue', $event)"
                        >
                            <template #label>
                                <span class="py-3 px-2">
                                    <span class="scope-item-title d-block">
                                        {{ t(`features.settings.backup.components.${component}`) }}
                                    </span>
                                    <span class="scope-description d-block text-medium-emphasis mt-1">
                                        {{ t(`features.settings.backup.componentDescriptions.${component}`) }}
                                    </span>
                                    <span v-if="brokenComponents.includes(component)" class="scope-description d-block text-error mt-1">
                                        {{ t('features.settings.backup.import.brokenHint') }}
                                    </span>
                                    <span v-else-if="!availableComponents.includes(component)" class="scope-description d-block text-medium-emphasis mt-1">
                                        {{ t('features.settings.backup.scope.notIncluded') }}
                                    </span>
                                </span>
                            </template>
                        </v-checkbox>
                    </div>
                </div>
            </v-expand-transition>
        </v-card>
    </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useI18n } from '@/i18n/composables'

const props = defineProps({
    modelValue: { type: Array, required: true },
    groups: { type: Array, required: true },
    availableComponents: { type: Array, required: true },
    brokenComponents: { type: Array, default: () => [] },
    disabled: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue'])
const { t } = useI18n()
const expanded = ref([])

const groupStates = computed(() => props.groups.map(group => {
    const selectable = group.components.filter(component =>
        props.availableComponents.includes(component) && !props.brokenComponents.includes(component))
    const selected = selectable.filter(component => props.modelValue.includes(component)).length
    return { ...group, selectable, selected, allSelected: selectable.length > 0 && selected === selectable.length }
}))

const toggleGroup = (group) => {
    if (props.disabled || !group.selectable.length) return
    const remaining = props.modelValue.filter(component => !group.components.includes(component))
    emit('update:modelValue', group.allSelected ? remaining : [...remaining, ...group.selectable])
}

watch(() => props.brokenComponents, (broken) => {
    expanded.value = props.groups
        .filter(group => group.components.some(component => broken.includes(component)))
        .map(group => group.id)
}, { immediate: true })
</script>

<style scoped>
.scope-group {
    border-color: rgba(var(--v-theme-on-surface), 0.12);
    transition: border-color 0.15s ease, background-color 0.15s ease;
}

.scope-group--selected {
    border-color: rgba(var(--v-theme-primary), 0.35);
    background-color: rgba(var(--v-theme-primary), 0.04);
}

.scope-group:hover {
    border-color: rgba(var(--v-theme-primary), 0.55);
}

.scope-heading {
    min-width: 0;
    color: inherit;
    border-radius: inherit;
}

.scope-heading:focus-visible {
    outline: 2px solid rgb(var(--v-theme-primary));
    outline-offset: -2px;
}

.scope-title {
    font-size: 0.9375rem;
    font-weight: 600;
    line-height: 1.5;
    letter-spacing: normal;
}

.scope-item-title {
    font-size: 0.875rem;
    font-weight: 500;
    line-height: 1.5;
    letter-spacing: normal;
}

.scope-description {
    font-size: 0.8125rem;
    line-height: 1.65;
    letter-spacing: normal;
    overflow-wrap: anywhere;
}

.scope-count {
    font-size: 0.75rem;
    font-weight: 500;
    line-height: 1.5;
    letter-spacing: normal;
    padding: 1px 8px;
    border-radius: 6px;
    background-color: rgba(var(--v-theme-on-surface), 0.04);
    white-space: nowrap;
}

.scope-group--selected .scope-count {
    background-color: rgba(var(--v-theme-primary), 0.08);
}

.scope-details {
    background-color: rgb(var(--v-theme-surface));
}

.scope-item + .scope-item {
    border-top: 1px solid rgba(var(--v-theme-on-surface), 0.06);
}
</style>
