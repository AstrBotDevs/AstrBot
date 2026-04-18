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
import { computed } from "vue";
import { MarkdownCodeBlockNode } from "markstream-vue";
import { useAttrs } from "vue";

defineOptions({
  inheritAttrs: false,
});

const props = withDefaults(
  defineProps<{
    node: Record<string, unknown>;
    isDark?: boolean;
  }>(),
  {
    isDark: false,
  },
);

const attrs = useAttrs();
const forwardedBindings = computed(() => ({
  ...attrs,
  ...props,
}));
const themeRenderKey = computed(() => (props.isDark ? "dark" : "light"));
</script>
