<script setup>
import { computed } from "vue";
import { useModuleI18n } from "@/i18n/composables";

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false,
  },
  targets: {
    type: Array,
    default: () => [],
  },
  exceptions: {
    type: Array,
    default: () => [],
  },
});

const emit = defineEmits(["update:modelValue", "confirm"]);
const { tm } = useModuleI18n("features/extension");

const show = computed({
  get: () => props.modelValue,
  set: (value) => emit("update:modelValue", value),
});
</script>

<template>
  <v-dialog v-model="show" max-width="620" :persistent="false">
    <v-card>
      <v-card-title class="text-h3 pa-4 pb-0 pl-6">
        {{ tm("batch.market.confirmTitle") }}
      </v-card-title>
      <v-card-text>
        <p class="mb-3">
          {{
            tm("batch.market.confirmMessage", {
              count: targets.length,
            })
          }}
        </p>

        <v-list class="batch-target-list" density="compact">
          <v-list-item
            v-for="plugin in targets"
            :key="plugin.market_plugin_id || plugin.repo || plugin.name"
            :title="plugin.display_name || plugin.name"
            prepend-icon="mdi-puzzle-outline"
          />
        </v-list>

        <v-alert
          v-if="exceptions.length > 0"
          type="warning"
          variant="tonal"
          density="comfortable"
          class="mt-4"
        >
          <div class="font-weight-medium mb-2">
            {{ tm("batch.market.exceptionsTitle") }}
          </div>
          <ul class="batch-exception-list">
            <li v-for="item in exceptions" :key="item.key">
              <span class="font-weight-medium">{{ item.label }}</span
              >:
              {{ item.reason }}
            </li>
          </ul>
        </v-alert>
      </v-card-text>
      <v-card-actions class="pa-4">
        <v-spacer />
        <v-btn variant="text" @click="show = false">
          {{ tm("batch.actions.cancel") }}
        </v-btn>
        <v-btn color="primary" variant="tonal" @click="emit('confirm')">
          {{
            tm("batch.market.confirmAction", {
              count: targets.length,
            })
          }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<style scoped>
.batch-target-list {
  max-height: 260px;
  overflow-y: auto;
}

.batch-exception-list {
  padding-left: 20px;
}
</style>
