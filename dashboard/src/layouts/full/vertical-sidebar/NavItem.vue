<script setup>
import { useI18n } from '@/i18n/composables';
import { useCustomizerStore } from '@/stores/customizer';
import { computed } from 'vue';

const props = defineProps({ item: Object, level: Number });
const { t } = useI18n();
const customizer = useCustomizerStore();

const itemStyle = computed(() => {
  const lvl = props.level ?? 0;
  const indent = customizer.mini_sidebar ? '0px' : `${lvl * 24}px`;
  return { '--indent-padding': indent };
});
</script>

<template>
  <v-list-group v-if="item.children" :value="item.title" :class="{ 'group-bordered': customizer.mini_sidebar }">
    <template v-slot:activator="{ props }">
      <v-list-item v-bind="props" rounded class="mb-1" color="secondary" :prepend-icon="item.icon"
        :style="{ '--indent-padding': '0px' }">
        <v-list-item-title style="font-size: 14px; font-weight: 500; line-height: 1.2; word-break: break-word;">
          {{ t(item.title) }}
        </v-list-item-title>
      </v-list-item>
    </template>

    <!-- children -->
    <template v-for="(child, index) in item.children" :key="index">
      <NavItem :item="child" :level="(level || 0) + 1" />
    </template>
  </v-list-group>

  <v-list-item v-else :to="item.type === 'external' ? '' : item.to" :href="item.type === 'external' ? item.to : ''" rounded
    class="mb-1" color="secondary" :disabled="item.disabled" :target="item.type === 'external' ? '_blank' : ''" :style="itemStyle">
    <template v-slot:prepend>
      <v-icon v-if="item.icon" :size="item.iconSize" class="hide-menu" :icon="item.icon"></v-icon>
    </template>
    <v-list-item-title style="font-size: 14px;">{{ t(item.title) }}</v-list-item-title>
    <v-list-item-subtitle v-if="item.subCaption" class="text-caption mt-n1 hide-menu">
      {{ item.subCaption }}
    </v-list-item-subtitle>
    <template v-slot:append v-if="item.chip">
      <v-chip :color="item.chipColor" class="sidebarchip hide-menu" :size="item.chipIcon ? 'small' : 'default'"
        :variant="item.chipVariant" :prepend-icon="item.chipIcon">
        {{ item.chip }}
      </v-chip>
    </template>
  </v-list-item>
</template>

<style>
/* 在折叠(mini)状态下，分组展开时给整个分组（母项+子项）加边框以便区分 */
.group-bordered.v-list-group--open {
  border: 2px solid rgba(var(--v-theme-borderLight), 0.35);
  border-radius: 8px;
  background: rgba(var(--v-theme-borderLight), 0.04);
}
</style>