<script setup>
import { computed, ref } from "vue";
import { useI18n, useModuleI18n } from "@/i18n/composables";
import PersonaCapabilityList from "./PersonaCapabilityList.vue";

const props = defineProps({
  tools: { type: Array, default: null },
  skills: { type: Array, default: null },
  availableTools: { type: Array, default: null },
  availableSkills: { type: Array, default: null },
  readonly: Boolean,
  saving: { type: String, default: "" },
  error: { type: String, default: "" },
  loadingTools: Boolean,
  loadingSkills: Boolean,
  updateCapability: { type: Function, default: null },
});

const emit = defineEmits(["update:tools", "update:skills"]);
const { t } = useI18n();
const { tm } = useModuleI18n("core.shared");
const fields = ["tools", "skills"];
const selectionDialog = ref(null);
const upgradeDialog = ref(false);
const decisions = ref({});
const removed = ref([]);
const conflict = ref("");
const removeChoice = "remove";
const sourceLabels = computed(() => ({
  mcp: "MCP",
  plugin: tm("personaQuickPreview.pluginSource"),
  local: tm("personaQuickPreview.localSource"),
  sandbox: tm("personaQuickPreview.presetSource"),
}));
const catalog = computed(() => ({
  tools: (props.availableTools ?? [])
    .filter((tool) => ["plugin", "mcp"].includes(tool.origin) && tool.resource)
    .map((tool) => ({
      ...tool,
      ...tool.resource,
      legacyName: tool.name,
      kind: "tool",
      label: tool.origin_display_name || tool.origin_name,
    })),
  skills: (props.availableSkills ?? [])
    .filter((skill) => skill.resource)
    .map((skill) => ({
      ...skill,
      ...skill.resource,
      legacyName: skill.name,
      kind: "skill",
      active: skill.active !== false && skill.plugin_active !== false,
      label:
        skill.plugin_display_name ||
        skill.plugin_name ||
        sourceLabels.value[skill.resource.source],
    })),
}));

function sameSource(group, item) {
  return (
    group.kind === item.kind &&
    group.source === item.source &&
    (group.source_id ?? null) === (item.source_id ?? null)
  );
}

function matches(field, name) {
  return catalog.value[field].filter((item) => item.legacyName === name);
}

function defaultItems(field) {
  const winners = new Map();
  for (const item of catalog.value[field]) {
    if (item.active === false) continue;
    if (field === "tools" || !winners.has(item.legacyName)) {
      winners.set(item.legacyName, item);
    }
  }
  return [...winners.values()];
}

function selected(field, item, value = props[field]) {
  if (value === null)
    return defaultItems(field).some((candidate) => candidate.key === item.key);
  return (value || []).some((entry) =>
    typeof entry === "string"
      ? entry === item.legacyName && matches(field, entry).length === 1
      : sameSource(entry, item) && entry.items.includes(item.name),
  );
}

function addItem(value, item) {
  const { kind, source, source_id, name } = item;
  const index = value.findIndex(
    (entry) => typeof entry !== "string" && sameSource(entry, item),
  );
  if (index === -1) {
    value.push({ kind, source, source_id: source_id ?? null, items: [name] });
  } else if (!value[index].items.includes(name)) {
    value[index] = { ...value[index], items: [...value[index].items, name] };
  }
}

function removeItem(value, item) {
  return value.flatMap((entry) => {
    if (typeof entry === "string" || !sameSource(entry, item)) return [entry];
    const items = entry.items.filter((name) => name !== item.name);
    return items.length ? [{ ...entry, items }] : [];
  });
}

function editItems(field, targets, isSelected) {
  let value = [...(props[field] || [])];
  if (props[field] === null)
    defaultItems(field).forEach((item) => addItem(value, item));
  for (const item of targets) {
    if (isSelected(item)) {
      if (!selected(field, item, value)) addItem(value, item);
    } else {
      value = removeItem(value, item);
      if (matches(field, item.legacyName).length === 1) {
        value = value.filter((entry) => entry !== item.legacyName);
      }
    }
  }
  return value;
}

