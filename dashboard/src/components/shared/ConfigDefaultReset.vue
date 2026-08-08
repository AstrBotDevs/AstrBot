<script setup>
import { computed } from 'vue';
import { useI18n } from '@/i18n/composables';
import {
  canRestorePluginConfigDefault,
  getPluginConfigDefaultValue,
} from '@/utils/pluginConfigDefaults';

const props = defineProps({
  modelValue: {
    type: [String, Number, Boolean, Array, Object],
    default: null,
  },
  itemMeta: {
    type: Object,
    default: null,
  },
  enabled: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits(['reset']);
const { t } = useI18n();
const showReset = computed(
  () =>
    props.enabled &&
    canRestorePluginConfigDefault(props.modelValue, props.itemMeta),
);

function resetToDefault() {
  emit('reset', getPluginConfigDefaultValue(props.itemMeta));
}
</script>

<template>
  <div class="config-default-reset">
    <div class="config-default-reset__field"><slot /></div>
    <v-btn
      v-if="showReset"
      icon
      size="x-small"
      variant="text"
      color="primary"
      class="config-default-reset__button"
      :title="t('core.common.restoreDefault')"
      :aria-label="t('core.common.restoreDefault')"
      @click="resetToDefault"
    >
      <v-icon size="18">mdi-restore</v-icon>
    </v-btn>
  </div>
</template>

<style scoped>
.config-default-reset {
  display: flex;
  align-items: center;
  gap: 4px;
  width: 100%;
}

.config-default-reset__field {
  flex: 1;
  min-width: 0;
}

.config-default-reset__button {
  flex: 0 0 auto;
}
</style>
