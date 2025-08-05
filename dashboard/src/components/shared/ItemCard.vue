<template>
  <v-card class="item-card hover-elevation" style="padding: 4px;" elevation="0">
    <v-card-title class="d-flex justify-space-between align-center pb-1 pt-3">
      <span class="text-h2 text-truncate" :title="getItemTitle()">{{ getItemTitle() }}</span>
      <v-tooltip location="top">
        <template v-slot:activator="{ props }">
          <v-switch 
            color="primary" 
            hide-details 
            density="compact" 
            :model-value="getItemEnabled()"
            :loading="loading"
            :disabled="loading"
            v-bind="props" 
            @update:model-value="toggleEnabled"
          ></v-switch>
        </template>
        <span>{{ getItemEnabled() ? t('core.common.itemCard.enabled') : t('core.common.itemCard.disabled') }}</span>
      </v-tooltip>
    </v-card-title>
    
    <v-card-text>
      <slot name="item-details" :item="item"></slot>
    </v-card-text>
    
    <v-card-actions style="margin: 8px;">
      <v-btn
        variant="outlined" 
        color="error"
        rounded="xl"
        @click="$emit('delete', item)"
      >
        {{ t('core.common.itemCard.delete') }}
      </v-btn>
      <v-btn
        variant="tonal"
        color="primary"
        rounded="xl"
        @click="$emit('edit', item)"
      >
        {{ t('core.common.itemCard.edit') }}
      </v-btn>
      <v-spacer></v-spacer>
    </v-card-actions>

    <div class="d-flex justify-end align-center" style="position: absolute; bottom: 16px; right: 16px; opacity: 0.2;" v-if="bglogo">
      <v-img
        :src="bglogo"
        contain
        width="120"
        height="120"
      ></v-img>
    </div>
  </v-card>
</template>

<script>
import { useI18n } from '@/i18n/composables';

export default {
  name: 'ItemCard',
  setup() {
    const { t } = useI18n();
    return { t };
  },
  props: {
    item: {
      type: Object,
      required: true
    },
    titleField: {
      type: String,
      default: 'id'
    },
    enabledField: {
      type: String,
      default: 'enable'
    },
    bglogo: {
      type: String,
      default: null
    },
    loading: {
      type: Boolean,
      default: false
    }
  },
  emits: ['toggle-enabled', 'delete', 'edit'],
  methods: {
    getItemTitle() {
      return this.item[this.titleField];
    },
    getItemEnabled() {
      return this.item[this.enabledField];
    },
    toggleEnabled() {
      this.$emit('toggle-enabled', this.item);
    }
  }
}
</script>

<style scoped>
.item-card {
  position: relative;
  border-radius: 18px;
  transition: all 0.3s ease;
  overflow: hidden;
  min-height: 220px;
  margin-bottom: 16px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}

.hover-elevation:hover {
  transform: translateY(-2px);
}

.item-status-indicator {
  position: absolute;
  top: 8px;
  left: 8px;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background-color: #ccc;
  z-index: 10;
}

.item-status-indicator.active {
  background-color: #4caf50;
}
</style>