async function applySelection(field, value) {
  if (props.readonly || props.saving) return false;
  conflict.value = "";
  const tools =
    field === "all" ? value.tools : field === "tools" ? value : props.tools;
  const selectedNames = new Map();
  for (const item of catalog.value.tools) {
    if (tools !== null && selected("tools", item, tools)) {
      if (
        selectedNames.has(item.legacyName) &&
        selectedNames.get(item.legacyName) !== item.key
      ) {
        conflict.value = item.legacyName;
        return false;
      }
      selectedNames.set(item.legacyName, item.key);
    }
  }
  if (props.updateCapability) {
    const previous =
      field === "all"
        ? { tools: props.tools, skills: props.skills }
        : props[field];
    return (await props.updateCapability(field, value, previous)) !== false;
  }
  if (field === "all") {
    emit("update:tools", value.tools);
    emit("update:skills", value.skills);
  } else {
    emit(field === "tools" ? "update:tools" : "update:skills", value);
  }
  return true;
}

const groups = computed(() =>
  Object.fromEntries(
    fields.map((field) => {
      const sources = new Map();
      for (const item of catalog.value[field]) {
        const individual = field === "skills" && item.source !== "plugin";
        const key = individual
          ? item.key
          : JSON.stringify([item.source, item.source_id]);
        if (!sources.has(key))
          sources.set(key, {
            key,
            name: individual ? item.name : item.label,
            items: [],
            individual,
          });
        sources.get(key).items.push(item);
      }
      return [
        field,
        [...sources.values()].map((group) => {
          const eligible = group.items.filter((item) => item.active !== false);
          const count = eligible.filter((item) => selected(field, item)).length;
          const item = group.items[0];
          return {
            ...group,
            eligible,
            selected: eligible.length > 0 && count === eligible.length,
            indeterminate: count > 0 && count < eligible.length,
            disabled: eligible.length === 0,
            configurable: !group.individual && eligible.length > 0,
            description: group.individual ? item.description : "",
            badge: sourceLabels.value[item.source],
            meta: group.individual
              ? ""
              : tm(
                  `personaQuickPreview.${
                    field === "tools" ? "toolCount" : "skillCount"
                  }`,
                  { selected: count, total: eligible.length },
                ),
          };
        }),
      ];
    }),
  ),
);

function toggle(field, candidates) {
  if (!candidates.length) return;
  const turnOn = !candidates.every((item) => selected(field, item));
  return applySelection(
    field,
    editItems(field, candidates, () => turnOn),
  );
}

function toggleAll(field) {
  const candidates = groups.value[field].flatMap((group) => group.eligible);
  if (
    candidates.some((item) => !selected(field, item)) &&
    !unavailable.value.some((row) => row.field === field) &&
    !removed.value.some((row) => row.field === field)
  ) {
    return applySelection(field, null);
  }
  return toggle(field, candidates);
}

function toggleAllInDialog() {
  const { eligible } = selectionDialog.value.group;
  const keys = selectionDialog.value.keys;
  if (eligible.every((item) => keys.includes(item.key))) {
    selectionDialog.value.keys = keys.filter(
      (key) => !eligible.some((item) => item.key === key),
    );
  } else {
    selectionDialog.value.keys = [
      ...new Set([...keys, ...eligible.map((item) => item.key)]),
    ];
  }
}

function openSelection(field, group) {
  selectionDialog.value = {
    field,
    group,
    keys: group.items
      .filter((item) => selected(field, item))
      .map((item) => item.key),
  };
}

const legacy = computed(() =>
  fields.flatMap((field) =>
    [
      ...new Set(
        (props[field] || []).filter((entry) => typeof entry === "string"),
      ),
    ].map((name) => {
      const candidates = matches(field, name);
      return { field, name, id: JSON.stringify([field, name]), candidates };
    }),
  ),
);

