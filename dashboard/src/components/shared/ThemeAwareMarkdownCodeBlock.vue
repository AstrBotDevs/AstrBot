<template>
  <MarkdownCodeBlockNode
    :key="themeRenderKey"
    v-bind="forwardedBindings"
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
import { computed, inject, type Ref } from "vue";
import { MarkdownCodeBlockNode } from "markstream-vue";
import { useAttrs } from "vue";

defineOptions({
  inheritAttrs: false,
});

const props = defineProps<{
  node: Record<string, unknown>;
  isDark?: boolean;
}>();

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
