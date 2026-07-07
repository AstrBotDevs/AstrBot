<script setup>
import { useI18n } from '@/i18n/composables';
import { computed } from 'vue';
import { useRoute } from 'vue-router';

const props = defineProps({ item: Object, level: Number, rail: Boolean });
const { t } = useI18n();
const route = useRoute();

const itemStyle = computed(() => {
  const lvl = props.level ?? 0;
  const indent = props.rail ? '0px' : `${lvl * 24}px`;
  return { '--indent-padding': indent };
});

const isItemActive = computed(() => {
  if (!props.item || props.item.type === 'external' || !props.item.to) return false;
  if (typeof props.item.to !== 'string') return false;
  if (props.item.to.includes('#')) {
    const [path, hash] = props.item.to.split('#');
    return route.path === path && route.hash === `#${hash}`;
  }
  const targetPath = props.item.to.replace(/\/$/, '') || '/';
  if (targetPath === '/') {
    return route.path === targetPath;
  }
  return route.path === targetPath || route.path.startsWith(`${targetPath}/`);
});

const itemTitle = computed(() => {
  if (!props.item?.title) return '';
  return props.item.isRawTitle ? props.item.title : t(props.item.title);
});

</script>

<template>
  <v-list-group v-if="item.children" :value="item.title" :class="{ 'rail-group': rail }">
    <template v-slot:activator="{ props: groupProps }">
      <v-tooltip v-if="rail" location="right" :text="itemTitle" open-delay="180">
        <template v-slot:activator="{ props: tooltipProps }">
          <v-list-item v-bind="{ ...groupProps, ...tooltipProps }" rounded class="mb-1" color="secondary"
            :prepend-icon="item.icon" :style="{ '--indent-padding': '0px' }" :aria-label="itemTitle">
            <v-list-item-title style="font-size: 14px; font-weight: 500; line-height: 1.2; word-break: break-word;">
              {{ itemTitle }}
            </v-list-item-title>
          </v-list-item>
        </template>
      </v-tooltip>
      <v-list-item v-else v-bind="groupProps" rounded class="mb-1" color="secondary" :prepend-icon="item.icon"
        :style="{ '--indent-padding': '0px' }">
        <v-list-item-title style="font-size: 14px; font-weight: 500; line-height: 1.2; word-break: break-word;">
          {{ itemTitle }}
        </v-list-item-title>
      </v-list-item>
    </template>

    <!-- children -->
    <template v-for="(child, index) in item.children" :key="child.title || child.to || `child-${index}`">
      <NavItem :item="child" :level="(level || 0) + 1" :rail="rail" />
    </template>
  </v-list-group>

  <v-tooltip v-else-if="rail" location="right" :text="itemTitle" open-delay="180">
    <template v-slot:activator="{ props: tooltipProps }">
      <v-list-item v-bind="tooltipProps" :to="item.type === 'external' ? '' : item.to"
        :href="item.type === 'external' ? item.to : ''" :active="isItemActive" rounded class="mb-1"
        color="secondary" :disabled="item.disabled" :target="item.type === 'external' ? '_blank' : ''"
        :style="itemStyle" :aria-label="itemTitle">
        <template v-slot:prepend>
          <v-icon v-if="item.icon" :size="item.iconSize" class="hide-menu" :icon="item.icon"></v-icon>
        </template>
        <v-list-item-title style="font-size: 14px;">{{ itemTitle }}</v-list-item-title>
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
  </v-tooltip>

  <v-list-item v-else :to="item.type === 'external' ? '' : item.to" :href="item.type === 'external' ? item.to : ''"
    :active="isItemActive" rounded class="mb-1" color="secondary" :disabled="item.disabled"
    :target="item.type === 'external' ? '_blank' : ''" :style="itemStyle">
    <template v-slot:prepend>
      <v-icon v-if="item.icon" :size="item.iconSize" class="hide-menu" :icon="item.icon"></v-icon>
    </template>
    <v-list-item-title style="font-size: 14px;">{{ itemTitle }}</v-list-item-title>
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
.rail-group {
  border-radius: 12px;
  transition: background-color 0.18s ease;
}

.rail-group.v-list-group--open {
  background: rgba(var(--v-theme-primary), 0.06);
}

.rail-group.v-list-group--open > .v-list-group__items {
  padding-bottom: 2px;
}
</style>
