<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useModuleI18n } from "@/i18n/composables";

const props = defineProps({
  text: { type: String, default: "" },
  tag: { type: String, default: "div" },
  lines: { type: Number, default: 4 },
});
const { tm } = useModuleI18n("features/trace");
const content = ref(null);
const expanded = ref(false);
const overflowing = ref(false);
let observer;

function measure() {
  if (!content.value) return;
  const lineHeight = Number.parseFloat(getComputedStyle(content.value).lineHeight);
  overflowing.value = content.value.scrollHeight > Math.ceil(lineHeight * props.lines) + 1;
  if (!overflowing.value) expanded.value = false;
}

onMounted(() => {
  measure();
  observer = new ResizeObserver(measure);
  observer.observe(content.value);
});
watch(() => [props.text, props.lines], async () => {
  await nextTick();
  measure();
});
onBeforeUnmount(() => observer?.disconnect());
</script>

<template>
  <div class="trace-message-preview">
    <component :is="tag" ref="content" class="trace-message-text" :class="{ 'is-collapsed': !expanded }" :style="{ '-webkit-line-clamp': lines }">{{ text }}</component>
    <button v-if="overflowing" type="button" class="trace-message-toggle" :aria-expanded="expanded" @click="expanded = !expanded">{{ tm(expanded ? 'messagePreview.collapse' : 'messagePreview.expand') }}</button>
  </div>
</template>

<style scoped>
.trace-message-preview { min-width: 0; }
.trace-message-text { font: inherit; line-height: 1.5; margin: 0; overflow-wrap: anywhere; white-space: pre-wrap; }
.trace-message-text.is-collapsed { display: -webkit-box; -webkit-box-orient: vertical; overflow: hidden; }
.trace-message-toggle { background: transparent; border: 0; border-radius: 4px; color: rgb(var(--v-theme-primary)); cursor: pointer; font-size: 11px; font-weight: 400; margin-top: 4px; min-height: 28px; padding: 2px 4px; }
.trace-message-toggle:hover { background: rgba(var(--v-theme-primary), 0.06); }
.trace-message-toggle:focus-visible { outline: 2px solid rgb(var(--v-theme-primary)); outline-offset: 2px; }
@media (pointer: coarse) { .trace-message-toggle { min-height: 44px; } }
</style>
