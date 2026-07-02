<!--
  Author: elecvoid243
  Date: 2026-06-28
  Spec: docs/superpowers/specs/2026-06-28-dynamic-choice-box-rendering-design.md §4

  InteractiveChoiceBox: 动态渲染 LLM ask_user_choice 工具输出的选项框。
  4 状态机(pending / submitted_via_option / submitted_via_input / ignored) + a11y。
-->
<template>
  <div
    class="interactive-choice-box"
    :class="{
      'is-pending': state === 'pending',
      'is-submitted': state === 'submitted_via_option' || state === 'submitted_via_input',
      'is-ignored': state === 'ignored',
      'is-dark': isDark,
    }"
    :aria-live="state === 'ignored' ? 'polite' : undefined"
  >
    <!-- Header: title + prompt -->
    <div v-if="state !== 'ignored'" class="choice-header">
      <v-icon v-if="state === 'pending'" size="16" class="choice-header-icon">mdi-help-circle-outline</v-icon>
      <v-icon v-else size="16" class="choice-header-icon">mdi-check-circle</v-icon>
      <div class="choice-header-text">
        <div v-if="part.title" class="choice-title">{{ part.title }}</div>
        <div class="choice-prompt">{{ part.prompt }}</div>
      </div>
    </div>
    <div v-else class="choice-header choice-header--ignored">
      <v-icon size="16" class="choice-header-icon">mdi-eye-off-outline</v-icon>
      <span class="choice-ignored-label">{{ tm("interactiveChoice.ignored") }}</span>
      <span v-if="part.prompt" class="choice-prompt choice-prompt--muted">{{ part.prompt }}</span>
    </div>

    <!-- Pending: 选项按钮 + 自由输入 -->
    <template v-if="state === 'pending'">
      <div class="choice-options">
        <button
          v-for="opt in part.options"
          :key="opt.id"
          type="button"
          class="choice-option-button"
          :aria-label="ariaLabelForOption(opt)"
          @click="onOptionClick(opt)"
        >
          <span class="choice-option-label">{{ opt.label }}</span>
          <span v-if="opt.description" class="choice-option-description">
            {{ opt.description }}
          </span>
        </button>
      </div>
      <div class="choice-input-row">
        <textarea
          v-model="freeText"
          class="choice-input"
          :placeholder="inputPlaceholderResolved"
          rows="2"
          @keydown.enter.exact.prevent="onInputSubmit"
        />
        <v-btn
          class="choice-submit-button"
          color="primary"
          variant="tonal"
          size="small"
          :disabled="!freeText.trim()"
          @click="onInputSubmit"
        >
          {{ tm("interactiveChoice.submit") }}
        </v-btn>
      </div>
    </template>

    <!-- 已选择(已提交且来源是 option) -->
    <template v-else-if="state === 'submitted_via_option'">
      <div class="choice-result">
        <span class="choice-result-label">{{ tm("interactiveChoice.alreadyChosen") }}:</span>
        <span class="choice-result-value">{{ submittedLabel }}</span>
      </div>
    </template>

    <!-- 已输入(已提交且来源是 textarea) -->
    <template v-else-if="state === 'submitted_via_input'">
      <div class="choice-result">
        <span class="choice-result-label">{{ tm("interactiveChoice.alreadyInput") }}:</span>
        <span class="choice-result-value">{{ submittedLabel }}</span>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import { useModuleI18n } from "@/i18n/composables";
import {
  getOptionSubmitText,
  type InteractiveChoicePart,
  type InteractiveChoiceOption,
} from "@/composables/parseInteractiveChoice";

const props = defineProps<{
  part: InteractiveChoicePart;
  isDark?: boolean;
  isIgnored?: boolean;
}>();

const emit = defineEmits<{
  submit: [text: string];
}>();

const { tm } = useModuleI18n("features/chat");

// ── 内部状态 ─────────────────────────────────────────────────
const submittedValue = ref<string | null>(null);
const submittedKind = ref<"option" | "input" | null>(null);
const freeText = ref("");

// ── 派生状态机 ───────────────────────────────────────────────
type State = "pending" | "submitted_via_option" | "submitted_via_input" | "ignored";

const state = computed<State>(() => {
  if (props.isIgnored && submittedValue.value === null) return "ignored";
  if (submittedValue.value === null) return "pending";
  return submittedKind.value === "option" ? "submitted_via_option" : "submitted_via_input";
});

