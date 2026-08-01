<script setup>
import { computed, ref } from "vue";
import { useI18n, useModuleI18n } from "@/i18n/composables";
import PersonaCapabilityList from "./PersonaCapabilityList.vue";

const props = defineProps({
  tools: {
    type: [Array, null],
    default: null,
  },
  skills: {
    type: [Array, null],
    default: null,
  },
  availableTools: {
    type: Array,
    default: () => [],
  },
  availableSkills: {
    type: Array,
    default: () => [],
  },
  readonly: {
    type: Boolean,
    default: false,
  },
  saving: {
    type: String,
    default: "",
  },
  error: {
    type: String,
    default: "",
  },
  loadingTools: {
    type: Boolean,
    default: false,
  },
  loadingSkills: {
    type: Boolean,
    default: false,
  },
  updateCapability: {
    type: Function,
    default: null,
  },
});

const emit = defineEmits(["update:tools", "update:skills"]);
const { t } = useI18n();
const { tm } = useModuleI18n("core.shared");

const selectionDialog = ref({
  show: false,
  field: "tools",
  name: "",
  titleKey: "personaQuickPreview.toolDialogTitle",
  hintKey: "personaQuickPreview.toolDialogHint",
  selectAllKey: "personaQuickPreview.selectAllTools",
  inactiveKey: "personaQuickPreview.toolInactive",
  items: [],
  selectedNames: [],
});

const selectableTools = computed(() =>
  props.availableTools.filter((tool) => tool.origin !== "builtin"),
);
const selectableToolNames = computed(() =>
  selectableTools.value
    .filter((tool) => tool.active !== false)
    .map((tool) => tool.name),
);
const selectableSkillNames = computed(() =>
  props.availableSkills
    .filter((skill) => skill.active !== false)
    .map((skill) => skill.name),
);

function isCapabilitySelected(field, name) {
  const configured = props[field];
  return (
    configured === null ||
    (Array.isArray(configured) && configured.includes(name))
  );
}

const toolGroups = computed(() => {
  const groups = new Map();
  for (const tool of selectableTools.value) {
    if (tool.origin !== "mcp" && tool.origin !== "plugin") {
      continue;
    }
    const sourceId =
      tool.origin_name || tm("personaQuickPreview.unknownSource");
    const sourceName = tool.origin_display_name || sourceId;
    const key = `${tool.origin}:${sourceId}`;
    if (!groups.has(key)) {
      groups.set(key, {
        key,
        name: sourceName,
        origin: tool.origin,
        tools: [],
      });
    }
    groups.get(key).tools.push(tool);
  }

  return [...groups.values()].map((group) => {
    const activeTools = group.tools.filter((tool) => tool.active !== false);
    const selectedCount = activeTools.filter((tool) =>
      isCapabilitySelected("tools", tool.name),
    ).length;
    return {
      ...group,
      badge:
        group.origin === "mcp" ? "MCP" : tm("personaQuickPreview.pluginSource"),
      badgeTone: group.origin === "mcp" ? "mcp" : "plugin",
      meta: tm("personaQuickPreview.toolCount", {
        selected: selectedCount,
        total: activeTools.length,
      }),
      selected: activeTools.length > 0 && selectedCount === activeTools.length,
      indeterminate: selectedCount > 0 && selectedCount < activeTools.length,
      disabled: activeTools.length === 0,
      configurable: activeTools.length > 0,
      toolNames: activeTools.map((tool) => tool.name),
    };
  });
});

