<script setup>
import { computed } from 'vue';
import { useModuleI18n } from '@/i18n/composables';
import ConfigPage from '@/views/ConfigPage.vue';

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false,
  },
  configId: {
    type: String,
    default: '',
  },
  configName: {
    type: String,
    default: '',
  },
});
const emit = defineEmits(['update:modelValue']);

const { tm } = useModuleI18n('core/shared');

const open = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value),
});

function close() {
  open.value = false;
}
</script>

<template>
  <v-overlay
    v-model="open"
    class="config-profile-drawer-overlay"
    location="right"
    transition="slide-x-reverse-transition"
    :scrim="true"
    @click:outside="close"
  >
    <v-card class="config-profile-drawer-card" elevation="12">
      <div class="config-profile-drawer-header">
        <div>
          <span class="text-h6">{{ tm('configProfileDrawer.title') }}</span>
          <div v-if="configName" class="text-caption text-grey">
            {{ configName }}
          </div>
        </div>
        <v-btn icon variant="text" :aria-label="tm('configProfileDrawer.close')" @click="close">
          <v-icon>mdi-close</v-icon>
        </v-btn>
      </div>
      <v-divider />
      <div class="config-profile-drawer-content">
        <ConfigPage v-if="open && configId" :initial-config-id="configId" />
      </div>
    </v-card>
  </v-overlay>
</template>

<style>
.config-profile-drawer-overlay {
  align-items: stretch;
  justify-content: flex-end;
}

.config-profile-drawer-card {
  display: flex;
  width: clamp(320px, 60vw, 820px);
  height: calc(100vh - 32px);
  flex-direction: column;
  margin: 16px;
}

.config-profile-drawer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px 12px;
}

.config-profile-drawer-content {
  flex: 1;
  overflow-y: auto;
  padding: 16px 16px 24px;
}
</style>
