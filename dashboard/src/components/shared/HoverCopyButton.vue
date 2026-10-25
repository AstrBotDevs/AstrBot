<template>
  <v-btn
    :icon="
      copied === null ? 'mdi-content-copy' : copied ? 'mdi-check' : 'mdi-close'
    "
    variant="text"
    size="x-small"
    class="hover-copy-button"
    :title="
      t(
        `core.common.${
          copied === null ? 'copy' : copied ? 'copied' : 'copyFailed'
        }`,
      )
    "
    :aria-label="`${t('core.common.copy')}: ${text}`"
    @click.stop="copy"
    @keydown.enter.stop
    @keydown.space.stop
  />
</template>

<script setup>
import { onBeforeUnmount, ref } from "vue";
import { useI18n } from "@/i18n/composables";
import { copyToClipboard } from "@/utils/clipboard";

const props = defineProps({
  text: { type: String, required: true },
});
const { t } = useI18n();
const copied = ref(null);
let resetTimer;

async function copy(event) {
  clearTimeout(resetTimer);
  try {
    copied.value = await copyToClipboard(props.text, {
      container: event.currentTarget.closest(".v-overlay__content"),
    });
  } catch {
    copied.value = false;
  }
  resetTimer = setTimeout(() => {
    copied.value = null;
  }, 1500);
}

onBeforeUnmount(() => clearTimeout(resetTimer));
</script>

<style scoped>
.hover-copy-button {
  position: absolute;
  transition: none;
  opacity: 0;
  pointer-events: none;
}

.v-list-item:hover .hover-copy-button,
.v-list-item:focus-within .hover-copy-button,
.hover-copy-button:focus-visible {
  position: relative;
  opacity: 1;
  pointer-events: auto;
}

@media (hover: none) {
  .hover-copy-button {
    position: relative;
    opacity: 1;
    pointer-events: auto;
  }
}
</style>
