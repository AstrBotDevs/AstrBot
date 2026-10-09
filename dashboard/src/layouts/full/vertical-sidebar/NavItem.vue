<script setup>
import { useI18n } from '@/i18n/composables';
import { computed } from 'vue';
import { useRoute } from 'vue-router';
import { AppWindow, Pin, PinOff, Puzzle, User } from '@lucide/vue';
import { getSidebarCustomization } from '@/utils/sidebarCustomization';
import { findSubRouteDef, getSubRoutePath } from '@/utils/sidebarSubItems';

const props = defineProps({ item: Object, level: Number, rail: Boolean, pinnable: Boolean, pinnedTos: Array });
const emit = defineEmits(['togglePin']);
const { t } = useI18n();
const route = useRoute();

const itemStyle = computed(() => {
  const lvl = props.level ?? 0;
  const indent = props.rail ? '0px' : `${lvl * 24}px`;
  return { '--indent-padding': indent };
});

// Absolute paths of sub-routes the user lifted to first-level items; those
// paths must not light up their former parent item anymore.
const promotedPaths = computed(() => {
  const values = getSidebarCustomization()?.promotedSubRoutes ?? [];
  const paths = [];
  values.forEach((value) => {
    const def = findSubRouteDef(value);
    if (def) {
      const path = getSubRoutePath(def.parentTitle, def.value);
      if (path) paths.push(path);
    }
  });
  return paths;
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
  if (route.path === targetPath) return true;
  if (route.path.startsWith(`${targetPath}/`)) {
    // A promoted sub-route owns its path now: /data stays inactive while
    // /data/statistics is active.
    return !promotedPaths.value.some(
      (p) => route.path === p || route.path.startsWith(`${p}/`)
    );
  }
  return false;
});

const itemTitle = computed(() => {
  if (!props.item?.title) return '';
  return props.item.isRawTitle ? props.item.title : t(props.item.title);
});

// Plugin page hover card: display name shown in dark text with the plugin id
// in parentheses; plugins without a display name show only the id.
const pluginDisplayName = computed(() => {
  const info = props.item?.pluginInfo;
  if (!info) return '';
  if (info.displayName) return info.displayName;
  if (!props.item.isRawTitle) return '';
  return props.item.title !== info.id ? props.item.title : '';
});

const isPinned = computed(() => Boolean(props.pinnedTos?.includes(props.item?.to)));

const isVuetifyIcon = computed(() => typeof props.item?.icon === 'string');

</script>

