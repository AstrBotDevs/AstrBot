<!--
  Author: elecvoid243
  Date: 2026-06-28
  Spec: docs/superpowers/specs/2026-06-28-dynamic-choice-box-rendering-design.md §4

  InteractiveChoiceBox: 动态渲染 LLM ask_user_choice 工具输出的选项框。
  4 状态机(pending / submitted_via_option / submitted_via_input / ignored) +
  非 pending 态可折叠展开回看选项 + a11y。
-->
<template>
  <div
    class="interactive-choice-box"
    :class="{
      'is-pending': state === 'pending',
      'is-submitted': state === 'submitted_via_option' || state === 'submitted_via_input',
      'is-ignored': state === 'ignored',
      'is-dark': isDark,
      'is-expanded': isExpanded,
    }"
    :aria-live="state === 'ignored' ? 'polite' : undefined"
  >
    <!-- Header: 标题/问题/概要 + (非 pending)折叠切换 -->
    <div
      class="choice-header"
      :class="{ 'choice-header--clickable': state !== 'pending' }"
      :role="state !== 'pending' ? 'button' : undefined"
      :tabindex="state !== 'pending' ? 0 : undefined"
      :aria-expanded="state !== 'pending' ? isExpanded : undefined"
      :aria-label="state !== 'pending' ? (isExpanded ? tm('interactiveChoice.collapseDetails') : tm('interactiveChoice.expandDetails')) : undefined"
      @click="state !== 'pending' && toggleExpand()"
      @keydown.enter.exact.prevent="state !== 'pending' && toggleExpand()"
      @keydown.space.exact.prevent="state !== 'pending' && toggleExpand()"
    >
      <!-- Pending: 帮助图标 -->
      <v-icon v-if="state === 'pending'" size="16" class="choice-header-icon">mdi-help-circle-outline</v-icon>
      <v-icon v-else-if="state === 'ignored'" size="16" class="choice-header-icon">mdi-eye-off-outline</v-icon>
      <!-- 已选/已输入态:✓ 绿勾 -->
      <v-icon v-else size="16" class="choice-header-icon">mdi-check-circle</v-icon>

      <div class="choice-header-text">
        <div v-if="part.title && state !== 'ignored'" class="choice-title">{{ part.title }}</div>

        <!-- Pending: 显示完整 prompt -->
        <div v-if="state === 'pending'" class="choice-prompt">{{ part.prompt }}</div>

        <!-- 已选择:显示 label -->
        <div v-else-if="state === 'submitted_via_option'" class="choice-result">
          <span class="choice-result-label">{{ tm("interactiveChoice.alreadyChosen") }}:</span>
          <span class="choice-result-value">{{ submittedLabel }}</span>
        </div>

        <!-- 已输入:显示输入文本 -->
        <div v-else-if="state === 'submitted_via_input'" class="choice-result">
          <span class="choice-result-label">{{ tm("interactiveChoice.alreadyInput") }}:</span>
          <span class="choice-result-value">{{ submittedLabel }}</span>
        </div>

        <!-- 已忽略: "已忽略" + prompt(只读) -->
        <div v-else-if="state === 'ignored'" class="choice-ignored-body">
          <span class="choice-ignored-label">{{ tm("interactiveChoice.ignored") }}</span>
          <span v-if="part.prompt" class="choice-prompt choice-prompt--muted">{{ part.prompt }}</span>
        </div>
      </div>

      <!-- 折叠展开按钮(仅非 pending) -->
      <v-icon
        v-if="state !== 'pending'"
        size="18"
        class="choice-toggle-icon"
        aria-hidden="true"
      >{{ isExpanded ? 'mdi-chevron-up' : 'mdi-chevron-down' }}</v-icon>
    </div>

    <!-- Pending: 选项按钮 + 自由输入(默认展开,无需切换) -->
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
          <span class="choice-option-label-row">
            <span v-if="opt.id" class="choice-option-marker">{{ opt.id }}.</span>
            <span>{{ opt.label }}</span>
          </span>
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

    <!-- 非 pending + 展开:回看选项列表(高亮已选项,disabled 防误操作) -->
    <template v-else-if="isExpanded">
      <!-- 非 ignored 时,header 折叠时只显示概要,这里补上完整 prompt -->
      <div v-if="part.prompt && state !== 'ignored'" class="choice-prompt choice-prompt--revisit">
        {{ part.prompt }}
      </div>
      <div class="choice-options">
        <div
          v-for="opt in part.options"
          :key="opt.id"
          class="choice-option-button choice-option-button--readonly"
          :class="{ 'is-selected-option': isOptionSelected(opt) }"
          :aria-label="ariaLabelForOption(opt)"
          role="group"
        >
          <span class="choice-option-label-row">
            <span v-if="opt.id" class="choice-option-marker">{{ opt.id }}.</span>
            <span>{{ opt.label }}</span>
          </span>
          <span v-if="opt.description" class="choice-option-description">
            {{ opt.description }}
          </span>
          <v-icon
            v-if="isOptionSelected(opt)"
            size="16"
            class="choice-option-check"
            aria-hidden="true"
          >mdi-check</v-icon>
        </div>
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

// 非 pending 状态下用户可折叠/展开回看选项。仅在 submitted/ignored 时生效。
const isExpanded = ref(false);