const canPreviewUpgrade = computed(() =>
  legacy.value.every(({ field }) =>
    field === "tools"
      ? props.availableTools !== null && !props.loadingTools
      : props.availableSkills !== null && !props.loadingSkills,
  ),
);
const matchedLegacy = computed(() =>
  legacy.value.filter((row) => row.candidates.length > 0),
);

const unavailable = computed(() =>
  fields.flatMap((field) =>
    (props[field] || []).flatMap((entry) => {
      if (typeof entry === "string") {
        const candidates = matches(field, entry);
        if (candidates.length === 1 && candidates[0].active !== false)
          return [];
        return [
          {
            field,
            name: entry,
            label: entry,
            id: JSON.stringify([field, entry]),
          },
        ];
      }
      return entry.items.flatMap((name) => {
        if (
          catalog.value[field].some(
            (item) =>
              sameSource(entry, item) &&
              item.name === name &&
              item.active !== false,
          )
        )
          return [];
        const item = { ...entry, name };
        const source = catalog.value[field].find((item) =>
          sameSource(entry, item),
        );
        return [
          {
            field,
            item,
            label: [
              source?.label || entry.source_id || entry.source,
              name,
            ].join(" / "),
            id: JSON.stringify([field, entry.source, entry.source_id, name]),
          },
        ];
      });
    }),
  ),
);

const unavailableByField = computed(() =>
  Object.fromEntries(
    fields.map((field) => [
      field,
      [...unavailable.value, ...removed.value].filter(
        (row) => row.field === field,
      ),
    ]),
  ),
);

async function toggleUnavailable(row) {
  const wasRemoved = removed.value.some((item) => item.id === row.id);
  let value = [...(props[row.field] || [])];
  if (wasRemoved) {
    if (row.item) addItem(value, row.item);
    else if (!value.includes(row.name)) value.push(row.name);
  } else if (row.item) {
    value = removeItem(value, row.item);
  } else {
    value = value.filter((entry) => entry !== row.name);
  }
  if (await applySelection(row.field, value)) {
    removed.value = wasRemoved
      ? removed.value.filter((item) => item.id !== row.id)
      : [...removed.value, row];
  }
}

function openUpgrade() {
  decisions.value = Object.fromEntries(
    matchedLegacy.value.map(({ id, candidates }) => [
      id,
      candidates.length === 1 ? candidates[0].key : null,
    ]),
  );
  upgradeDialog.value = true;
}

const upgraded = computed(() => {
  const value = Object.fromEntries(
    fields.map((field) => [
      field,
      props[field]?.filter((entry) => typeof entry !== "string") ?? null,
    ]),
  );
  for (const { id, field, candidates } of matchedLegacy.value) {
    const item = candidates.find((item) => item.key === decisions.value[id]);
    if (item) addItem(value[field], item);
  }
  return value;
});

const upgradeReady = computed(
  () =>
    legacy.value.length > 0 &&
    canPreviewUpgrade.value &&
    matchedLegacy.value.every(
      ({ id, candidates }) =>
        decisions.value[id] === removeChoice ||
        candidates.some((item) => item.key === decisions.value[id]),
    ),
);
</script>