const skillItems = computed(() => {
  const items = [];
  const pluginGroups = new Map();

  for (const skill of props.availableSkills) {
    if (skill.active === false) {
      continue;
    }
    if (skill.source_type === "plugin") {
      const sourceId =
        skill.plugin_name ||
        skill.source_label ||
        tm("personaQuickPreview.unknownSource");
      const sourceName =
        skill.plugin_display_name || skill.source_label || sourceId;
      const key = `plugin:${sourceId}`;
      if (!pluginGroups.has(key)) {
        const group = {
          key,
          name: sourceName,
          skills: [],
        };
        pluginGroups.set(key, group);
        items.push(group);
      }
      pluginGroups.get(key).skills.push(skill);
      continue;
    }

    let badge = tm("personaQuickPreview.localSource");
    let badgeTone = "local";
    if (skill.source_type === "sandbox_only") {
      badge = tm("personaQuickPreview.presetSource");
      badgeTone = "preset";
    } else if (skill.source_type === "both") {
      badge = tm("personaQuickPreview.localAndSandboxSource");
      badgeTone = "mixed";
    }
    items.push({
      key: `skill:${skill.name}`,
      name: skill.name,
      description: skill.description || "",
      meta: "",
      badge,
      badgeTone,
      selected: isCapabilitySelected("skills", skill.name),
      disabled: false,
    });
  }

  return items.map((item) => {
    if (!item.skills) {
      return item;
    }
    const selectedCount = item.skills.filter((skill) =>
      isCapabilitySelected("skills", skill.name),
    ).length;
    return {
      ...item,
      badge: tm("personaQuickPreview.pluginSource"),
      badgeTone: "plugin",
      meta: tm("personaQuickPreview.skillCount", {
        selected: selectedCount,
        total: item.skills.length,
      }),
      selected: item.skills.length > 0 && selectedCount === item.skills.length,
      indeterminate: selectedCount > 0 && selectedCount < item.skills.length,
      disabled: item.skills.length === 0,
      configurable: true,
      skillNames: item.skills.map((skill) => skill.name),
    };
  });
});

const dialogSelectableItems = computed(() =>
  selectionDialog.value.items.filter((item) => item.active !== false),
);
const dialogSelectedCount = computed(
  () =>
    dialogSelectableItems.value.filter((item) =>
      selectionDialog.value.selectedNames.includes(item.name),
    ).length,
);
const dialogAllSelected = computed(
  () =>
    dialogSelectableItems.value.length > 0 &&
    dialogSelectedCount.value === dialogSelectableItems.value.length,
);
const dialogPartiallySelected = computed(
  () => dialogSelectedCount.value > 0 && !dialogAllSelected.value,
);

async function applyCapabilityUpdate(field, nextValue, previousValue) {
  if (props.readonly || props.saving) {
    return false;
  }
  if (props.updateCapability) {
    return (
      (await props.updateCapability(field, nextValue, previousValue)) !== false
    );
  }
  emit(field === "tools" ? "update:tools" : "update:skills", nextValue);
  return true;
}

async function toggleCapabilities(field, names, toggleGroup = false) {
  if (props.readonly || props.saving || names.length === 0) {
    return;
  }

  const availableNames =
    field === "tools" ? selectableToolNames.value : selectableSkillNames.value;
  const previousValue = props[field];
  const selectedNames =
    previousValue === null
      ? [...availableNames]
      : [...(Array.isArray(previousValue) ? previousValue : [])];
  const allTargetsSelected = names.every((name) =>
    selectedNames.includes(name),
  );

  if (toggleGroup && !allTargetsSelected) {
    for (const name of names) {
      if (!selectedNames.includes(name)) {
        selectedNames.push(name);
      }
    }
  } else {
    for (const name of names) {
      const index = selectedNames.indexOf(name);
      if (index === -1) {
        selectedNames.push(name);
      } else {
        selectedNames.splice(index, 1);
      }
    }
  }

  const nextValue =
    availableNames.length > 0 &&
    availableNames.every((name) => selectedNames.includes(name))
      ? null
      : selectedNames;
  await applyCapabilityUpdate(field, nextValue, previousValue);
}

