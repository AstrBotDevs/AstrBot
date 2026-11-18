<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from "vue";

const props = defineProps({ lang: { type: String, default: "zh" } });
const copy = computed(() =>
  props.lang === "en"
    ? {
        label: "Interactive example",
        replay: "Replay",
        question: "Show me my reading list.",
        thinking: "Opening your reading list…",
        reply: "Here is your reading list. Mark a book as read to update it.",
        title: "Reading list",
        read: "read",
        mark: "Mark as read",
        undo: "Mark as unread",
        titles: [
          "The Design of Everyday Things",
          "Invisible Cities",
          "Siddhartha",
        ],
        authors: ["Don Norman", "Italo Calvino", "Hermann Hesse"],
        steps: ["Ask in chat", "Return a view", "Update in place"],
        hint: "Try the checkboxes. This preview runs locally; it does not send messages or call a model.",
        updated: "Reading status updated",
        idle: "Your turn — mark a book as read.",
      }
    : {
        label: "交互示例",
        replay: "重新播放",
        question: "给我看看阅读清单。",
        thinking: "正在打开阅读清单…",
        reply: "这是你的阅读清单。读完一本，可以直接在这里标记。",
        title: "阅读清单",
        read: "已读",
        mark: "标记已读",
        undo: "标记待读",
        titles: ["设计心理学", "看不见的城市", "悉达多"],
        authors: ["唐纳德·诺曼", "伊塔洛·卡尔维诺", "赫尔曼·黑塞"],
        steps: ["在对话中提出请求", "返回交互组件", "就地更新状态"],
        hint: "点击勾选即可体验。此预览仅在本页运行，不会发送消息或调用模型。",
        updated: "阅读状态已更新",
        idle: "试一试，标记一本已读的书。",
      },
);
const root = ref(null);
const phase = ref(2);
const read = ref([false, false, true]);
const count = computed(() => read.value.filter(Boolean).length);
let timers = [];
let observer;

function replay() {
  timers.forEach(clearTimeout);
  read.value = [false, false, true];
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    phase.value = 2;
    return;
  }
  phase.value = 0;
  timers = [
    setTimeout(() => {
      phase.value = 1;
    }, 450),
    setTimeout(() => {
      phase.value = 2;
    }, 1200),
    setTimeout(() => {
      read.value[0] = true;
      phase.value = 3;
    }, 2800),
  ];
}

function toggle(index) {
  timers.forEach(clearTimeout);
  read.value[index] = !read.value[index];
  phase.value = 3;
}

onMounted(() => {
  observer = new IntersectionObserver(
    ([entry]) => {
      if (entry.isIntersecting) {
        replay();
        observer.disconnect();
      }
    },
    { threshold: 0.4 },
  );
  observer.observe(root.value);
});
onBeforeUnmount(() => {
  observer?.disconnect();
  timers.forEach(clearTimeout);
});
</script>

