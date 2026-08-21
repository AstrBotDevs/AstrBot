<script setup lang="ts">
import { useModuleI18n } from "@/i18n/composables";

withDefaults(
  defineProps<{
    activated: boolean;
    tooltipLocation?: "top" | "left";
  }>(),
  {
    tooltipLocation: "top",
  },
);

const emit = defineEmits(["toggle"]);
const { tm } = useModuleI18n("features/extension");
</script>

<template>
  <v-tooltip :location="tooltipLocation">
    <template #activator="{ props: tooltipProps }">
      <div class="plugin-activation-switch" @click.stop>
        <div v-bind="tooltipProps" class="plugin-activation-switch__control">
          <v-switch
            :model-value="activated"
            :aria-label="activated ? tm('buttons.stop') : tm('buttons.load')"
            color="success"
            density="compact"
            hide-details
            inset
            @update:model-value="emit('toggle')"
          />
        </div>
      </div>
    </template>
    <span>{{ activated ? tm("buttons.stop") : tm("buttons.load") }}</span>
  </v-tooltip>
</template>

<style scoped>
.plugin-activation-switch {
  display: flex;
  align-items: center;
  flex-shrink: 0;
}

.plugin-activation-switch__control {
  display: inline-flex;
  align-items: center;
}

.plugin-activation-switch :deep(.v-switch) {
  margin: 0;
}
</style>
