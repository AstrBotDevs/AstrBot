<!--
  Author: elecvoid243
  Date: 2026-06-28
  Spec: docs/superpowers/specs/2026-06-28-dynamic-choice-box-rendering-design.md §4
  v1.2 增量: docs/superpowers/specs/2026-07-19-server-driven-cancelled-state-design.md §4.4

  InteractiveChoiceBox: 动态渲染 LLM ask_user_choice 工具输出的选项框。
  5 状态机(pending / submitted_via_option / submitted_via_input / ignored / cancelled) + a11y。
  v1.2 新增 `cancelled` 状态,覆盖服务端超时与运行时取消两种场景。
-->
<template>
  <div
    class="interactive-choice-box"
    :class="{
      'is-pending': state === 'pending',
      'is-submitted':
        state === 'submitted_via_option' || state === 'submitted_via_input',
      'is-ignored': state === 'ignored',
      'is-cancelled': state === 'cancelled',
      'is-dark': isDark,
    }"
    :aria-live="
      state === 'ignored' || state === 'cancelled' ? 'polite' : undefined
    "
  >
    <!-- Header: title + prompt -->
    <div
      v-if="state !== 'ignored' && state !== 'cancelled'"
      class="choice-header"
    >
      <v-icon v-if="state === 'pending'" size="16" class="choice-header-icon"
        >mdi-help-circle-outline</v-icon
      >
      <v-icon v-else size="16" class="choice-header-icon"
        >mdi-check-circle</v-icon
      >
      <div class="choice-header-text">
        <div v-if="part.title" class="choice-title" :title="part.title">
          {{ part.title }}
        </div>
        <div class="choice-prompt" :title="part.prompt">{{ part.prompt }}</div>
      </div>
    </div>
    <div
      v-else-if="state === 'ignored'"
      class="choice-header choice-header--ignored"
    >
      <v-icon size="16" class="choice-header-icon">mdi-eye-off-outline</v-icon>
      <span class="choice-ignored-label">{{
        tm("interactiveChoice.ignored")
      }}</span>
      <span
        v-if="part.title"
        class="choice-title choice-title--ignored"
        :title="part.title"
        >{{ part.title }}</span
      >
      <span
        v-if="part.prompt"
        class="choice-prompt choice-prompt--muted"
        :title="part.prompt"
        >{{ part.prompt }}</span
      >
    </div>
    <!-- v1.2: cancelled header(server-driven terminal state).Mirrors the
         .choice-header--ignored template shape exactly so the CSS in Step 8
         can use consolidated selectors (.choice-header--ignored,
         .choice-header--cancelled) and the box looks visually consistent
         with the ignored state. The 即可消失 option buttons / input are
         rendered by the `v-if="state === 'pending'"` branch below,which
         already excludes cancelled because `state !== 'pending'`. -->
    <div
      v-else-if="state === 'cancelled'"
      class="choice-header choice-header--cancelled"
    >
      <v-icon size="16" class="choice-header-icon"
        >mdi-close-circle-outline</v-icon
      >
      <span class="choice-cancelled-label">{{
        tm("interactiveChoice.cancelled")
      }}</span>
      <span
        v-if="part.title"
        class="choice-title choice-title--cancelled"
        :title="part.title"
        >{{ part.title }}</span
      >
      <span
        v-if="part.prompt"
        class="choice-prompt choice-prompt--muted"
        :title="part.prompt"
        >{{ part.prompt }}</span
      >
    </div>

    <!-- Pending: prose 段(帮用户决策)+ 选项按钮 + 自由输入 -->
    <template v-if="state === 'pending'">
      <InteractiveChoiceProse
        v-if="part.extra_content"
        :content="part.extra_content"
        :is-dark="isDark"
        :uid="part.request_id"
      />
      <div class="choice-options">
        <button
          v-for="opt in part.options"
          :key="opt.id"
          type="button"
          class="choice-option-button"
          :aria-label="ariaLabelForOption(opt)"
          @click="onOptionClick(opt)"
        >
          <span class="choice-option-label" :title="opt.label">
            <span v-if="opt.id" class="choice-option-id">{{ opt.id }}.</span>
            {{ opt.label }}
          </span>
          <span
            v-if="opt.description"
            class="choice-option-description"
            :title="opt.description"
          >
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

    <!-- 非 pending:可折叠回看"prose + 原始选项",避免历史 prose 与选项信息丢失。
         默认折叠;展开后依次渲染 prose(若存在)与全部 options,并高亮当时选中的那一项。
         折叠触发条件:state 非 pending 且(prose 存在 或 options 非空)。 -->
    <div
      v-if="state !== 'pending' && (part.options.length || part.extra_content)"
      class="choice-options-collapse"
    >
      <button
        type="button"
        class="choice-collapse-toggle"
        :aria-expanded="optionsExpanded"
        @click="optionsExpanded = !optionsExpanded"
      >
        <v-icon size="14" class="choice-collapse-icon">{{
          optionsExpanded ? "mdi-chevron-down" : "mdi-chevron-right"
        }}</v-icon>
        <span>{{
          optionsExpanded
            ? tm("interactiveChoice.collapseDetails")
            : tm("interactiveChoice.expandDetails")
        }}</span>
        <span class="choice-collapse-count">({{ collapseItemCount }})</span>
      </button>
      <div v-if="optionsExpanded" class="choice-details">
        <InteractiveChoiceProse
          v-if="part.extra_content"
          :content="part.extra_content"
          :is-dark="isDark"
          :uid="part.request_id"
        />
        <div
          v-if="part.options.length"
          class="choice-options choice-options--readonly"
        >
          <div
            v-for="opt in part.options"
            :key="opt.id"
            class="choice-option-readonly"
            :class="{ 'is-selected': opt.id === selectedOptionId }"
          >
            <div class="choice-option-readonly-head">
              <v-icon
                v-if="opt.id === selectedOptionId"
                size="14"
                class="choice-option-check"
                >mdi-check</v-icon
              >
              <span class="choice-option-label" :title="opt.label">
                <span v-if="opt.id" class="choice-option-id"
                  >{{ opt.id }}.</span
                >
                {{ opt.label }}
              </span>
            </div>
            <span
              v-if="opt.description"
              class="choice-option-description"
              :title="opt.description"
            >
              {{ opt.description }}
            </span>
          </div>
        </div>
      </div>
    </div>
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
import InteractiveChoiceProse from "@/components/chat/message_list_comps/InteractiveChoiceProse.vue";

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

