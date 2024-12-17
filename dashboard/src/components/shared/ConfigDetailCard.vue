<script setup>
import UiParentCard from '@/components/shared/UiParentCard.vue';

const props = defineProps({
  config: Array
});
</script>

<template>
  <a v-show="config.length === 0">该插件没有配置</a>
  <UiParentCard v-for="group in config" :key="group.name" :title="group.name" style="margin-bottom: 16px;">
    <template v-for="item in group.body">
      <template v-if="item.config_type === 'item'">
        <template v-if="item.val_type === 'bool'">
          <v-switch v-model="item.value" :label="item.name" :hint="item.description" color="primary" inset></v-switch>
        </template>
        <template v-else-if="item.val_type === 'str'">
          <v-text-field v-model="item.value" :label="item.name" :hint="item.description" style="margin-bottom: 8px;"
            variant="outlined"></v-text-field>
        </template>
        <template v-else-if="item.val_type === 'int'">
          <v-text-field v-model="item.value" :label="item.name" :hint="item.description" style="margin-bottom: 8px;"
            variant="outlined"></v-text-field>
        </template>
        <template v-else-if="item.val_type === 'list'">
          <span>{{ item.name }}</span>
          <v-combobox v-model="item.value" chips clearable label="请添加" multiple prepend-icon="mdi-tag-multiple-outline">
            <template v-slot:selection="{ attrs, item, select, selected }">
              <v-chip v-bind="attrs" :model-value="selected" closable @click="select" @click:close="remove(item)">
                <strong>{{ item }}</strong>
              </v-chip>
            </template>
          </v-combobox>
        </template>
      </template>
      <template v-else-if="item.config_type === 'divider'">
        <v-divider style="margin-top: 8px; margin-bottom: 8px;"></v-divider>
      </template>
    </template>
  </UiParentCard>
</template>
