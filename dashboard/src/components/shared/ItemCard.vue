<template>
  <v-card class="item-card hover-elevation" :variant="variant" elevation="0">
    <v-card-title class="d-flex justify-space-between align-center pb-1 pt-3">
      <span class="text-h2 text-truncate" :title="getItemTitle()">{{
        getItemTitle()
      }}</span>
      <v-tooltip location="top">
        <template #activator="{ props: activatorProps }">
          <v-switch
            color="primary"
            hide-details
            density="compact"
            :model-value="getItemEnabled()"
            :loading="loading"
            :disabled="loading || disableToggle"
            v-bind="activatorProps"
            @update:model-value="toggleEnabled"
          ></v-switch>
        </template>
        <span>{{
          getItemEnabled()
            ? t('core.common.itemCard.enabled')
            : t('core.common.itemCard.disabled')
        }}</span>
      </v-tooltip>
    </v-card-title>

    <v-card-text>
      <slot name="item-details" :item="item"></slot>
    </v-card-text>

    <v-card-actions class="item-card__actions">
      <v-btn
        variant="outlined"
        color="error"
        size="small"
        :disabled="loading || disableDelete"
        @click="$emit('delete', item)"
      >
        {{ t('core.common.itemCard.delete') }}
      </v-btn>
      <v-btn
        v-if="showEditButton"
        variant="tonal"
        color="primary"
        size="small"
        :disabled="loading"
        @click="$emit('edit', item)"
      >
        {{ t('core.common.itemCard.edit') }}
      </v-btn>
      <v-btn
        v-if="showCopyButton"
        variant="tonal"
        color="secondary"
        size="small"
        :disabled="loading"
        @click="$emit('copy', item)"
      >
        {{ t('core.common.itemCard.copy') }}
      </v-btn>
      <slot name="actions" :item="item"></slot>
      <v-spacer></v-spacer>
    </v-card-actions>

    <div
      v-if="bglogo"
      class="item-card__background d-flex justify-end align-center"
    >
      <v-img
        :src="bglogo"
        :class="{ 'provider-icon--monochrome': bglogoMonochrome }"
        contain
        width="120"
        height="120"
      ></v-img>
    </div>
  </v-card>
</template>

<script setup lang="ts">
import { useI18n } from '@/i18n/composables';

type CardItem = Record<string, unknown>;
type CardVariant =
  'flat' | 'text' | 'plain' | 'outlined' | 'elevated' | 'tonal';

interface ItemCardProps {
  item: CardItem;
  titleField?: string;
  enabledField?: string;
  bglogo?: string | null;
  bglogoMonochrome?: boolean;
  loading?: boolean;
  showCopyButton?: boolean;
  showEditButton?: boolean;
  disableToggle?: boolean;
  disableDelete?: boolean;
  variant?: CardVariant | undefined;
}

const props = withDefaults(defineProps<ItemCardProps>(), {
  titleField: 'id',
  enabledField: 'enable',
  bglogo: null,
  bglogoMonochrome: false,
  loading: false,
  showCopyButton: false,
  showEditButton: true,
  disableToggle: false,
  disableDelete: false,
  variant: undefined,
});

const emit = defineEmits<{
  'toggle-enabled': [item: CardItem];
  delete: [item: CardItem];
  edit: [item: CardItem];
  copy: [item: CardItem];
}>();

const { t } = useI18n();

function getItemTitle(): string {
  return String(props.item[props.titleField] ?? '');
}

function getItemEnabled(): boolean {
  return Boolean(props.item[props.enabledField]);
}

function toggleEnabled(): void {
  emit('toggle-enabled', props.item);
}
</script>

<style scoped>
.item-card {
  background: rgb(var(--v-theme-surface));
  position: relative;
  padding: var(--astrbot-space-1);
  border-radius: 8px;
  overflow: hidden;
  min-height: 220px;
  height: 100%;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}

.hover-elevation:hover {
  background: rgb(var(--v-theme-surface-variant));
}

.item-card__actions {
  margin: var(--astrbot-space-2);
}

.item-card__background {
  position: absolute;
  right: var(--astrbot-space-4);
  bottom: var(--astrbot-space-4);
  opacity: 0.2;
}

.item-status-indicator {
  position: absolute;
  top: 8px;
  left: 8px;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background-color: rgb(var(--v-theme-on-surface-variant));
  z-index: 10;
}

.item-status-indicator.active {
  background-color: rgb(var(--v-theme-success));
}
</style>