<template>
  <figure ref="root" class="reading-demo" :aria-label="copy.label">
    <div class="demo-toolbar">
      <span><i aria-hidden="true"></i>{{ copy.label }}</span>
      <button type="button" @click="replay">
        <span aria-hidden="true">↻</span> {{ copy.replay }}
      </button>
    </div>
    <div class="conversation">
      <div class="user-message">{{ copy.question }}</div>
      <div class="bot-message">
        <svg class="bot-mark" viewBox="0 0 24 24" aria-hidden="true">
          <path
            d="M12 1C10 7 7 10 1 12c6 2 9 5 11 11 2-6 5-9 11-11C17 10 14 7 12 1Z"
            fill="currentColor"
          />
        </svg>
        <div class="bot-content">
          <div
            class="thinking"
            v-if="phase < 2"
            :class="{ waiting: phase === 0 }"
          >
            {{ copy.thinking }}<span>···</span>
          </div>
          <div v-else class="result">
            <p class="reply">{{ copy.reply }}</p>
            <div class="list-heading">
              <strong>{{ copy.title }}</strong>
              <span
                ><b>{{ count }} / 3</b> {{ copy.read }}</span
              >
            </div>
            <ul class="books">
              <li v-for="(title, index) in copy.titles" :key="index">
                <span class="number" aria-hidden="true">0{{ index + 1 }}</span>
                <span
                  class="spine"
                  :class="`spine-${index}`"
                  aria-hidden="true"
                ></span>
                <div class="book-copy">
                  <strong>{{ title }}</strong
                  ><span>{{ copy.authors[index] }}</span>
                </div>
                <button
                  type="button"
                  class="read-toggle"
                  :aria-pressed="read[index]"
                  :aria-label="`${
                    read[index] ? copy.undo : copy.mark
                  }: ${title}`"
                  @click="toggle(index)"
                >
                  <span class="toggle-label">{{
                    read[index] ? copy.read : copy.mark
                  }}</span>
                  <span class="check" aria-hidden="true"
                    ><svg v-if="read[index]" viewBox="0 0 16 16">
                      <path d="m3 8 3 3 7-7" /></svg
                  ></span>
                </button>
              </li>
            </ul>
            <div class="status" aria-live="polite">
              {{ phase === 3 ? `✓ ${copy.updated}` : copy.idle }}
            </div>
          </div>
        </div>
      </div>
    </div>
    <ol class="steps" aria-label="Flow">
      <li
        v-for="(step, index) in copy.steps"
        :key="index"
        :class="{ current: Math.max(0, phase - 1) === index }"
      >
        <span>{{ index + 1 }}</span
        >{{ step }}
      </li>
    </ol>
    <figcaption>{{ copy.hint }}</figcaption>
  </figure>
</template>

<style scoped>
.reading-demo {
  --demo-accent: var(--vp-c-brand-1);
  margin: 24px 0 32px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 16px;
  overflow: hidden;
  background: var(--vp-c-bg);
  color: var(--vp-c-text-1);
  font-size: 14px;
}
.demo-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 20px;
  background: var(--vp-c-bg-soft);
  font-size: 12px;
  color: var(--vp-c-text-2);
}
.demo-toolbar > span {
  display: flex;
  align-items: center;
  gap: 8px;
}
.demo-toolbar i {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--demo-accent);
}
.reading-demo button {
  font: inherit;
  cursor: pointer;
  border: 0;
  background: none;
  color: inherit;
}
.reading-demo button:focus-visible {
  outline: 2px solid var(--demo-accent);
  outline-offset: 4px;
  border-radius: 4px;
}
.demo-toolbar button {
  padding: 2px 4px;
}
.demo-toolbar button span {
  font-size: 17px;
  margin-right: 4px;
}
.conversation {
  padding: 28px 26px 16px;
  min-height: 410px;
}
.user-message {
  width: fit-content;
  max-width: 85%;
  margin: 0 0 24px auto;
  padding: 10px 16px;
  background: var(--vp-c-default-soft);
  border-radius: 16px 16px 4px 16px;
  line-height: 1.6;
}
.bot-message {
  display: flex;
  gap: 14px;
  align-items: flex-start;
}
.bot-mark {
  width: 22px;
  height: 22px;
  flex: none;
  color: var(--demo-accent);
  margin-top: 4px;
}
.bot-content {
  flex: 1;
  min-width: 0;
}
.reply {
  margin: 0 0 24px;
  line-height: 1.7;
  font-size: 13px;
  color: var(--vp-c-text-2);
}
.thinking {
  color: var(--vp-c-text-2);
  font-size: 13px;
  transition: opacity 0.2s;
}
.thinking.waiting {
  opacity: 0;
}
.thinking span {
  margin-left: 8px;
}
.result {
  animation: arrive 0.35s ease-out;
}
.list-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}
.list-heading > strong {
  font-size: 20px;
  letter-spacing: -0.5px;
}
.list-heading > span {
  font-size: 11px;
  color: var(--vp-c-text-2);
}
.list-heading b {
  font-weight: 500;
  color: var(--demo-accent);
}
.books {
  padding: 0;
  margin: 0;
  list-style: none;
  border-top: 1px solid var(--vp-c-divider);
}
.books li {
  margin: 0;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 15px 0;
  border-bottom: 1px solid var(--vp-c-divider);
}
.number {
  font-size: 11px;
  color: var(--vp-c-text-2);
  font-variant-numeric: tabular-nums;
}
.spine {
  height: 32px;
  width: 3px;
  flex: none;
  background: #bda185;
}
.spine-1 {
  background: #8c9e9e;
}
.spine-2 {
  background: #9ba58d;
}
.book-copy {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
  min-width: 0;
}
.book-copy strong {
  font-family: "Songti SC", Georgia, serif;
  font-weight: 500;
  font-size: 16px;
  line-height: 1.5;
}
.book-copy > span {
  font-size: 11px;
  color: var(--vp-c-text-2);
}
.read-toggle {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 32px;
  flex: none;
}
.toggle-label {
  font-size: 11px;
  color: var(--vp-c-text-2);
}
.check {
  border: 1px solid var(--vp-c-divider);
  width: 20px;
  height: 20px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  transition:
    background 0.2s,
    border-color 0.2s;
}
.check svg {
  width: 14px;
  height: 14px;
  fill: none;
  stroke: var(--vp-c-bg);
  stroke-width: 1.8;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.read-toggle[aria-pressed="true"] .check {
  background: var(--demo-accent);
  border-color: var(--demo-accent);
}
.read-toggle:hover .check {
  border-color: var(--demo-accent);
}
.status {
  font-size: 11px;
  color: var(--vp-c-text-2);
  padding-top: 12px;
  min-height: 30px;
}
.steps {
  display: flex;
  gap: 16px;
  list-style: none;
  margin: 0;
  padding: 14px 20px;
  border-top: 1px solid var(--vp-c-divider);
  background: var(--vp-c-bg-soft);
}
.steps li {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  line-height: 1.5;
  color: var(--vp-c-text-2);
  margin: 0;
  flex: 1;
}
.steps li > span {
  display: grid;
  place-items: center;
  width: 17px;
  height: 17px;
  border: 1px solid var(--vp-c-divider);
  border-radius: 50%;
  flex: none;
  font-size: 10px;
}
.steps .current {
  color: var(--demo-accent);
}
.steps .current > span {
  border-color: var(--demo-accent);
}
figcaption {
  padding: 12px 20px;
  font-size: 11px;
  line-height: 1.7;
  color: var(--vp-c-text-2);
}
@keyframes arrive {
  from {
    opacity: 0;
    transform: translateY(5px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation: none !important;
    transition: none !important;
  }
}
@media (max-width: 520px) {
  .conversation {
    padding: 22px 16px 16px;
    min-height: 430px;
  }
  .bot-message {
    gap: 9px;
  }
  .bot-mark {
    width: 18px;
  }
  .toggle-label {
    display: none;
  }
  .steps {
    gap: 8px;
    padding: 12px;
  }
  .steps li {
    font-size: 10px;
    align-items: start;
  }
  .book-copy strong {
    font-size: 15px;
  }
  .books li {
    gap: 9px;
  }
}
</style>
