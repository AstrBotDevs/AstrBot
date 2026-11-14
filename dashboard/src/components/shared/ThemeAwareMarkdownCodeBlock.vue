<template>
  <CodeBlockNode
    v-bind="forwardedBindings"
    :clipboard-writer="writeCodeToClipboard"
    @copy="emit('copy', $event)"
  >
    <template
      v-for="(_, slotName) in $slots"
      #[slotName]="slotProps"
    >
      <slot :name="slotName" v-bind="slotProps || {}" />
    </template>
  </CodeBlockNode>
</template>

<script setup lang="ts">
import { computed, inject, type Ref, useAttrs } from "vue";
import { CodeBlockNode, type CodeBlockNodeProps } from "markstream-vue";
import { copyToClipboard } from "@/utils/clipboard";

defineOptions({
  inheritAttrs: false,
});

type MarkdownCodeBlockEmits = {
  copy: [payload: string];
};

const props = defineProps<{
  node: CodeBlockNodeProps["node"];
  isDark?: boolean;
  codeBlockOptions?: CodeBlockNodeProps["codeBlockOptions"];
}>();

const emit = defineEmits<MarkdownCodeBlockEmits>();

async function writeCodeToClipboard(code: string) {
  if (!(await copyToClipboard(code))) {
    throw new Error("Failed to copy code to the clipboard");
  }
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
  codeBlockOptions: {
    fontSize: 14,
    overflow: "scroll",
    diffStyle: "unified",
    disableLineNumbers: !props.node.diff,
    ...props.codeBlockOptions,
  } satisfies CodeBlockNodeProps["codeBlockOptions"],
}));
</script>
