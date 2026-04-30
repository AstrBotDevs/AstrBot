<template>
  <v-card
    class="outlined-action-list-item rounded-lg"
    :class="{ 'outlined-action-list-item--clickable': clickable }"
    variant="outlined"
    :ripple="false"
    @click="handleClick"
  >
    <div class="outlined-action-list-item__main">
      <div class="outlined-action-list-item__content">
        <div class="outlined-action-list-item__header">
          <slot name="title-prepend"></slot>
          <div class="outlined-action-list-item__title">
            {{ title }}
          </div>
          <slot name="title-extra"></slot>
        </div>

        <slot></slot>
      </div>

      <div
        v-if="$slots.actions || $slots.control"
        class="outlined-action-list-item__actions"
      >
        <div
          v-if="$slots.actions"
          class="outlined-action-list-item__hover-actions"
        >
          <slot name="actions"></slot>
        </div>

        <slot name="control"></slot>
      </div>
    </div>
  </v-card>
</template>

<script setup>
const props = defineProps({
  title: {
    type: String,
    required: true,
  },
  clickable: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits(["click"]);

const handleClick = (event) => {
  if (!props.clickable) return;
  emit("click", event);
};
</script>

<style scoped>
.outlined-action-list-item {
  background: rgb(var(--v-theme-surface));
  transition: background-color 0.16s ease;
}

.outlined-action-list-item:hover,
.outlined-action-list-item:focus-within {
  background: rgba(var(--v-theme-on-surface), 0.04);
}

.outlined-action-list-item--clickable {
  cursor: pointer;
}

.outlined-action-list-item :deep(.v-card__overlay),
.outlined-action-list-item :deep(.v-ripple__container) {
  display: none;
}

.outlined-action-list-item__main {
  align-items: center;
  display: flex;
  gap: 16px;
  justify-content: space-between;
  min-height: 104px;
  padding: 16px;
}

.outlined-action-list-item__content {
  min-width: 0;
}

.outlined-action-list-item__header {
  align-items: center;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 6px;
}

.outlined-action-list-item__title {
  font-size: 1rem;
  font-weight: 700;
  line-height: 1.35;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.outlined-action-list-item__actions {
  align-items: center;
  display: flex;
  flex-shrink: 0;
  gap: 8px;
  margin-left: auto;
}

.outlined-action-list-item__hover-actions {
  align-items: center;
  display: flex;
  gap: 4px;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.16s ease;
}

.outlined-action-list-item:hover .outlined-action-list-item__hover-actions,
.outlined-action-list-item:focus-within .outlined-action-list-item__hover-actions {
  opacity: 1;
  pointer-events: auto;
}

@media (max-width: 860px) {
  .outlined-action-list-item__main {
    align-items: stretch;
    flex-direction: column;
  }

  .outlined-action-list-item__actions {
    flex-wrap: wrap;
    justify-content: flex-end;
    margin-left: 0;
  }

  .outlined-action-list-item__hover-actions {
    opacity: 1;
    pointer-events: auto;
  }
}
</style>
