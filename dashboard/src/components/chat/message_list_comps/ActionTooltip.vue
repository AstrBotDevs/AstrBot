<template>
  <!-- Hover hint for a message action: a short name and what it does. -->
  <v-tooltip
    v-model="open"
    activator="parent"
    location="top"
    :open-delay="300"
    :max-width="240"
    content-class="action-tooltip"
  >
    <div class="action-tooltip-title">{{ title }}</div>
    <div v-if="description" class="action-tooltip-description">
      {{ description }}
    </div>
  </v-tooltip>
</template>

<script setup lang="ts">
import { getCurrentInstance, onBeforeUnmount, onMounted, ref } from "vue";

defineProps<{ title: string; description?: string }>();

// Vuetify opens a tooltip on focus of the activator itself only. Edit and
// regenerate wrap their (possibly disabled) button in a span so a disabled
// button still explains itself on hover, so also open on keyboard focus
// anywhere inside the activator.
const open = ref(false);
const instance = getCurrentInstance();
let activator: HTMLElement | null = null;
const onFocusIn = (event: FocusEvent) => {
  if ((event.target as HTMLElement).matches(":focus-visible")) open.value = true;
};
const onFocusOut = () => {
  open.value = false;
};
onMounted(() => {
  activator = (instance?.proxy?.$el as Node | null)?.parentElement ?? null;
  activator?.addEventListener("focusin", onFocusIn);
  activator?.addEventListener("focusout", onFocusOut);
});
onBeforeUnmount(() => {
  activator?.removeEventListener("focusin", onFocusIn);
  activator?.removeEventListener("focusout", onFocusOut);
});
</script>

<!-- Not scoped: the tooltip renders in an overlay outside this component.
     A solid dark card stays crisp in both themes (Vuetify's default is a
     translucent grey that looks washed out on dark backgrounds). The width cap
     is the max-width prop: Vuetify writes max-width inline, over any CSS. -->
<style>
.v-tooltip > .v-overlay__content.action-tooltip {
  padding: 6px 10px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 8px;
  background: #262626;
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.28);
  color: #fff;
  line-height: 1.4;
  opacity: 1;
}

.action-tooltip-title {
  font-size: 0.78rem;
  font-weight: 600;
}

.action-tooltip-description {
  margin-top: 1px;
  font-size: 0.72rem;
  color: rgba(255, 255, 255, 0.62);
}
</style>
