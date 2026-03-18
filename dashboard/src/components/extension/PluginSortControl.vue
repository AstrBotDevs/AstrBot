<script setup>
const props = defineProps({
  modelValue: {
    type: String,
    required: true,
  },
  items: {
    type: Array,
    required: true,
  },
  label: {
    type: String,
    required: true,
  },
  order: {
    type: String,
    default: "desc",
  },
  ascendingLabel: {
    type: String,
    default: "Ascending",
  },
  descendingLabel: {
    type: String,
    default: "Descending",
  },
  showOrder: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits(["update:modelValue", "update:order"]);

const updateSortBy = (value) => {
  emit("update:modelValue", value);
};

const toggleOrder = () => {
  emit("update:order", props.order === "desc" ? "asc" : "desc");
};
</script>

<template>
  <div class="plugin-sort-control">
    <v-select
      :model-value="modelValue"
      :items="items"
      density="compact"
      variant="outlined"
      hide-details
      :label="label"
      class="plugin-sort-control__select"
      @update:model-value="updateSortBy"
    >
      <template #prepend-inner>
        <v-icon size="small">
          mdi-sort
        </v-icon>
      </template>
    </v-select>

    <v-btn
      v-if="showOrder"
      icon
      variant="text"
      density="compact"
      @click="toggleOrder"
    >
      <v-icon>
        {{
          order === "desc" ? "mdi-arrow-down-thin" : "mdi-arrow-up-thin"
        }}
      </v-icon>
      <v-tooltip
        activator="parent"
        location="top"
      >
        {{ order === "desc" ? descendingLabel : ascendingLabel }}
      </v-tooltip>
    </v-btn>
  </div>
</template>

<style scoped>
.plugin-sort-control {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.plugin-sort-control__select {
  min-width: 180px;
  max-width: 220px;
}

.plugin-sort-control__select :deep(.v-field__input),
.plugin-sort-control__select :deep(.v-field-label),
.plugin-sort-control__select :deep(.v-select__selection-text),
.plugin-sort-control__select :deep(.v-field__prepend-inner) {
  font-size: 0.875rem;
}
</style>
