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
  if (!props.item || props.item.type === 'external' || !props.item.to)
    return false;
  if (typeof props.item.to !== 'string') return false;
  if (props.item.to.includes('#')) {
    const [path, hash] = props.item.to.split('#');
    return route.path === path && route.hash === `#${hash}`;
  }
  const targetPath = props.item.to.replace(/\/$/, '') || '/';
  return (
    route.path === targetPath ||
    (targetPath !== '/' && route.path.startsWith(`${targetPath}/`))
  );
});

const itemTitle = computed(() => {
  if (!props.item?.title) return '';
  return props.item.isRawTitle ? props.item.title : t(props.item.title);
});
</script>

<template>
  <v-list-group
    v-if="item.children"
    :value="item.title"
    :class="{ 'rail-group': rail }"
  >
    <template #activator="{ props: activatorProps }">
      <v-tooltip
        v-if="rail"
        location="right"
        :text="itemTitle"
        open-delay="180"
      >
        <template #activator="{ props: tooltipProps }">
          <v-list-item
            v-bind="{ ...activatorProps, ...tooltipProps }"
            rounded="sm"
            class="nav-item mb-1"
            color="secondary"
            :prepend-icon="item.icon"
            :aria-label="itemTitle"
          >
            <v-list-item-title class="nav-item-title">
              {{ itemTitle }}
            </v-list-item-title>
          </v-list-item>
        </template>
      </v-tooltip>
      <v-list-item
        v-else
        v-bind="activatorProps"
        rounded="sm"
        class="nav-item mb-1"
        color="secondary"
        :prepend-icon="item.icon"
      >
        <v-list-item-title class="nav-item-title">
          {{ itemTitle }}
        </v-list-item-title>
      </v-list-item>
    </template>

    <!-- children -->
    <template
      v-for="(child, index) in item.children"
      :key="child.title || child.to || `child-${index}`"
    >
      <NavItem :item="child" :level="(level || 0) + 1" :rail="rail" />
    </template>
  </v-list-group>

  <v-tooltip
    v-else-if="rail"
    location="right"
    :text="itemTitle"
    open-delay="180"
  >
    <template #activator="{ props: tooltipProps }">
      <v-list-item
        v-bind="tooltipProps"
        :to="item.type === 'external' ? '' : item.to"
        :href="item.type === 'external' ? item.to : ''"
        :active="isItemActive"
        rounded="sm"
        class="nav-item mb-1"
        color="secondary"
        :disabled="item.disabled"
        :target="item.type === 'external' ? '_blank' : ''"
        :style="itemStyle"
        :aria-label="itemTitle"
      >
        <template #prepend>
          <v-icon
            v-if="item.icon"
            :size="item.iconSize"
            class="hide-menu"
            :icon="item.icon"
          ></v-icon>
        </template>
        <v-list-item-title class="nav-item-title">{{
          itemTitle
        }}</v-list-item-title>
      </v-list-item>
    </template>
  </v-tooltip>

  <v-list-item
    v-else
    :to="item.type === 'external' ? '' : item.to"
    :href="item.type === 'external' ? item.to : ''"
    :active="isItemActive"
    rounded="sm"
    class="nav-item mb-1"
    color="secondary"
    :disabled="item.disabled"
    :target="item.type === 'external' ? '_blank' : ''"
    :style="itemStyle"
  >
    <template #prepend>
      <v-icon
        v-if="item.icon"
        :size="item.iconSize"
        class="hide-menu"
        :icon="item.icon"
      ></v-icon>
    </template>
    <v-list-item-title class="nav-item-title">{{
      itemTitle
    }}</v-list-item-title>
    <v-list-item-subtitle
      v-if="item.subCaption"
      class="text-caption mt-n1 hide-menu"
    >
      {{ item.subCaption }}
    </v-list-item-subtitle>
    <template v-if="item.chip" #append>
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

<style>
.nav-item-title {
  font-size: 14px;
  font-weight: 500;
  line-height: 20px;
  overflow-wrap: anywhere;
}

.nav-item {
  --indent-padding: 0;
}
</style>