<template>
  <div class="persona-capabilities-editor">
    <v-alert v-if="legacy.length" type="info" density="compact" variant="tonal">
      {{ tm("personaQuickPreview.legacySelection") }}
      <template v-if="!readonly" #append>
        <v-btn
          variant="text"
          :disabled="Boolean(saving) || !canPreviewUpgrade"
          @click="openUpgrade"
        >
          {{ tm("personaQuickPreview.previewUpgrade") }}
        </v-btn>
      </template>
    </v-alert>
    <v-alert v-if="conflict" type="warning" density="compact" variant="tonal">
      {{ tm("personaQuickPreview.nameConflict", { name: conflict }) }}
    </v-alert>

    <template v-for="field in fields" :key="field">
      <PersonaCapabilityList
        :title="
          tm(
            field === 'tools'
              ? 'personaQuickPreview.toolsLabel'
              : 'personaQuickPreview.skillsLabel',
          )
        "
        :icon="field === 'tools' ? 'mdi-tools' : 'mdi-lightning-bolt'"
        :items="groups[field]"
        :empty-text="
          tm(
            field === 'tools'
              ? 'personaQuickPreview.noToolsAvailable'
              : 'personaQuickPreview.noSkills',
          )
        "
        :inactive-text="
          tm(
            field === 'tools'
              ? 'personaQuickPreview.toolInactive'
              : 'personaQuickPreview.skillInactive',
          )
        "
        :configure-text="
          tm(
            field === 'tools'
              ? 'personaQuickPreview.configureTools'
              : 'personaQuickPreview.configureSkills',
          )
        "
        :readonly="readonly"
        :saving="Boolean(saving)"
        :loading="field === 'tools' ? loadingTools : loadingSkills"
        @toggle="toggle(field, $event.eligible)"
        @toggle-all="toggleAll(field)"
        @configure="openSelection(field, $event)"
      />
      <v-sheet
        v-if="
          !(field === 'tools' ? loadingTools : loadingSkills) &&
          unavailableByField[field].length
        "
        border
        rounded="lg"
        class="pa-3"
      >
        <div class="text-subtitle-2 mb-1">
          {{
            tm(
              field === "tools"
                ? "personaQuickPreview.unlistedSavedTools"
                : "personaQuickPreview.unlistedSavedSkills",
            )
          }}
        </div>
        <div
          v-for="row in unavailableByField[field]"
          :key="row.id"
          class="d-flex align-center justify-space-between ga-2"
        >
          <span
            class="text-break"
            :class="{
              'text-decoration-line-through': removed.some(
                (item) => item.id === row.id,
              ),
            }"
            >{{ row.label }}</span
          >
          <v-btn
            v-if="!readonly"
            type="button"
            variant="text"
            size="small"
            :disabled="Boolean(saving)"
            @click="toggleUnavailable(row)"
          >
            {{
              tm(
                removed.some((item) => item.id === row.id)
                  ? "personaQuickPreview.undoToolRemoval"
                  : "personaQuickPreview.removeSavedTool",
              )
            }}
          </v-btn>
        </div>
      </v-sheet>
    </template>

    <v-dialog
      :model-value="Boolean(selectionDialog)"
      max-width="640"
      scrollable
      :persistent="Boolean(saving)"
      @update:model-value="!$event && (selectionDialog = null)"
    >
      <v-card v-if="selectionDialog">
        <v-card-title class="text-h3 pa-4 pb-0 pl-6">{{
          selectionDialog.group.name
        }}</v-card-title>
        <v-card-text class="pa-6">
          <v-alert
            v-if="conflict"
            type="warning"
            variant="tonal"
            density="compact"
            class="mb-3"
          >
            {{ tm("personaQuickPreview.nameConflict", { name: conflict }) }}
          </v-alert>
          <v-alert
            v-if="error"
            type="error"
            variant="tonal"
            density="compact"
            class="mb-3"
            >{{ error }}</v-alert
          >
          <v-btn
            variant="text"
            size="small"
            :disabled="Boolean(saving)"
            @click="toggleAllInDialog"
          >
            {{
              tm(
                selectionDialog.field === "tools"
                  ? "personaQuickPreview.selectAllTools"
                  : "personaQuickPreview.selectAllSkills",
              )
            }}
          </v-btn>
          <v-list density="compact">
            <v-list-item
              v-for="item in selectionDialog.group.items"
              :key="item.key"
              :subtitle="item.description"
            >
              <template #prepend>
                <v-checkbox-btn
                  :model-value="selectionDialog.keys.includes(item.key)"
                  :disabled="item.active === false || Boolean(saving)"
                  :aria-label="item.name"
                  @update:model-value="
                    $event
                      ? selectionDialog.keys.push(item.key)
                      : (selectionDialog.keys = selectionDialog.keys.filter(
                          (key) => key !== item.key,
                        ))
                  "
                />
              </template>
              <v-list-item-title>{{ item.name }}</v-list-item-title>
            </v-list-item>
          </v-list>
        </v-card-text>
        <v-card-actions class="justify-end px-6 pb-4">
          <v-btn
            variant="text"
            :disabled="Boolean(saving)"
            @click="selectionDialog = null"
            >{{ t("core.common.cancel") }}</v-btn
          >
          <v-btn
            color="primary"
            variant="tonal"
            :loading="Boolean(saving)"
            @click="
              async () => {
                if (
                  await applySelection(
                    selectionDialog.field,
                    editItems(
                      selectionDialog.field,
                      selectionDialog.group.eligible,
                      (item) => selectionDialog.keys.includes(item.key),
                    ),
                  )
                )
                  selectionDialog = null;
              }
            "
          >
            {{ t("core.common.save") }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog
      v-model="upgradeDialog"
      max-width="640"
      scrollable
      :persistent="Boolean(saving)"
    >
      <v-card>
        <v-card-title class="text-h3 pa-4 pb-0 pl-6">{{
          tm("personaQuickPreview.previewUpgrade")
        }}</v-card-title>
        <v-card-text class="pa-6">
          <p class="mb-4">{{ tm("personaQuickPreview.upgradeHelp") }}</p>
          <v-alert
            v-if="conflict"
            type="warning"
            variant="tonal"
            density="compact"
            class="mb-3"
          >
            {{ tm("personaQuickPreview.nameConflict", { name: conflict }) }}
          </v-alert>
          <v-alert
            v-if="error"
            type="error"
            variant="tonal"
            density="compact"
            class="mb-3"
            >{{ error }}</v-alert
          >
          <template v-for="field in fields" :key="field">
            <h3 class="text-subtitle-1 mb-2">
              {{
                tm(
                  field === "tools"
                    ? "personaQuickPreview.toolsLabel"
                    : "personaQuickPreview.skillsLabel",
                )
              }}
            </h3>
            <v-select
              v-for="row in matchedLegacy.filter(
                (entry) => entry.field === field,
              )"
              :key="row.id"
              v-model="decisions[row.id]"
              :label="row.name"
              density="compact"
              variant="outlined"
              :items="[
                ...row.candidates.map((item) => ({
                  title: [item.source, item.label || item.source_id, item.name]
                    .filter(Boolean)
                    .join(' / '),
                  value: item.key,
                })),
                {
                  title: tm('personaQuickPreview.removeSavedTool'),
                  value: removeChoice,
                },
              ]"
              :hint="
                tm(
                  row.candidates.length === 1
                    ? 'personaQuickPreview.currentMatch'
                    : 'personaQuickPreview.chooseSource',
                )
              "
              persistent-hint
              class="mb-3"
            />
            <div
              v-for="group in upgraded[field]"
              :key="JSON.stringify([group.source, group.source_id])"
              class="mb-3"
            >
              <div class="text-body-2 font-weight-medium">
                {{
                  [
                    group.source,
                    catalog[field].find((item) => sameSource(group, item))
                      ?.label,
                    group.source_id,
                  ]
                    .filter(Boolean)
                    .join(" / ")
                }}
              </div>
              <div class="text-body-2 text-medium-emphasis">
                {{ group.items.join(", ") }}
              </div>
            </div>
          </template>
        </v-card-text>
        <v-card-actions class="justify-end px-6 pb-4">
          <v-btn
            variant="text"
            :disabled="Boolean(saving)"
            @click="upgradeDialog = false"
            >{{ t("core.common.cancel") }}</v-btn
          >
          <v-btn
            color="primary"
            variant="tonal"
            :disabled="!upgradeReady"
            :loading="Boolean(saving)"
            @click="
              async () => {
                if (await applySelection('all', upgraded))
                  upgradeDialog = false;
              }
            "
          >
            {{
              tm(
                updateCapability
                  ? "personaQuickPreview.saveUpgrade"
                  : "personaQuickPreview.applyUpgrade",
              )
            }}
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
</style>
