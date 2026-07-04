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
      'is-submitted':
        state === 'submitted_via_option' || state === 'submitted_via_input',
      'is-ignored': state === 'ignored',
      'is-dark': isDark,
    }"
    :aria-live="state === 'ignored' ? 'polite' : undefined"
  >
    <!-- Header: title + prompt -->
    <div v-if="state !== 'ignored'" class="choice-header">
      <v-icon v-if="state === 'pending'" size="16" class="choice-header-icon"
        >mdi-help-circle-outline</v-icon
      >
      <v-icon v-else size="16" class="choice-header-icon"
        >mdi-check-circle</v-icon
      >
      <div class="choice-header-text">
        <div v-if="part.title" class="choice-title">{{ part.title }}</div>
        <div class="choice-prompt">{{ part.prompt }}</div>
      </div>
    </div>
    <div v-else class="choice-header choice-header--ignored">
      <v-icon size="16" class="choice-header-icon">mdi-eye-off-outline</v-icon>
      <span class="choice-ignored-label">{{
        tm("interactiveChoice.ignored")
      }}</span>
      <span v-if="part.prompt" class="choice-prompt choice-prompt--muted">{{
        part.prompt
      }}</span>
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
        <span class="choice-result-label"
          >{{ tm("interactiveChoice.alreadyChosen") }}:</span
        >
        <span class="choice-result-value">{{ submittedLabel }}</span>
      </div>
    </template>

    <!-- 已输入(已提交且来源是 textarea) -->
    <template v-else-if="state === 'submitted_via_input'">
      <div class="choice-result">
        <span class="choice-result-label"
          >{{ tm("interactiveChoice.alreadyInput") }}:</span
        >
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
import { useInteractiveChoiceStore } from "@/stores/interactiveChoice";

const props = defineProps<{
  part: InteractiveChoicePart;
  /**
   * UMO this choice belongs to. Required (Bug Y1 fix) — without it
   * the store cannot scope `markSubmitted` / `getSubmissionState` to
   * the right session, which would leak submission intents across
   * sessions.
   */
  umo: string;
  isDark?: boolean;
  isIgnored?: boolean;
}>();

// v1.0 提交协议:emit (requestId, payload),由 ChatMessageList 冒泡到 Chat.vue
// 处理实际发送。payload.choice_id 为 "__free_text__" 表示自由文本提交。
const emit = defineEmits<{
  submit: [
    requestId: string,
    payload: { choice_id: string; free_text: string },
  ];
}>();

const { tm } = useModuleI18n("features/chat");

// ── 状态来源:Pinia store(按 request_id 隔离) ──────────────────────
//
// Bug 1 修复:之前 submittedValue / submittedKind / submittedOptionId 是
// 局部 ref,父组件 v-for 在 bot message 推入新 part 时可能重新挂载本组件,
// 局部 ref 全部丢失,'已选择' 退回 '待选择'。把状态搬到 store 后,即便
// 整个 InteractiveChoiceBox 被重建,也能从 store 读回用户的提交意图。
const interactiveChoiceStore = useInteractiveChoiceStore();

// Reactively reads the submission state for this choice's request_id.
// Bug Y1 fix: scope reads by the supplied UMO so a submission
// recorded under session B cannot surface here.
const submissionState = computed(() =>
  interactiveChoiceStore.getSubmissionState(props.umo, props.part.request_id),
);

// 自由文本输入框的临时输入——这是 UI 局部状态,不需要全局共享,保留 ref。
const freeText = ref("");

// ── 派生状态机 ───────────────────────────────────────────────
type State =
  | "pending"
  | "submitted_via_option"
  | "submitted_via_input"
  | "ignored";

const state = computed<State>(() => {
  // 已被后续 user message 忽略的 bot 消息上的 box,只要用户没提交过,显示 ignored
  if (props.isIgnored && !submissionState.value) return "ignored";
  if (!submissionState.value) return "pending";
  return submissionState.value.kind === "option"
    ? "submitted_via_option"
    : "submitted_via_input";
});

const submittedLabel = computed(() => {
  const sub = submissionState.value;
  if (!sub) return "";
  if (sub.kind === "option") {
    const opt = props.part.options.find((o) => o.id === sub.optionId);
    if (opt) return getOptionSubmitText(opt);
    // optionId 找不到对应 label 时,回退到 freeText(若有)或空串。
    return sub.freeText ?? "";
  }
  return sub.freeText ?? "";
});

const inputPlaceholderResolved = computed(
  () =>
    props.part.input_placeholder || tm("interactiveChoice.defaultPlaceholder"),
);

function onOptionClick(opt: InteractiveChoiceOption) {
  // eslint-disable-next-line no-console
  console.log("[InteractiveChoiceBox] onOptionClick", {
    requestId: props.part.request_id,
    optionId: opt.id,
    state: state.value,
    isIgnored: props.isIgnored,
  });
  if (state.value !== "pending") return;
  // 先写 store,再 emit——保证父组件拿到的 requestId 与本次选项匹配,
  // 也保证即便 emit 之后父组件立刻触发重渲染,store 状态已就位。
  // Bug Y1 fix: write to this UMO's bucket only.
  interactiveChoiceStore.markSubmitted(
    props.umo,
    props.part.request_id,
    "option",
    {
      optionId: opt.id,
    },
  );
  emit("submit", props.part.request_id, { choice_id: opt.id, free_text: "" });
}

function onInputSubmit() {
  const text = freeText.value.trim();
  if (!text || state.value !== "pending") return;
  // 自由文本提交:choice_id 用哨兵值 "__free_text__" 标识,真实文本放在 free_text
  // Bug Y1 fix: write to this UMO's bucket only.
  interactiveChoiceStore.markSubmitted(
    props.umo,
    props.part.request_id,
    "input",
    {
      freeText: text,
    },
  );
  emit("submit", props.part.request_id, {
    choice_id: "__free_text__",
    free_text: text,
  });
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
  transition:
    background 0.12s ease,
    border-color 0.12s ease;
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
