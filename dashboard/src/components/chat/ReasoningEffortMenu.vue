<template>
  <StyledMenu
    v-model="menuOpen"
    location="top end"
    :offset="8"
    :disabled="disabled"
  >
    <template #activator="{ props: activatorProps }">
      <button
        v-bind="activatorProps"
        type="button"
        class="reasoning-effort-trigger"
        :class="{
          'is-open': menuOpen,
          'is-off': modelValue === 'none',
        }"
        :disabled="disabled"
        :aria-label="tm('reasoningEffort.label')"
        :aria-expanded="menuOpen"
      >
        <span class="reasoning-effort-text">{{
          tm(`reasoningEffort.levels.${modelValue || 'default'}`)
        }}</span>
        <ChevronDown
          :size="14"
          :stroke-width="1.75"
          class="reasoning-effort-chevron"
        />
        <v-tooltip
          activator="parent"
          location="top"
          :disabled="menuOpen || disabled"
          >{{ tm("reasoningEffort.label") }}</v-tooltip
        >
      </button>
    </template>
    <div class="reasoning-effort-menu-header">
      {{ tm("reasoningEffort.label") }}
    </div>
    <v-list-item
      v-for="level in ['', ...levels]"
      :key="level"
      class="styled-menu-item reasoning-effort-option"
      rounded="md"
      :active="level === modelValue"
      @click="emit('update:modelValue', level)"
    >
      <v-list-item-title class="reasoning-effort-option-title">{{
        tm(`reasoningEffort.levels.${level || 'default'}`)
      }}</v-list-item-title>
      <template #append>
        <Check
          v-if="level === modelValue"
          :size="15"
          :stroke-width="2"
          class="reasoning-effort-check"
        />
      </template>
    </v-list-item>
  </StyledMenu>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { Check, ChevronDown } from "@lucide/vue";
import StyledMenu from "@/components/shared/StyledMenu.vue";
import { useModuleI18n } from "@/i18n/composables";

withDefaults(
  defineProps<{
    modelValue: string;
    levels: string[];
    disabled?: boolean;
  }>(),
  {
    disabled: false,
  },
);

const emit = defineEmits<{
  "update:modelValue": [value: string];
}>();

const { tm } = useModuleI18n("features/chat");
const menuOpen = ref(false);
</script>

<style scoped>
.reasoning-effort-trigger {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 32px;
  max-width: 128px;
  padding: 0 9px 0 10px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.14);
  border-radius: 999px;
  background: rgba(var(--v-theme-on-surface), 0.025);
  color: rgba(var(--v-theme-on-surface), 0.82);
  cursor: pointer;
  font: inherit;
  font-size: 12.5px;
  font-weight: 500;
  line-height: 1;
  white-space: nowrap;
  transition:
    background-color 0.16s ease,
    border-color 0.16s ease,
    color 0.16s ease;
}

.reasoning-effort-trigger:hover:not(:disabled),
.reasoning-effort-trigger.is-open {
  border-color: rgba(var(--v-theme-on-surface), 0.28);
  background: rgba(var(--v-theme-on-surface), 0.06);
  color: rgb(var(--v-theme-on-surface));
}

.reasoning-effort-trigger:focus-visible {
  outline: 2px solid rgba(var(--v-theme-primary), 0.45);
  outline-offset: 2px;
}

.reasoning-effort-trigger:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.reasoning-effort-trigger.is-off {
  border-style: dashed;
  border-color: rgba(var(--v-theme-on-surface), 0.16);
  background: transparent;
  color: rgba(var(--v-theme-on-surface), 0.56);
}

.reasoning-effort-chevron {
  flex: 0 0 auto;
  opacity: 0.6;
  transition: transform 0.16s ease;
}

.reasoning-effort-trigger.is-open .reasoning-effort-chevron {
  transform: rotate(180deg);
}

.reasoning-effort-text {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}

.reasoning-effort-menu-header {
  padding: 4px 10px 6px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.02em;
  color: rgba(var(--v-theme-on-surface), 0.52);
  user-select: none;
}

.reasoning-effort-option {
  min-width: 136px;
}

.reasoning-effort-option-title {
  font-size: 13px;
}

.reasoning-effort-check {
  color: rgb(var(--v-theme-primary));
  margin-inline-start: 12px;
}

@media (max-width: 768px) {
  .reasoning-effort-trigger {
    height: 30px;
    min-width: 0;
    max-width: none;
    padding: 0 7px 0 8px;
    gap: 4px;
    font-size: 12px;
  }
}
</style>