function openSelectionDialog(field, group, items) {
  if (props.readonly || props.saving || !items?.length) {
    return;
  }
  const isToolDialog = field === "tools";
  selectionDialog.value = {
    show: true,
    field,
    name: group.name,
    titleKey: isToolDialog
      ? "personaQuickPreview.toolDialogTitle"
      : "personaQuickPreview.skillDialogTitle",
    hintKey: isToolDialog
      ? "personaQuickPreview.toolDialogHint"
      : "personaQuickPreview.skillDialogHint",
    selectAllKey: isToolDialog
      ? "personaQuickPreview.selectAllTools"
      : "personaQuickPreview.selectAllSkills",
    inactiveKey: isToolDialog
      ? "personaQuickPreview.toolInactive"
      : "personaQuickPreview.skillInactive",
    items,
    selectedNames: items
      .filter((item) => isCapabilitySelected(field, item.name))
      .map((item) => item.name),
  };
}

function closeSelectionDialog() {
  if (!props.saving) {
    selectionDialog.value.show = false;
  }
}

function toggleDialogItem(itemName) {
  const item = selectionDialog.value.items.find(
    (candidate) => candidate.name === itemName,
  );
  if (!item || item.active === false || props.saving) {
    return;
  }
  const selectedNames = [...selectionDialog.value.selectedNames];
  const index = selectedNames.indexOf(itemName);
  if (index === -1) {
    selectedNames.push(itemName);
  } else {
    selectedNames.splice(index, 1);
  }
  selectionDialog.value.selectedNames = selectedNames;
}

function toggleAllDialogItems() {
  if (props.saving || dialogSelectableItems.value.length === 0) {
    return;
  }
  const selectableNames = dialogSelectableItems.value.map((item) => item.name);
  if (dialogAllSelected.value) {
    selectionDialog.value.selectedNames =
      selectionDialog.value.selectedNames.filter(
        (name) => !selectableNames.includes(name),
      );
  } else {
    selectionDialog.value.selectedNames = [
      ...new Set([...selectionDialog.value.selectedNames, ...selectableNames]),
    ];
  }
}

async function saveSelectionDialog() {
  if (props.readonly || props.saving) {
    return;
  }
  const field = selectionDialog.value.field;
  const availableNames =
    field === "tools" ? selectableToolNames.value : selectableSkillNames.value;
  const previousValue = props[field];
  const selectedNames =
    previousValue === null
      ? [...availableNames]
      : [...(Array.isArray(previousValue) ? previousValue : [])];
  const dialogItemNames = selectionDialog.value.items.map((item) => item.name);
  const nextSelectedNames = selectedNames.filter(
    (name) => !dialogItemNames.includes(name),
  );
  nextSelectedNames.push(...selectionDialog.value.selectedNames);
  const nextValue = availableNames.every((name) =>
    nextSelectedNames.includes(name),
  )
    ? null
    : [...new Set(nextSelectedNames)];
  if (await applyCapabilityUpdate(field, nextValue, previousValue)) {
    selectionDialog.value.show = false;
  }
}
</script>