// 已选中的选项引用(展开时用于高亮显示)
const submittedOption = ref<InteractiveChoiceOption | null>(null);

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
    // 优先用 submittedOption(展开时高亮)
    if (submittedOption.value) return submittedOption.value.label;
    // 旧路径:通过 value 反查 label(向后兼容)
    const opt = props.part.options.find((o) => o.value === submittedValue.value);
    return opt?.label ?? submittedValue.value;
  }
  return submittedValue.value;
});

const inputPlaceholderResolved = computed(
  () => props.part.input_placeholder || tm("interactiveChoice.defaultPlaceholder"),
);

/**
 * 判断给定 option 是否就是用户已选择的(仅 submitted_via_option 态生效)。
 * - 通过 id 匹配(无论 plugin 老 schema 用 value 还是新 schema 用 id,id 都必填)
 * - submitted_via_input 态:用户没选 option,没选项应高亮
 * - ignored 态:没操作过,无 submittedOption
 */
function isOptionSelected(opt: InteractiveChoiceOption): boolean {
  if (state.value !== "submitted_via_option") return false;
  return submittedOption.value?.id === opt.id;
}

function onOptionClick(opt: InteractiveChoiceOption) {
  if (state.value !== "pending") return;
  const text = getOptionSubmitText(opt);
  submittedValue.value = text;
  submittedKind.value = "option";
  submittedOption.value = opt;  // 记下选项引用,用于展开高亮
  emit("submit", text);
}

function onInputSubmit() {
  const text = freeText.value.trim();
  if (!text || state.value !== "pending") return;
  submittedValue.value = text;
  submittedKind.value = "input";
  submittedOption.value = null;  // 输入框提交,不清空选项
  emit("submit", text);
}

/**
 * 折叠/展开切换。仅非 pending 态可调。
 * pending 时永远展开(用户必须能直接操作按钮 + 输入框)。
 */
function toggleExpand() {
  if (state.value === "pending") return;
  isExpanded.value = !isExpanded.value;
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
  border-color: rgba(var(--v-theme-on-surface), 0.18);
}

.interactive-choice-box.is-dark {
  /* 深色下用更高 alpha + 微弱外发光,让选项框从聊天背景中跳出 */
  background: rgba(var(--v-theme-primary), 0.12);
  border-color: rgba(var(--v-theme-primary), 0.55);
  box-shadow: 0 0 0 1px rgba(var(--v-theme-primary), 0.18);
}

/* 深色 + 已提交/已忽略:用 on-surface 中灰,避免上面 on-surface 0.18 在黑底上被吞掉 */
.interactive-choice-box.is-dark.is-submitted,
.interactive-choice-box.is-dark.is-ignored {
  border-color: rgba(var(--v-theme-on-surface), 0.32);
  box-shadow: none;
}

.choice-header {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-bottom: 10px;
  color: rgb(var(--v-theme-on-surface));
}

.choice-header--clickable {
  cursor: pointer;
  padding: 2px 4px;
  margin: -2px -4px 10px;
  border-radius: 6px;
  transition: background-color 0.12s ease;
}

.choice-header--clickable:hover {
  background-color: rgba(var(--v-theme-primary), 0.06);
}

.choice-header--clickable:focus-visible {
  outline: 2px solid rgba(var(--v-theme-primary), 0.5);
  outline-offset: 1px;
}

.choice-toggle-icon {
  margin-left: auto;
  margin-top: 2px;
  color: rgba(var(--v-theme-on-surface), 0.6);
  transition: transform 0.18s ease;
  flex-shrink: 0;
}

.is-expanded .choice-toggle-icon {
  transform: none;
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

.choice-option-label-row {
  display: inline-flex;
  align-items: baseline;
  gap: 4px;
  font-size: 14px;
  font-weight: 500;
  line-height: 1.35;
}

.choice-option-marker {
  font-size: 13px;
  font-weight: 600;
  color: rgba(var(--v-theme-primary), 0.75);
  letter-spacing: 0.02em;
  flex-shrink: 0;
}

.interactive-choice-box.is-dark .choice-option-marker {
  color: rgba(var(--v-theme-primary), 0.95);
}

.choice-option-description {
  font-size: 12px;
  line-height: 1.4;
  opacity: 0.7;
  white-space: pre-wrap;
}

/* 已选/已忽略态展开后看到的选项(只读,不可点击) */
.choice-option-button--readonly {
  cursor: default;
  pointer-events: auto;  /* 仍可选中文字 copy */
  flex-direction: row;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
}

.choice-option-button--readonly .choice-option-description {
  flex: 1;
  min-width: 0;
}

.choice-option-button--readonly.is-selected-option {
  border-color: rgb(var(--v-theme-primary));
  background-color: rgba(var(--v-theme-primary), 0.12);
  font-weight: 600;
}

.interactive-choice-box.is-dark
  .choice-option-button--readonly.is-selected-option {
  background-color: rgba(var(--v-theme-primary), 0.22);
}

.choice-option-check {
  flex-shrink: 0;
  color: rgb(var(--v-theme-primary));
  margin-left: 4px;
}

/* 展开时顶部补的 prompt(跟 collapsed 时的概要区分) */
.choice-prompt--revisit {
  margin: 0 0 10px;
  padding: 6px 8px;
  background: rgba(var(--v-theme-primary), 0.06);
  border-radius: 6px;
  font-size: 13px;
  color: rgba(var(--v-theme-on-surface), 0.85);
}

.interactive-choice-box.is-dark .choice-prompt--revisit {
  background: rgba(var(--v-theme-primary), 0.14);
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

.is-pending .choice-toggle-icon {
  display: none;
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