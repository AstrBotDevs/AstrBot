<template>
  <MarkdownCodeBlockNode
    :key="themeRenderKey"
    v-bind="forwardedBindings"
    @copy="handleCopy"
  >
    <template
      v-for="(_, slotName) in $slots"
      #[slotName]="slotProps"
    >
      <slot :name="slotName" v-bind="slotProps || {}" />
    </template>
  </MarkdownCodeBlockNode>
</template>

<script setup lang="ts">
import { computed, inject, type Ref, useAttrs } from "vue";
import { MarkdownCodeBlockNode } from "markstream-vue";
import { copyToClipboard } from "@/utils/clipboard";

defineOptions({
  inheritAttrs: false,
});

type MarkdownCodeBlockEmits = {
  copy: [payload: string];
};

const props = defineProps<{
  node: Record<string, unknown>;
  isDark?: boolean;
}>();

const emit = defineEmits<MarkdownCodeBlockEmits>();

const shouldUseClipboardFallback =
  typeof window !== "undefined" &&
  (!window.isSecureContext ||
    typeof navigator === "undefined" ||
    !navigator.clipboard?.writeText);

function handleCopy(payload: MarkdownCodeBlockEmits["copy"][0]) {
  if (typeof payload !== "string") return;

  if (shouldUseClipboardFallback) {
    void copyToClipboard(payload);
  }
  emit("copy", payload);
}

const injectedIsDark = inject<Ref<boolean> | boolean>("isDark");
const effectiveIsDark = computed(
  () => props.isDark ?? (injectedIsDark instanceof Object && "value" in injectedIsDark ? injectedIsDark.value : injectedIsDark) ?? false,
);

const attrs = useAttrs();
const forwardedBindings = computed(() => ({
  ...attrs,
  ...props,
  isDark: effectiveIsDark.value,
}));
const themeRenderKey = computed(() => (effectiveIsDark.value ? "dark" : "light"));
</script>