<template>
  <div class="persona-capabilities-editor">
    <PersonaCapabilityList
      :title="tm('personaQuickPreview.toolsLabel')"
      icon="mdi-tools"
      :items="toolGroups"
      :empty-text="tm('personaQuickPreview.noToolsAvailable')"
      :inactive-text="tm('personaQuickPreview.toolInactive')"
      :configure-text="tm('personaQuickPreview.configureTools')"
      :readonly="readonly"
      :saving="Boolean(saving)"
      :loading="loadingTools"
      @toggle="toggleCapabilities('tools', $event.toolNames, true)"
      @toggle-all="
        toggleCapabilities(
          'tools',
          toolGroups.flatMap((item) => item.toolNames),
          true,
        )
      "
      @configure="openSelectionDialog('tools', $event, $event.tools)"
    />

    <PersonaCapabilityList
      :title="tm('personaQuickPreview.skillsLabel')"
      icon="mdi-lightning-bolt"
      :items="skillItems"
      :empty-text="tm('personaQuickPreview.noSkills')"
      :inactive-text="tm('personaQuickPreview.skillInactive')"
      :configure-text="tm('personaQuickPreview.configureSkills')"
      :readonly="readonly"
      :saving="Boolean(saving)"
      :loading="loadingSkills"
      @toggle="
        toggleCapabilities(
          'skills',
          $event.skillNames || [$event.name],
          Boolean($event.skillNames),
        )
      "
      @toggle-all="
        toggleCapabilities(
          'skills',
          skillItems.flatMap((item) => item.skillNames || [item.name]),
          true,
        )
      "
      @configure="openSelectionDialog('skills', $event, $event.skills)"
    />

    <v-dialog
      v-model="selectionDialog.show"
      max-width="640"
      scrollable
      :persistent="Boolean(saving)"
    >
      <v-card>
        <v-card-title class="text-h3 pa-4 pb-0 pl-6">
          {{ tm(selectionDialog.titleKey, { name: selectionDialog.name }) }}
        </v-card-title>
        <v-card-text class="pa-6">
          <div class="capability-dialog__hint">
            {{ tm(selectionDialog.hintKey) }}
          </div>

          <v-alert
            v-if="error"
            type="error"
            variant="tonal"
            density="compact"
            class="mb-3"
          >
            {{ tm("personaQuickPreview.saveFailed", { message: error }) }}
          </v-alert>

          <div class="capability-dialog__select-all">
            <v-checkbox-btn
              :model-value="dialogAllSelected"
              :indeterminate="dialogPartiallySelected"
              :disabled="dialogSelectableItems.length === 0"
              :aria-label="tm(selectionDialog.selectAllKey)"
              density="compact"
              @click.stop="toggleAllDialogItems"
            />
            <span>{{ tm(selectionDialog.selectAllKey) }}</span>
          </div>

          <v-list class="capability-dialog__list" density="compact">
            <v-list-item
              v-for="item in selectionDialog.items"
              :key="item.name"
              :disabled="item.active === false"
              class="capability-dialog__item"
              @click="toggleDialogItem(item.name)"
            >
              <template #prepend>
                <v-checkbox-btn
                  :model-value="
                    selectionDialog.selectedNames.includes(item.name)
                  "
                  :disabled="item.active === false"
                  :aria-label="item.name"
                  density="compact"
                  @click.stop="toggleDialogItem(item.name)"
                />
              </template>
              <v-list-item-title>{{ item.name }}</v-list-item-title>
              <v-list-item-subtitle v-if="item.description">
                {{ item.description }}
              </v-list-item-subtitle>
              <template v-if="item.active === false" #append>
                <v-chip size="x-small" variant="tonal" color="warning">
                  {{ tm(selectionDialog.inactiveKey) }}
                </v-chip>
              </template>
            </v-list-item>
          </v-list>
        </v-card-text>
        <v-card-actions class="justify-end px-6 pb-4">
          <v-btn
            variant="text"
            :disabled="Boolean(saving)"
            @click="closeSelectionDialog"
          >
            {{ t("core.common.cancel") }}
          </v-btn>
          <v-btn
            color="primary"
            variant="tonal"
            :loading="saving === selectionDialog.field"
            @click="saveSelectionDialog"
          >
            {{ t("core.common.save") }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<style scoped>
.persona-capabilities-editor {
  display: grid;
  min-width: 0;
  gap: 14px;
}

.capability-dialog__hint {
  margin-bottom: 12px;
  color: rgb(var(--v-theme-on-surface));
  font-size: 0.84rem;
  opacity: 0.65;
}

.capability-dialog__select-all {
  display: flex;
  align-items: center;
  min-height: 42px;
  padding: 0 8px;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  font-size: 0.86rem;
}

.capability-dialog__list {
  max-height: min(560px, 60vh);
  overflow-y: auto;
}

.capability-dialog__item {
  min-height: 52px;
  border-radius: 6px;
}
</style>
