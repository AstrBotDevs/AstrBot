<template>
  <v-card class="item-card hover-elevation pa-4" elevation="0">
    <div class="item-card-content" :style="{ opacity: getItemEnabled() ? 1 : 0.6 }">
      <!-- 标题 + 开关 -->
      <div class="item-card-header">
        <div class="item-card-title text-h4 font-weight-bold" :title="getItemTitle()">
          {{ getItemTitle() }}
        </div>

        <div class="item-card-switch">
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
                inset
              ></v-switch>
            </template>
            <span>{{ getItemEnabled() ? t('core.common.itemCard.enabled') : t('core.common.itemCard.disabled') }}</span>
          </v-tooltip>
        </div>
      </div>

      <!-- 中间层 UI -->
      <div class="item-card-details">
        <slot name="item-details" :item="item"></slot>
      </div>

      <!-- logo + 操作按钮 -->
      <div class="item-card-footer">
        <div v-if="bglogo" class="item-card-logo">
          <v-img
            :src="bglogo"
            width="64"
            height="64"
            contain
            :style="{ opacity: getItemEnabled() ? 0.9 : 0.4 }"
          ></v-img>
        </div>

        <div class="item-card-actions">
          <v-btn
            variant="outlined"
            color="primary"
            rounded="pill"
            size="small"
            block
            :disabled="loading"
            @click="$emit('edit', item)"
          >
            <v-icon start>mdi-pencil</v-icon>
            {{ t('core.common.itemCard.edit') }}
          </v-btn>

          <v-btn
            variant="outlined"
            color="error"
            rounded="pill"
            size="small"
            block
            :disabled="loading"
            @click="$emit('delete', item)"
          >
            <v-icon start>mdi-delete-outline</v-icon>
            {{ t('core.common.itemCard.delete') }}
          </v-btn>

          <v-btn
            v-if="showCopyButton"
            variant="tonal"
            color="secondary"
            rounded="pill"
            size="small"
            block
            :disabled="loading"
            @click="$emit('copy', item)"
          >
            <v-icon start>mdi-content-copy</v-icon>
            {{ t('core.common.itemCard.copy') }}
          </v-btn>

          <slot name="actions" :item="item"></slot>
        </div>
      </div>
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
    },
    showCopyButton: {
      type: Boolean,
      default: false
    }
  },
  emits: ['toggle-enabled', 'delete', 'edit', 'copy'],
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
  min-height: 160px;
  width: 100%;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  border: 1px solid #e0e0e0;
}

.item-card-content {
  position: relative;
  overflow: hidden;
  flex: 1 1 auto;
  height: 100%;
  display: flex;
  flex-direction: column;
}

.item-card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.item-card-title {
  min-width: 0;
  flex: 1 1 auto;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.item-card-switch {
  flex: 0 0 auto;
}

.item-card-details {
  width: 100%;
  margin-top: 6px;
  margin-bottom: 10px;
}

.item-card-footer {
  margin-top: auto;
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 12px;
}

.item-card-actions {
  min-width: 100px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  align-items: stretch;
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
