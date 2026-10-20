<template>
  <div>
    <v-row v-if="items.length === 0">
      <v-col cols="12" class="text-center pa-8">
        <v-icon size="64" color="grey-lighten-1">{{ emptyIcon }}</v-icon>
        <p class="text-grey mt-4">{{ displayEmptyText }}</p>
      </v-col>
    </v-row>

    <v-row v-else>
      <v-col v-for="(item, index) in items" :key="index" cols="12" md="6" lg="4" xl="3">
        <v-card class="item-card hover-elevation" style="padding: 4px;" elevation="0">
          <div class="item-status-indicator" :class="{'active': getItemEnabled(item)}"></div>
          <v-card-title class="d-flex justify-space-between align-center pb-1 pt-3">
            <span class="text-h2 text-truncate" :title="getItemTitle(item)">{{ getItemTitle(item) }}</span>
            <v-tooltip location="top">
              <template v-slot:activator="{ props }">
                <v-switch 
                  color="primary" 
                  hide-details 
                  density="compact" 
                  :model-value="getItemEnabled(item)"
                  v-bind="props" 
                  @update:model-value="toggleEnabled(item)"
                ></v-switch>
              </template>
              <span>{{ getItemEnabled(item) ? t('core.common.itemCard.enabled') : t('core.common.itemCard.disabled') }}</span>
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
              class="rounded-circle"
            ></v-img>
          </div>

        </v-card>
      </v-col>
    </v-row>
  </div>
</template>

<script>
import { useI18n } from '@/i18n/composables';

export default {
  name: 'ItemCardGrid',
  setup() {
    const { t } = useI18n();
    return { t };
  },
  props: {
    items: {
      type: Array,
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
    emptyIcon: {
      type: String,
      default: 'mdi-alert-circle-outline'
    },
    emptyText: {
      type: String,
      default: null
    },
    bglogo: {
      type: String,
      default: null
    }
  },
  emits: ['toggle-enabled', 'delete', 'edit'],
  computed: {
    displayEmptyText() {
      return this.emptyText || this.t('core.common.itemCard.noData');
    }
  },
  methods: {
    getItemTitle(item) {
      return item[this.titleField];
    },
    getItemEnabled(item) {
      return item[this.enabledField];
    },
    toggleEnabled(item) {
      this.$emit('toggle-enabled', item);
    }
  }
}
</script>

<style>

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
</style>