// v1.2: Reactively reads the server-cancelled flag for this
// choice's request_id, scoped by UMO. Driven by two independent
// paths (live SSE `interactive_choice_resolved {reason: "cancelled"}`
// from F3 and `reconcile(umo)` orphan detection from F2) so the
// box can flip to the non-interactive "已取消" state regardless of
// whether the resolved event arrived cleanly.
const cancelledState = computed(() =>
  interactiveChoiceStore.isCancelled(props.umo, props.part.request_id),
);

// 自由文本输入框的临时输入——这是 UI 局部状态,不需要全局共享,保留 ref。
const freeText = ref("");

// 非 pending 状态下"回看原始选项"折叠区的展开标志。历史信息默认折叠,
// 保持聊天流干净;这是纯 UI 局部状态,无需持久化到 store。
const optionsExpanded = ref(false);

// ── 派生状态机 ───────────────────────────────────────────────
type State =
  | "pending"
  | "submitted_via_option"
  | "submitted_via_input"
  | "ignored"
  | "cancelled"; // ── v1.2 新增

const state = computed<State>(() => {
  // 状态优先级(从高到低)——spec §5.1 强制约束:
  //   1. submissionState —— 用户已提交,UI 必须诚实显示"已选择 X"
  //   2. cancelledState  —— 后端推送/兜底检测到超时或取消
  //   3. props.isIgnored —— 后续 user message 已"走过"本 box
  //   4. pending         —— 默认
  //
  // 为什么 submission 必须排在 cancelled 之前:竞态保护。如果用户在
  // T=timeout−1 抢点提交,本地提交意图是诚实的(显示"已选择 X"),
  // 服务端 a moment later 发来 cancelled 事件 / 因网络故障 reconcile
  // 兜底检测到 backend list 里已无此 rid。如果 cancelled 排第一,UI
  // 会把用户已选的那一选项偷偷改成"已取消",那就是 UI 在说谎。
  if (submissionState.value) {
    return submissionState.value.kind === "option"
      ? "submitted_via_option"
      : "submitted_via_input";
  }
  if (cancelledState.value) return "cancelled";
  if (props.isIgnored) return "ignored";
  return "pending";
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

// 折叠区展开时,用于高亮"当时选中项"的选项 id。仅当提交来源是 option
// 时有值;自由文本提交或被忽略时为 null(无高亮)。
const selectedOptionId = computed<string | null>(() => {
  const sub = submissionState.value;
  return sub && sub.kind === "option" ? sub.optionId ?? null : null;
});

// 折叠区计数 = prose 段(prose 若存在计 1)+ 原始选项数。
// 当 prose 与 options 同时存在时,二者都进同一个折叠,共用同一个展开态,
// 因此计数要相加。空 part(或两者皆无)由模板 v-if 兜底,这里只算正数。
const collapseItemCount = computed<number>(() => {
  let count = 0;
  if (props.part.extra_content && props.part.extra_content.length > 0) {
    count += 1;
  }
  count += props.part.options.length;
  return count;
});

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
.interactive-choice-box.is-ignored,
.interactive-choice-box.is-cancelled {
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

.choice-header--ignored,
.choice-header--cancelled {
  color: rgba(var(--v-theme-on-surface), 0.6);
  /* 让长 title / prompt 能在 header 行内自然换行,不被压成单字符。
     v1.2 之前 ignored header 只渲染 label + prompt,内容短;补上
     title 渲染后(见模板),CJK 长 title 可能在 560px 容器里被
     flex 默认 shrink 挤扁,加 wrap 让浏览器自动换行。 */
  flex-wrap: wrap;
}

.choice-title--ignored,
.choice-title--cancelled {
  /* 与 pending/submitted 的 .choice-title 共享字号字重,这里只
     收敛 line-height 让行内 title 不与 label 基线打架。 */
  line-height: 1.3;
  word-break: break-word;
}

.choice-ignored-label,
.choice-cancelled-label {
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
.is-submitted .choice-option-button,
.is-cancelled .choice-option-button {
  pointer-events: none;
  opacity: 0.6;
}

/* ── 非 pending 状态:可折叠的原始选项回看区 ───────────────────── */
.choice-options-collapse {
  margin-top: 8px;
}

.choice-collapse-toggle {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 4px;
  margin-left: -4px;
  border: none;
  background: transparent;
  color: rgba(var(--v-theme-on-surface), 0.6);
  cursor: pointer;
  font: inherit;
  font-size: 12px;
  border-radius: 6px;
  transition: color 0.12s ease;
}

.choice-collapse-toggle:hover {
  color: rgb(var(--v-theme-primary));
}

.choice-collapse-icon {
  flex-shrink: 0;
}

.choice-collapse-count {
  opacity: 0.8;
}

.choice-options--readonly {
  margin-top: 6px;
  margin-bottom: 0;
}

/* 折叠展开区 .choice-details:同时容纳 prose 段与只读 options 时,
   prose 自身的 margin (6/0/10) 容易把上下撑开过大。收紧 prose 在
   折叠容器内的边距,让它紧贴在 toggle 按钮下、跟 options 挨得近一点。 */
.choice-details {
  margin-top: 6px;
}
.choice-details > .choice-prose {
  margin-top: 0;
}
.choice-details > .choice-options {
  /* prose → options 收尾,去掉 prose 底部 10px + options 顶部 6px 中的冗余 */
  margin-top: 6px;
}

.choice-option-readonly {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 7px 10px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  border-radius: 8px;
  background: rgba(var(--v-theme-on-surface), 0.02);
}

.choice-option-readonly.is-selected {
  border-color: rgba(var(--v-theme-primary), 0.5);
  background: rgba(var(--v-theme-primary), 0.08);
}

.choice-option-readonly-head {
  display: flex;
  align-items: center;
  gap: 4px;
}

.choice-option-check {
  color: rgb(var(--v-theme-primary));
  flex-shrink: 0;
}

/* 选项 id 前缀(通常是 A / B / C)——加粗、主题色,置于 label 最前 */
.choice-option-id {
  font-weight: 700;
  color: rgb(var(--v-theme-primary));
  margin-right: 2px;
}
</style>
