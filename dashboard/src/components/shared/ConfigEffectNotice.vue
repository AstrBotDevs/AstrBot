<script setup>
import { computed } from "vue";
import { useModuleI18n } from "@/i18n/composables";
import { getConfigEffectNotices } from "@/utils/configEffects.mjs";

const props = defineProps({
  field: { type: String, required: true },
  config: { type: Object, required: true },
  pluginName: { type: String, default: "" },
});
const { tm } = useModuleI18n("features/config");
const notices = computed(() =>
  props.pluginName ? [] : getConfigEffectNotices(props.field, props.config),
);
</script>

<template>
  <div
    v-if="notices.length"
    class="config-effects"
    role="status"
    aria-live="polite"
  >
    <v-chip size="x-small" color="warning" variant="tonal" class="mb-1">
      {{ tm("effects.conditional") }}
    </v-chip>
    <p v-for="notice in notices" :key="notice" class="config-effect-reason">
      {{ tm(`effects.${notice}`) }}
    </p>
  </div>
</template>

<style scoped>
.config-effects {
  margin-top: 8px;
  font-size: 0.75rem;
  line-height: 1.5;
  white-space: normal;
}
.config-effect-reason {
  margin: 0 0 4px;
  color: rgb(var(--v-theme-on-surface));
}
</style>