const submittedLabel = computed(() => {
  if (submittedValue.value === null) return "";
  if (submittedKind.value === "option") {
    const opt = props.part.options.find((o) => o.id === submittedOptionId.value);
    if (opt) return getOptionSubmitText(opt);
    return submittedValue.value;
  }
  return submittedValue.value;
});

const submittedOptionId = ref<string | null>(null);

const inputPlaceholderResolved = computed(
  () => props.part.input_placeholder || tm("interactiveChoice.defaultPlaceholder"),
);

function onOptionClick(opt: InteractiveChoiceOption) {
  if (state.value !== "pending") return;
  submittedOptionId.value = opt.id;
  submittedValue.value = getOptionSubmitText(opt);
  submittedKind.value = "option";
  emit("submit", submittedValue.value);
}

function onInputSubmit() {
  const text = freeText.value.trim();
  if (!text || state.value !== "pending") return;
  submittedValue.value = text;
  submittedKind.value = "input";
  emit("submit", text);
}

function ariaLabelForOption(opt: InteractiveChoiceOption): string {
  return opt.description ? `${opt.label} — ${opt.description}` : opt.label;
}
</script>

<style scoped>
.interactive-choice-box {
  margin: 8px 0;
  padding: 12px 14px;
  border-radius: 10px;
  background: rgba(var(--v-theme-primary), 0.04);
  border: 1px solid rgba(var(--v-theme-primary), 0.18);
  max-width: min(560px, 100%);
}

.interactive-choice-box.is-submitted,
.interactive-choice-box.is-ignored {
  opacity: 0.6;
  background: transparent;
  border-color: rgba(var(--v-theme-on-surface), 0.12);
}

.interactive-choice-box.is-dark {
  background: rgba(var(--v-theme-primary), 0.08);
  border-color: rgba(var(--v-theme-primary), 0.28);
}

.choice-header {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-bottom: 10px;
  color: rgb(var(--v-theme-on-surface));
}

.choice-header-icon {
  margin-top: 2px;
  color: rgb(var(--v-theme-primary));
  flex-shrink: 0;
}

.choice-header-text {
  min-width: 0;
  flex: 1;
}

.choice-title {
  font-size: 13px;
  font-weight: 600;
  line-height: 1.3;
  margin-bottom: 2px;
}

.choice-prompt {
  font-size: 14px;
  line-height: 1.45;
  word-break: break-word;
}

.choice-prompt--muted {
  font-size: 12px;
  opacity: 0.7;
}

.choice-header--ignored {
  color: rgba(var(--v-theme-on-surface), 0.6);
}

.choice-ignored-label {
  font-size: 13px;
  font-weight: 600;
  margin-right: 6px;
}

.choice-options {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 12px;
}

.choice-option-button {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  padding: 9px 12px;
  border: 1px solid rgba(var(--v-theme-primary), 0.32);
  border-radius: 8px;
  background: rgb(var(--v-theme-surface));
  color: rgb(var(--v-theme-on-surface));
  cursor: pointer;
  text-align: left;
  font: inherit;
  transition: background 0.12s ease, border-color 0.12s ease;
}

.choice-option-button:hover {
  background: rgba(var(--v-theme-primary), 0.08);
  border-color: rgb(var(--v-theme-primary));
}

.choice-option-label {
  font-size: 14px;
  font-weight: 500;
  line-height: 1.35;
}

.choice-option-description {
  font-size: 12px;
  line-height: 1.4;
  opacity: 0.7;
  white-space: pre-wrap;
}

.choice-input-row {
  display: flex;
  gap: 8px;
  align-items: flex-end;
}

.choice-input {
  flex: 1;
  min-height: 0;
  padding: 8px 10px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.18);
  border-radius: 8px;
  background: rgb(var(--v-theme-surface));
  color: rgb(var(--v-theme-on-surface));
  font: inherit;
  font-size: 13px;
  line-height: 1.4;
  resize: vertical;
  outline: none;
}

.choice-input:focus {
  border-color: rgb(var(--v-theme-primary));
}

.choice-submit-button {
  flex-shrink: 0;
  min-height: 36px;
  padding: 0 14px;
}

.choice-result {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
}

.choice-result-label {
  color: rgba(var(--v-theme-on-surface), 0.6);
  font-weight: 500;
}

.choice-result-value {
  color: rgb(var(--v-theme-on-surface));
  font-weight: 500;
  word-break: break-word;
}

.is-ignored .choice-option-button,
.is-submitted .choice-option-button {
  pointer-events: none;
  opacity: 0.6;
}
</style>