<template>
  <v-dialog
    :model-value="modelValue"
    max-width="1000"
    height="760"
    scrollable
    :persistent="busy"
    @update:model-value="!$event && close()"
  >
    <v-card class="mapping-card">
      <v-card-title class="text-h3 pa-4 pb-0 pl-6 d-flex align-center ga-2">
        <v-btn
          v-if="view !== 'list'"
          icon="mdi-arrow-left"
          variant="text"
          size="small"
          :aria-label="tm('back')"
          :disabled="busy"
          @click="back"
        />
        <span>{{
          view === "list"
            ? tm("title")
            : view === "target"
            ? tm("add")
            : tm(destination === "profile" ? "profile" : "overrides")
        }}</span>
        <v-spacer />
        <v-btn
          icon="mdi-close"
          variant="text"
          size="small"
          :aria-label="tm('close')"
          :disabled="busy"
          @click="close"
        />
      </v-card-title>
      <v-card-subtitle
        v-if="view === 'list'"
        class="text-body-2 text-wrap px-6 pt-2"
      >
        {{ tm("description") }}
      </v-card-subtitle>
      <v-card-text
        class="pt-5"
        :class="{ 'mapping-card__split': view === 'target' }"
      >
        <v-alert v-if="error" type="error" variant="tonal" class="mb-4">{{
          error
        }}</v-alert>
        <template v-if="view === 'list'">
          <div class="mapping-list-toolbar">
            <v-text-field
              v-model="search"
              :placeholder="tm('search')"
              :aria-label="tm('search')"
              prepend-inner-icon="mdi-magnify"
              variant="outlined"
              density="compact"
              hide-details
              clearable
            />
            <v-btn
              variant="text"
              :disabled="loading || saving"
              @click="groupDialog = true"
              >{{ tm("groups") }}</v-btn
            >
            <v-btn
              variant="tonal"
              color="primary"
              prepend-icon="mdi-plus"
              :disabled="loading || saving"
              @click="startAdd"
              >{{ tm("add") }}</v-btn
            >
          </div>
          <v-data-table
            :headers="headers"
            :mobile-breakpoint="600"
            :hide-default-header="$vuetify.display.width < 600"
            :items="filteredRows"
            :loading="loading"
            :items-per-page="10"
            :items-per-page-options="[10, 20, 50]"
            :hide-default-footer="filteredRows.length <= 10"
            :items-per-page-text="tm('perPage')"
            :page-text="
              tm('pageText', { start: '{0}', end: '{1}', total: '{2}' })
            "
            :no-data-text="tm('empty')"
            item-value="key"
            class="mapping-table"
          >
            <template #item.target="{ item }">
              <div class="py-3 mapping-target">
                <div>{{ item.display_name || item.target }}</div>
                <div class="text-caption text-medium-emphasis">
                  {{
                    item.target_type === "umop"
                      ? tm("routeOrder", { order: item.order + 1 })
                      : item.target
                  }}
                </div>
              </div>
            </template>
            <template #item.profile="{ item }">
              <v-btn
                variant="text"
                size="small"
                class="mapping-value"
                :disabled="busy"
                @click="edit(item, 'profile')"
                >{{
                  item.profile_id == null
                    ? tm("follows", { name: item.profile?.name || "" })
                    : item.profile?.name || item.profile_id
                }}</v-btn
              >
            </template>
            <template #item.overrides="{ item }">
              <span
                v-if="item.target_type === 'umop'"
                class="text-medium-emphasis"
                >—</span
              >
              <v-btn
                v-else
                variant="text"
                size="small"
                :disabled="busy"
                @click="edit(item, 'overrides')"
                >{{
                  Object.keys(item.overrides).length
                    ? tm("overrideCount", {
                        count: Object.keys(item.overrides).length,
                      })
                    : tm("addOverride")
                }}</v-btn
              >
            </template>
            <template #item.actions="{ item }">
              <v-btn
                icon="mdi-delete-outline"
                variant="text"
                size="small"
                :aria-label="
                  tm('remove', { name: item.display_name || item.target })
                "
                :disabled="busy"
                @click="remove(item)"
              />
            </template>
          </v-data-table>
        </template>
        <div
          v-else
          class="mapping-editor"
          :class="{ 'mapping-editor--split': view === 'target' }"
        >
          <aside v-if="view === 'target'" class="mapping-picker">
            <UmoSelector
              :model-value="selectedUmos"
              multiple
              :disabled="busy"
              @loaded="sessionInfos = $event"
              @update:model-value="changeSelection('umo', $event)"
            >
              <template #activator="{ open }">
                <v-menu>
                  <template #activator="{ props: menuProps }">
                    <v-btn
                      v-bind="menuProps"
                      variant="tonal"
                      prepend-icon="mdi-plus"
                      :disabled="busy"
                      >{{ tm("addTargets") }}</v-btn
                    >
                  </template>
                  <v-list density="compact">
                    <v-list-item
                      :title="tm('session')"
                      prepend-icon="mdi-message-outline"
                      @click="open"
                    />
                    <v-list-item
                      :title="tm('group')"
                      prepend-icon="mdi-folder-outline"
                      @click="
                        groupDraft = [...selectedGroups];
                        groupPicker = true;
                      "
                    />
                  </v-list>
                </v-menu>
              </template>
            </UmoSelector>
            <v-list class="mapping-picker__selected" density="compact">
              <v-list-item
                v-for="group in groups.filter((g) =>
                  selectedGroups.includes(g.id),
                )"
                :key="`group:${group.id}`"
                :title="group.name"
                :subtitle="tm('groupCount', { count: group.umos.length })"
                prepend-icon="mdi-folder-outline"
              >
                <template #append>
                  <v-btn
                    icon="mdi-close"
                    size="x-small"
                    variant="text"
                    :disabled="busy"
                    :aria-label="tm('removeTarget', { name: group.name })"
                    @click="
                      changeSelection(
                        'group',
                        selectedGroups.filter((id) => id !== group.id),
                      )
                    "
                  />
                </template>
              </v-list-item>
              <v-list-item v-for="umo in selectedUmos" :key="umo">
                <UmoDisplay
                  :umo="umo"
                  :auto-name="sessionNames[umo]?.auto_name || ''"
                  :user-alias="
                    sessionNames[umo]?.user_alias ||
                    sessionNames[umo]?.display_name ||
                    ''
                  "
                  compact
                  two-line-title
                  :show-info="false"
                />
                <template #append>
                  <v-btn
                    icon="mdi-close"
                    size="x-small"
                    variant="text"
                    :disabled="busy"
                    :aria-label="
                      tm('removeTarget', {
                        name: sessionNames[umo]?.display_name || umo,
                      })
                    "
                    @click="
                      changeSelection(
                        'umo',
                        selectedUmos.filter((id) => id !== umo),
                      )
                    "
                  />
                </template>
              </v-list-item>
            </v-list>
            <div
              v-if="targets.length"
              class="text-body-2 text-medium-emphasis mt-3"
            >
              {{ tm("selectedCount", { count: targets.length }) }}
            </div>
          </aside>
          <section class="mapping-editor__content">
            <template v-if="view === 'target'">
              <v-btn-toggle
                :model-value="destination"
                mandatory
                divided
                color="primary"
                variant="outlined"
                :disabled="busy"
                class="mb-5"
                @update:model-value="changeDestination"
              >
                <v-btn value="profile" variant="text">{{
                  tm("profile")
                }}</v-btn>
                <v-btn value="overrides" variant="text">{{
                  tm("overrides")
                }}</v-btn>
              </v-btn-toggle>
              <p
                v-if="!targets.length"
                class="mapping-editor__empty text-medium-emphasis"
              >
                {{ tm("selectTargetsHint") }}
              </p>
            </template>
            <div v-else class="text-body-2 text-medium-emphasis mb-4">
              {{ targetLabel }}
            </div>
            <template v-if="editTargets.length">
              <div v-if="destination === 'profile'" class="mapping-profile">
                <v-select
                  v-model="profileChoice"
                  :items="profileOptions"
                  :label="tm('profile')"
                  variant="outlined"
                  hide-details
                  :disabled="busy"
                />
                <p class="text-body-2 text-medium-emphasis mt-3">
                  {{ tm("profileHint") }}
                </p>
              </div>
              <template v-else>
                <p
                  v-if="editTargets.length > 1"
                  class="text-body-2 text-medium-emphasis mb-3"
                >
                  {{ tm("batchHint", { count: editTargets.length }) }}
                </p>
                <SessionOverrides
                  :key="editTargets.join(',')"
                  ref="overrideEditor"
                  embedded
                  :initial-umo="editTargets[0]"
                  :target-umos="editTargets"
                  @saved="saved"
                />
              </template>
            </template>
          </section>
        </div>
      </v-card-text>
      <v-divider v-if="view !== 'list'" />
      <v-card-actions v-if="view !== 'list'" class="px-6 py-4">
        <v-spacer />
        <v-btn
          v-if="destination === 'profile'"
          color="primary"
          variant="tonal"
          :disabled="!editTargets.length || profileChoice === null || busy"
          :loading="saving"
          @click="saveProfile"
          >{{ tm("save") }}</v-btn
        >
        <template v-else>
          <v-btn
            variant="text"
            :disabled="!overrideEditor?.canReset"
            @click="overrideEditor?.resetAll()"
            >{{ configTm("overrides.resetAll") }}</v-btn
          >
          <v-btn
            color="primary"
            variant="tonal"
            :disabled="!overrideEditor?.canSave"
            :loading="overrideEditor?.saving"
            @click="overrideEditor?.save(false)"
            >{{ configTm("overrides.save") }}</v-btn
          >
        </template>
      </v-card-actions>
    </v-card>
  </v-dialog>
  <v-dialog v-model="groupPicker" max-width="480">
    <v-card>
      <v-card-title class="text-h3 pa-4 pb-0 pl-6">{{
        tm("chooseGroup")
      }}</v-card-title>
      <v-card-text class="pt-5">
        <v-select
          v-model="groupDraft"
          :items="groups"
          item-title="name"
          item-value="id"
          multiple
          chips
          closable-chips
          :label="tm('chooseGroup')"
          variant="outlined"
          hide-details
        />
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="groupPicker = false">{{
          configTm("overrides.cancel")
        }}</v-btn>
        <v-btn
          variant="tonal"
          color="primary"
          @click="
            changeSelection('group', groupDraft);
            groupPicker = false;
          "
        >
          {{ configTm("overrides.done") }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
  <SessionGroupsDialog v-model="groupDialog" @changed="load" />
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { configProfileApi, configRouteApi, sessionApi } from "@/api/v1";
import UmoSelector from "@/components/shared/UmoSelector.vue";
import UmoDisplay from "@/components/shared/UmoDisplay.vue";
import SessionOverrides from "./SessionOverrides.vue";
import SessionGroupsDialog from "./SessionGroupsDialog.vue";
import { useModuleI18n } from "@/i18n/composables";
import { askForConfirmation, useConfirmDialog } from "@/utils/confirmDialog";
const props = defineProps<{ modelValue: boolean }>();
const emit = defineEmits<{ "update:modelValue": [value: boolean] }>();
const { tm: configTm } = useModuleI18n("features.config");
const tm = (key: string, params?: Record<string, any>) =>
  configTm(`mappings.${key}`, params);
const confirmDialog = useConfirmDialog();
const view = ref<"list" | "target" | "editor">("list");
const destination = ref<"profile" | "overrides">("profile");
const groupPicker = ref(false);
const groupDraft = ref<string[]>([]);
const sessionInfos = ref<any[]>([]);
const sessionNames = computed(() =>
  Object.fromEntries(
    [...rows.value, ...sessionInfos.value].map((info) => [info.umo, info]),
  ),
);
const selectedUmos = ref<string[]>([]);
const selectedGroups = ref<string[]>([]);
const groups = ref<any[]>([]);
const profiles = ref<any[]>([]);
const routes = ref<Record<string, string>>({});
const rows = ref<any[]>([]);
const search = ref("");
const loading = ref(false);
const saving = ref(false);
const error = ref("");
const groupDialog = ref(false);
const editTargets = ref<string[]>([]);
const targetLabel = ref("");
const editingRoute = ref(false);
const profileChoice = ref<string | null>(null);
const originalProfile = ref<string | null>(null);
const overrideEditor = ref<InstanceType<typeof SessionOverrides> | null>(null);
const busy = computed(() => saving.value || !!overrideEditor.value?.saving);
const targets = computed<string[]>(() => [
  ...new Set<string>([
    ...selectedUmos.value,
    ...groups.value
      .filter((g) => selectedGroups.value.includes(g.id))
      .flatMap((g) => g.umos || []),
  ]),
]);
const headers = computed(() => [
  { title: tm("source"), key: "target", sortable: false, width: "40%" },
  { title: tm("profile"), key: "profile", sortable: false, width: "32%" },
  { title: tm("overrides"), key: "overrides", sortable: false, width: "20%" },
  { title: "", key: "actions", sortable: false, width: 48 },
]);
const profileOptions = computed(() => [
  ...(!editingRoute.value ? [{ title: tm("followRouting"), value: "" }] : []),
  ...profiles.value.map((p) => ({ title: p.name, value: p.id })),
]);
const filteredRows = computed(() => {
  const q = (search.value || "").toLowerCase();
  return rows.value.filter((r) =>
    `${r.target} ${r.display_name} ${r.profile?.name || ""}`
      .toLowerCase()
      .includes(q),
  );
});
async function load() {
  loading.value = true;
  error.value = "";
  try {
    const [profileResponse, routeResponse, groupResponse] = await Promise.all([
      configProfileApi.list(),
      configRouteApi.list(),
      sessionApi.listGroups(),
    ]);
    for (const response of [profileResponse, routeResponse, groupResponse])
      if (response.data.status !== "ok")
        throw new Error(response.data.message || tm("error"));
    profiles.value = profileResponse.data.data.info_list;
    routes.value = routeResponse.data.data.routing || {};
    groups.value = groupResponse.data.data.groups || [];
    const sessions: any[] = [];
    let page = 1;
    while (true) {
      const response = await sessionApi.listRules({ page, page_size: 100 });
      if (response.data.status !== "ok")
        throw new Error(response.data.message || tm("error"));
      const items = response.data.data.rules || [];
      sessions.push(...items);
      if (!items.length || sessions.length >= response.data.data.total) break;
      page++;
    }
    rows.value = [
      ...sessions.map((s) => ({
        ...s,
        key: `umo:${s.umo}`,
        target_type: "umo",
        target: s.umo,
        overrides: s.rules?.config_overrides || {},
      })),
      ...Object.entries(routes.value).flatMap(([target, profile_id], order) => {
        const parts = target.split(":");
        const isBot =
          parts.length === 3 &&
          !!parts[0] &&
          !/[*?[\]]/.test(parts[0]) &&
          parts.slice(1).every((part) => part === "" || part === "*");
        if (isBot || sessions.some((session) => session.umo === target))
          return [];
        return [
          {
            key: `umop:${target}`,
            target_type: "umop",
            target,
            display_name: target,
            profile_id,
            profile: profiles.value.find((p) => p.id === profile_id),
            overrides: {},
            order,
          },
        ];
      }),
    ];
  } catch (err: any) {
    error.value = err.message || tm("error");
  } finally {
    loading.value = false;
  }
}
function startAdd() {
  selectedUmos.value = [];
  selectedGroups.value = [];
  editTargets.value = [];
  editingRoute.value = false;
  profileChoice.value = null;
  originalProfile.value = null;
  destination.value = "profile";
  error.value = "";
  view.value = "target";
}
async function changeSelection(kind: "umo" | "group", value: string[]) {
  if (busy.value) return;
  const nextTargets = [
    ...new Set<string>([
      ...(kind === "umo" ? value : selectedUmos.value),
      ...groups.value
        .filter((g) =>
          (kind === "group" ? value : selectedGroups.value).includes(g.id),
        )
        .flatMap((g) => g.umos || []),
    ]),
  ];
  const changed =
    nextTargets.length !== editTargets.value.length ||
    nextTargets.some((umo) => !editTargets.value.includes(umo));
  if (
    changed &&
    destination.value === "overrides" &&
    !((await overrideEditor.value?.canLeave()) ?? true)
  )
    return;
  if (kind === "group") selectedGroups.value = value;
  else selectedUmos.value = value;
  if (changed) editTargets.value = nextTargets;
}
async function changeDestination(value: unknown) {
  if (
    (value !== "profile" && value !== "overrides") ||
    value === destination.value
  )
    return;
  if (!(await canLeave())) return;
  destination.value = value;
  profileChoice.value = null;
  originalProfile.value = null;
}
function edit(item: any, kind: "profile" | "overrides") {
  editTargets.value = [item.target];
  editingRoute.value = item.target_type === "umop";
  targetLabel.value = item.display_name || item.target;
  destination.value = kind;
  profileChoice.value = item.profile_id ?? "";
  originalProfile.value = profileChoice.value;
  error.value = "";
  view.value = "editor";
}
async function canLeave() {
  if (busy.value) return false;
  if (view.value !== "list" && destination.value === "overrides")
    return (await overrideEditor.value?.canLeave()) ?? true;
  if (view.value !== "list" && profileChoice.value !== originalProfile.value)
    return askForConfirmation(tm("discard"), confirmDialog);
  return true;
}
defineExpose({ canLeave });
async function close() {
  if (await canLeave()) emit("update:modelValue", false);
}
async function back() {
  if (await canLeave()) {
    view.value = "list";
    error.value = "";
  }
}
async function saved() {
  view.value = "list";
  await load();
}
async function saveProfile() {
  if (profileChoice.value === null || !editTargets.value.length || busy.value)
    return;
  saving.value = true;
  error.value = "";
  try {
    for (const target of editTargets.value) {
      const response = editingRoute.value
        ? await configRouteApi.replace({
            routing: { ...routes.value, [target]: profileChoice.value },
          })
        : await sessionApi.upsertRule({
            umo: target,
            rule_key: "config_overrides",
            rule_value: {},
            profile_id: profileChoice.value || null,
          });
      if (response.data.status !== "ok")
        throw new Error(`${target}: ${response.data.message || tm("error")}`);
    }
    originalProfile.value = profileChoice.value;
    await saved();
  } catch (err: any) {
    error.value = err.message || tm("error");
  } finally {
    saving.value = false;
  }
}
async function remove(item: any) {
  if (
    !(await askForConfirmation(
      tm("removeConfirm", { name: item.display_name || item.target }),
      confirmDialog,
    ))
  )
    return;
  saving.value = true;
  error.value = "";
  try {
    const response =
      item.target_type === "umop"
        ? await configRouteApi.delete(item.target)
        : await sessionApi.deleteRules({
            umo: item.target,
            rule_key: "config_binding",
          });
    if (response.data.status !== "ok")
      throw new Error(response.data.message || tm("error"));
    await load();
  } catch (err: any) {
    error.value = err.message || tm("error");
  } finally {
    saving.value = false;
  }
}
watch(
  () => props.modelValue,
  (open) => {
    if (open) {
      view.value = "list";
      search.value = "";
      void load();
    }
  },
  { immediate: true },
);
</script>

<style scoped>
.mapping-card > .v-card-text {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}
.mapping-list-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 20px;
}
.mapping-list-toolbar .v-text-field {
  max-width: 340px;
  margin-right: auto;
}
.mapping-table {
  background: transparent;
}
.mapping-target {
  min-width: 160px;
  max-width: 340px;
  overflow-wrap: anywhere;
}
.mapping-value {
  max-width: 260px;
  height: auto;
  min-height: 32px;
  white-space: normal;
  text-align: left;
}
.mapping-card > .mapping-card__split {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.mapping-editor--split {
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr);
  gap: 24px;
  flex: 1;
  min-height: 0;
}
.mapping-picker {
  display: flex;
  flex-direction: column;
  min-height: 0;
  border-right: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  padding-right: 20px;
}
.mapping-picker__selected {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  margin-top: 16px;
}
.mapping-picker__selected :deep(.v-list-item) {
  padding: 10px 0;
}
.mapping-picker__selected :deep(.v-list-item-title) {
  overflow: hidden;
  text-overflow: ellipsis;
}
.mapping-picker__selected :deep(.v-list-item__content) {
  min-width: 0;
}
.mapping-editor__content {
  min-width: 0;
  overflow-y: auto;
}
.mapping-editor__empty {
  padding: 40px 0;
  text-align: center;
}
.mapping-profile {
  max-width: 600px;
}
@media (max-width: 700px) {
  .mapping-card > .mapping-card__split {
    overflow-y: auto;
  }
  .mapping-editor--split {
    display: flex;
    flex-direction: column;
    flex: none;
  }
  .mapping-picker {
    border-right: 0;
    padding-right: 0;
  }
  .mapping-picker__selected {
    flex: none;
    max-height: 180px;
  }
  .mapping-editor__content {
    overflow: visible;
  }
}
@media (max-width: 600px) {
  .mapping-list-toolbar {
    flex-wrap: wrap;
  }
  .mapping-list-toolbar .v-text-field {
    flex-basis: 100%;
    max-width: none;
  }
  .mapping-target {
    max-width: 180px;
  }
  .mapping-value {
    max-width: 180px;
  }
}
</style>
