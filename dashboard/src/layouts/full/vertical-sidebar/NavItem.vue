<script setup>
import { useI18n } from '@/i18n/composables';

const props = defineProps({ item: Object, level: Number });
const { t } = useI18n();
</script>

<template>
  <v-list-group v-if="item.children" :value="item.title">
    <template v-slot:activator="{ props }">
      <v-list-item
        v-bind="props"
        rounded
        class="mb-1"
        color="secondary"
        :prepend-icon="item.icon"
      >
        <v-list-item-title style="font-size: 14px; font-weight: 500; line-height: 1.2; word-break: break-word;">
          {{ t(item.title) }}
        </v-list-item-title>
      </v-list-item>
    </template>
    
    <template v-for="(child, index) in item.children" :key="index">
      <NavItem :item="child" :level="(level || 0) + 1" />
    </template>
  </v-list-group>

  <v-list-item
    v-else
    :to="item.type === 'external' ? '' : item.to"
    :href="item.type === 'external' ? item.to : ''"
    rounded
    class="mb-1"
    color="secondary"
    :disabled="item.disabled"
    :target="item.type === 'external' ? '_blank' : ''"
    :style="level > 0 ? { paddingLeft: '32px' } : {}"
  >
    <template v-slot:prepend>
      <v-icon v-if="item.icon" :size="item.iconSize" class="hide-menu" :icon="item.icon"></v-icon>
    </template>
    <v-list-item-title style="font-size: 14px; line-height: 1.2; word-break: break-word;">{{ t(item.title) }}</v-list-item-title>
    <v-list-item-subtitle v-if="item.subCaption" class="text-caption mt-n1 hide-menu">
      {{ item.subCaption }}
    </v-list-item-subtitle>
    <template v-slot:append v-if="item.chip">
      <v-chip
        :color="item.chipColor"
        class="sidebarchip hide-menu"
        :size="item.chipIcon ? 'small' : 'default'"
        :variant="item.chipVariant"
        :prepend-icon="item.chipIcon"
      >
        {{ item.chip }}
      </v-chip>
    </template>
  </v-list-item>
</template>
