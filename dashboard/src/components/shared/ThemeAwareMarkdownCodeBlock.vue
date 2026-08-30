<template>
  <CodeBlockNode
    :key="themeRenderKey"
    v-bind="forwardedBindings"
    @copy="handleCopy"
  >
    <template v-for="(_, slotName) in $slots" #[slotName]="slotProps">
      <slot :name="slotName" v-bind="slotProps || {}" />
    </template>
  </CodeBlockNode>
</template>

<script setup lang="ts">
import { computed, inject, type Ref, useAttrs } from 'vue';
import { CodeBlockNode, type CodeBlockNodeProps } from 'markstream-vue';
import { copyToClipboard } from '@/utils/clipboard';
import { isFenceLanguageSettled } from '@/utils/shikiLimitedBundle';

defineOptions({
  inheritAttrs: false,
});

const props = defineProps<{
  node: CodeBlockNodeProps['node'];
  isDark?: boolean;
}>();

const emit = defineEmits<{
  copy: [payload: string];
}>();

function handleCopy(payload: string) {
  if (typeof payload !== 'string') return;

  if (
    typeof window === 'undefined' ||
    !window.isSecureContext ||
    !navigator.clipboard?.writeText
  ) {
    void copyToClipboard(payload);
  }
  emit('copy', payload);
}

const injectedIsDark = inject<Ref<boolean> | boolean>('isDark');
const effectiveIsDark = computed(
  () =>
    props.isDark ??
    (injectedIsDark instanceof Object && 'value' in injectedIsDark
      ? injectedIsDark.value
      : injectedIsDark) ??
    false,
);

const attrs = useAttrs();
const settledNode = computed(() => {
  const node = props.node;
  if (!node || isFenceLanguageSettled(node)) return node;
  return { ...node, language: 'text' };
});
const forwardedBindings = computed(() => ({
  ...attrs,
  ...props,
  node: settledNode.value,
  isDark: effectiveIsDark.value,
}));
const themeRenderKey = computed(() =>
  effectiveIsDark.value ? 'dark' : 'light',
);
</script>
