<template>
  <div>
    <v-row v-if="items.length === 0">
      <v-col cols="12" class="text-center pa-8">
        <v-icon size="64" color="grey-lighten-1">{{ emptyIcon }}</v-icon>
        <p class="text-grey mt-4">{{ emptyText }}</p>
      </v-col>
    </v-row>

    <v-row v-else>
      <v-col v-for="(item, index) in items" :key="index" cols="12" md="6" lg="4" xl="3">
        <v-card class="item-card hover-elevation" :color="getItemEnabled(item) ? '' : 'grey-lighten-4'">
          <div class="item-status-indicator" :class="{'active': getItemEnabled(item)}"></div>
          <v-card-title class="d-flex justify-space-between align-center pb-1 pt-3">
            <span class="text-h4 text-truncate" :title="getItemTitle(item)">{{ getItemTitle(item) }}</span>
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
              <span>{{ getItemEnabled(item) ? '已启用' : '已禁用' }}</span>
            </v-tooltip>
          </v-card-title>
          
          <v-card-text>
            <slot name="item-details" :item="item"></slot>
          </v-card-text>
          
          <v-divider></v-divider>
          
          <v-card-actions class="pa-2">
            <v-spacer></v-spacer>
            <v-btn 
              variant="text" 
              size="small" 
              color="error" 
              prepend-icon="mdi-delete" 
              @click="$emit('delete', item)"
            >
              删除
            </v-btn>
            <v-btn 
              variant="text" 
              size="small" 
              color="primary" 
              prepend-icon="mdi-pencil" 
              @click="$emit('edit', item)"
            >
              编辑
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-col>
    </v-row>
  </div>
</template>

<script>
export default {
  name: 'ItemCardGrid',
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
      default: '暂无数据'
    }
  },
  emits: ['toggle-enabled', 'delete', 'edit'],
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

<style scoped>
.item-card {
  position: relative;
  border-radius: 8px;
  transition: all 0.3s ease;
  overflow: hidden;
  min-height: 220px;
  margin-bottom: 16px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}

.hover-elevation:hover {
  box-shadow: 0 6px 12px rgba(0, 0, 0, 0.1);
  transform: translateY(-2px);
}
</style>