<template>
  <v-list-group v-if="item.children" :value="item.title" :class="{ 'rail-group': rail }">
    <template v-slot:activator="{ props: groupProps }">
      <v-tooltip
        v-if="rail"
        location="right"
        :text="itemTitle"
        :open-delay="0"
        content-class="sidebar-rail-tooltip"
      >
        <template v-slot:activator="{ props: tooltipProps }">
          <v-list-item v-bind="{ ...groupProps, ...tooltipProps }" rounded class="dashboard-nav-item" color="secondary"
            :style="{ '--indent-padding': '0px' }" :aria-label="itemTitle">
            <template #prepend>
              <v-icon v-if="isVuetifyIcon" :icon="item.icon" size="18" />
              <component :is="item.icon" v-else-if="item.icon" :size="18" class="sidebar-lucide-icon" />
            </template>
            <v-list-item-title class="dashboard-nav-item__title">
              {{ itemTitle }}
            </v-list-item-title>
          </v-list-item>
        </template>
      </v-tooltip>
      <v-list-item v-else v-bind="groupProps" rounded class="dashboard-nav-item" color="secondary"
        :style="{ '--indent-padding': '0px' }">
        <template #prepend>
          <v-icon v-if="isVuetifyIcon" :icon="item.icon" size="18" />
          <component :is="item.icon" v-else-if="item.icon" :size="18" class="sidebar-lucide-icon" />
        </template>
        <v-list-item-title class="dashboard-nav-item__title">
          {{ itemTitle }}
        </v-list-item-title>
      </v-list-item>
    </template>

    <!-- children -->
    <template v-for="(child, index) in item.children" :key="child.title || child.to || `child-${index}`">
      <NavItem
        :item="child"
        :level="(level || 0) + 1"
        :rail="rail"
        :pinnable="pinnable"
        :pinned-tos="pinnedTos"
        @toggle-pin="(i) => emit('togglePin', i)"
      />
    </template>
  </v-list-group>

  <v-tooltip
    v-else-if="rail"
    location="right"
    :text="itemTitle"
    :open-delay="0"
    content-class="sidebar-rail-tooltip"
  >
    <template v-slot:activator="{ props: tooltipProps }">
      <v-list-item v-bind="tooltipProps" :to="item.type === 'external' ? '' : item.to"
        :href="item.type === 'external' ? item.to : ''" :active="isItemActive" rounded class="dashboard-nav-item"
        color="secondary" :disabled="item.disabled" :target="item.type === 'external' ? '_blank' : ''"
        :style="itemStyle" :aria-label="itemTitle">
        <template v-slot:prepend>
          <v-icon v-if="item.icon && isVuetifyIcon" size="18" class="hide-menu" :icon="item.icon" />
          <component :is="item.icon" v-else-if="item.icon" :size="18" class="sidebar-lucide-icon hide-menu" />
        </template>
        <v-list-item-title class="dashboard-nav-item__title">{{ itemTitle }}</v-list-item-title>
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

  <v-tooltip
    v-else
    :disabled="!item.pluginInfo"
    location="right"
    :open-delay="0"
    content-class="plugin-page-hover-card"
  >
    <template v-slot:activator="{ props: tooltipProps }">
      <v-list-item v-bind="tooltipProps" :to="item.type === 'external' ? '' : item.to" :href="item.type === 'external' ? item.to : ''"
        :active="isItemActive" rounded class="dashboard-nav-item" color="secondary" :disabled="item.disabled"
        :target="item.type === 'external' ? '_blank' : ''" :style="itemStyle">
        <template v-slot:prepend>
          <v-icon v-if="item.icon && isVuetifyIcon" size="18" class="hide-menu" :icon="item.icon" />
          <component :is="item.icon" v-else-if="item.icon" :size="18" class="sidebar-lucide-icon hide-menu" />
        </template>
        <v-list-item-title class="dashboard-nav-item__title">{{ itemTitle }}</v-list-item-title>
        <v-list-item-subtitle v-if="item.subCaption" class="text-caption mt-n1 hide-menu">
          {{ item.subCaption }}
        </v-list-item-subtitle>
        <template v-slot:append v-if="item.chip || (pinnable && !rail)">
          <v-chip :color="item.chipColor" class="sidebarchip hide-menu" :size="item.chipIcon ? 'small' : 'default'"
            :variant="item.chipVariant" :prepend-icon="item.chipIcon" v-if="item.chip">
            {{ item.chip }}
          </v-chip>
          <button
            v-if="pinnable && !rail"
            type="button"
            class="nav-item-pin"
            :class="{ 'nav-item-pin--active': isPinned }"
            :aria-label="isPinned ? t('core.navigation.unpin') : t('core.navigation.pin')"
            @click.prevent.stop="emit('togglePin', item)"
          >
            <PinOff v-if="isPinned" :size="14" />
            <Pin v-else :size="14" />
          </button>
        </template>
      </v-list-item>
    </template>
    <div v-if="item.pluginInfo" class="plugin-hover-card">
      <div class="plugin-hover-card__title">{{ itemTitle }}</div>
      <div class="plugin-hover-card__row">
        <Puzzle :size="13" class="plugin-hover-card__icon" />
        <template v-if="pluginDisplayName">
          <span class="plugin-hover-card__name">{{ pluginDisplayName }}</span>
          <span class="plugin-hover-card__id">({{ item.pluginInfo.id }})</span>
        </template>
        <span v-else class="plugin-hover-card__id">{{ item.pluginInfo.id }}</span>
      </div>
      <div v-if="item.pluginInfo.author" class="plugin-hover-card__row">
        <User :size="13" class="plugin-hover-card__icon" />
        <span>{{ item.pluginInfo.author }}</span>
      </div>
      <div class="plugin-hover-card__row">
        <AppWindow :size="13" class="plugin-hover-card__icon" />
        <span>{{ t('core.navigation.pluginViewType') }}</span>
      </div>
    </div>
  </v-tooltip>
</template>

<style>
.dashboard-nav-item__title {
  font-size: 14px;
  font-weight: 500;
  line-height: 20px;
  word-break: break-word;
}

.sidebar-lucide-icon {
  flex: 0 0 auto;
  color: currentcolor;
  stroke-width: 2;
}

.v-tooltip .v-overlay__content.plugin-page-hover-card {
  padding: 10px 14px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  border-radius: 12px;
  background: rgb(var(--v-theme-surface));
  box-shadow:
    0 8px 24px rgba(0, 0, 0, 0.12),
    0 2px 6px rgba(0, 0, 0, 0.08);
  color: rgb(var(--v-theme-on-surface));
  opacity: 1 !important;
  transition: none !important;
}

.plugin-hover-card__title {
  font-size: 14px;
  font-weight: 600;
  line-height: 20px;
}

.plugin-hover-card__row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 4px;
  color: rgba(var(--v-theme-on-surface), 0.65);
  font-size: 12px;
  line-height: 16px;
}

.plugin-hover-card__icon {
  flex: 0 0 auto;
  color: rgba(var(--v-theme-on-surface), 0.45);
}

.plugin-hover-card__name {
  color: rgb(var(--v-theme-on-surface));
  font-weight: 500;
}

.plugin-hover-card__id {
  color: rgba(var(--v-theme-on-surface), 0.55);
  font-family: monospace;
}

.nav-item-pin {
  display: grid;
  place-items: center;
  padding: 2px;
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: rgba(var(--v-theme-on-surface), 0.45);
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.15s ease;
}

.dashboard-nav-item:hover .nav-item-pin,
.nav-item-pin:focus-visible {
  opacity: 1;
}

.nav-item-pin:hover {
  color: rgba(var(--v-theme-on-surface), 0.85);
}

.nav-item-pin--active {
  color: rgb(var(--v-theme-primary));
  opacity: 1;
}

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
