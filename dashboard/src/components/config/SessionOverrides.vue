<template>
  <section
    class="session-workspace"
    :class="{ 'session-workspace--embedded': embedded }"
  >
    <div v-if="!embedded" class="session-toolbar">
      <button
        type="button"
        class="session-picker"
        :title="selectedUmo"
        :disabled="busy"
        @click="pickerDialog = true"
      >
        <span class="session-picker__text">
          <span class="session-picker__name"
            ><strong>{{ details?.display_name || tm("chooseSession") }}</strong
            ><v-icon size="18">mdi-chevron-down</v-icon></span
          >
          <span v-if="details" class="session-picker__source">{{
            tm("inherits", { name: effectiveDetails.profile.name })
          }}</span>
        </span>
      </button>
      <v-chip
        v-if="activeGroup"
        size="small"
        closable
        variant="tonal"
        @click:close="groupId = ''"
        >{{ activeGroup.name }}</v-chip
      >
      <div class="session-toolbar__actions">
        <v-checkbox
          v-if="details"
          v-model="onlyOverrides"
          :label="tm('onlyOverrides')"
          color="primary"
          density="compact"
          hide-details
        />
        <v-menu>
          <template #activator="{ props }"
            ><v-btn
              v-bind="props"
              icon="mdi-dots-horizontal"
              variant="text"
              size="small"
              :aria-label="tm('moreActions')"
              :disabled="busy"
          /></template>
          <v-list density="compact">
            <v-list-item
              v-if="details"
              prepend-icon="mdi-pencil-outline"
              :title="tm('alias')"
              @click="aliasDialog = true"
            />
            <v-list-item
              prepend-icon="mdi-folder-outline"
              :title="tm('groups')"
              @click="groupDialog = true"
            />
          </v-list>
        </v-menu>
      </div>
    </div>
    <v-alert
      v-if="error"
      type="error"
      variant="tonal"
      closable
      class="my-4"
      @click:close="error = ''"
      >{{ error }}</v-alert
    >
    <div v-if="loading" class="session-editor__empty">
      <v-progress-circular indeterminate color="primary" />
    </div>
    <template v-else-if="details">
      <div
        class="override-fields"
        :class="{ 'override-fields--busy': saving }"
        :inert="saving || undefined"
      >
        <v-list class="settings-list" bg-color="transparent" lines="two">
          <v-list-item
            v-if="!embedded"
            tag="button"
            type="button"
            class="override-field"
            :active="false"
            :disabled="busy"
            :title="tm('baseProfile')"
            :subtitle="
              profileId
                ? effectiveDetails.profile.name
                : tm('followsRouting', { name: effectiveDetails.profile.name })
            "
            @click="
              profileChoice = profileId;
              profileDialog = true;
            "
          >
            <template #append
              ><v-icon size="20" color="medium-emphasis"
                >mdi-chevron-right</v-icon
              ></template
            >
          </v-list-item>
          <template v-for="(group, index) in visibleGroups" :key="group.key">
            <v-divider v-if="index" class="my-3" />
            <v-list-subheader class="override-group-title">{{
              tm(`fieldGroups.${group.key}`)
            }}</v-list-subheader>
            <v-list-item
              v-for="field in group.fields"
              :key="field.path"
              tag="button"
              type="button"
              class="override-field"
              :active="false"
              :disabled="busy"
              :title="tm(`fields.${field.label}`)"
              :subtitle="
                batchMode && !touchedFields.has(field.path)
                  ? tm('batchUnchanged')
                  : field.path in draft
                  ? tm('valueCustom', {
                      value: displayValue(draft[field.path], field.path),
                    })
                  : batchMode
                  ? tm('follow')
                  : tm('valueFollowing', {
                      value: displayValue(
                        effectiveDetails.inherited[field.path],
                        field.path,
                      ),
                    })
              "
              @click="
                editingField = field;
                editingMode =
                  field.path in draft
                    ? field.meta.type === 'bool'
                      ? draft[field.path]
                      : 'custom'
                    : 'inherit';
                editingValue = clone(
                  draft[field.path] ??
                    (batchMode
                      ? undefined
                      : effectiveDetails.inherited[field.path]) ??
                    (field.meta.type === 'list'
                      ? []
                      : field.meta.type === 'int'
                      ? 5
                      : ''),
                );
                fieldDialog = true;
              "
            >
              <template #append
                ><v-icon size="20" color="medium-emphasis"
                  >mdi-chevron-right</v-icon
                ></template
              >
            </v-list-item>
          </template>
        </v-list>
        <div
          v-if="!visibleFields.length"
          class="session-editor__empty session-editor__empty--small"
        >
          <v-icon size="28">mdi-check-circle-outline</v-icon>
          <p>{{ tm("noOverridesHere") }}</p>
          <v-btn
            variant="text"
            color="primary"
            @click="onlyOverrides = false"
            >{{ tm("showAll") }}</v-btn
          >
        </div>
      </div>
      <footer v-if="!embedded" class="session-editor__footer">
        <div v-if="dirty" class="session-save-state">
          <span class="save-dot" /><span>{{ tm("unsaved") }}</span>
        </div>
        <div class="session-save-actions">
          <v-btn variant="text" :disabled="!canReset" @click="resetAll">{{
            tm("resetAll")
          }}</v-btn>
          <v-btn
            v-if="activeGroup"
            variant="tonal"
            :disabled="busy || !Object.keys(changes).length"
            @click="save(true)"
            >{{ tm("applyGroup", { count: activeGroup.umos.length }) }}</v-btn
          >
          <v-btn
            color="primary"
            variant="tonal"
            :disabled="!canSave"
            :loading="saving"
            @click="save(false)"
            >{{ tm("save") }}</v-btn
          >
        </div>
      </footer>
    </template>
    <div v-else-if="!loading" class="session-editor__empty">
      <v-icon size="36" color="primary">mdi-tune-variant</v-icon>
      <h2>{{ tm("emptyTitle") }}</h2>
      <p>{{ tm("emptyHint") }}</p>
      <UmoSelector
        :model-value="selectedUmo"
        :multiple="false"
        @update:model-value="selectSession(String($event || ''))"
        ><template #activator="{ open }"
          ><v-btn variant="tonal" color="primary" @click="open">{{
            tm("chooseSession")
          }}</v-btn></template
        ></UmoSelector
      >
    </div>

    <v-dialog
      v-model="profileDialog"
      max-width="480"
      :persistent="previewLoading"
    >
      <v-card>
        <v-card-title class="text-h3 pa-4 pb-0 pl-6">{{
          tm("baseProfile")
        }}</v-card-title>
        <v-card-text>
          <v-radio-group v-model="profileChoice" hide-details>
            <v-radio
              :label="
                tm('followsRouting', {
                  name: details?.routing_profile?.name || '',
                })
              "
              value=""
            />
            <v-radio
              v-for="profile in details?.profiles || []"
              :key="profile.id"
              :label="profile.name"
              :value="profile.id"
            />
          </v-radio-group>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn
            variant="text"
            :disabled="previewLoading"
            @click="profileDialog = false"
            >{{ tm("cancel") }}</v-btn
          >
          <v-btn
            variant="tonal"
            color="primary"
            :loading="previewLoading"
            @click="chooseProfile"
            >{{ tm("done") }}</v-btn
          >
        </v-card-actions>
      </v-card>
    </v-dialog>
    <v-dialog v-model="fieldDialog" max-width="480" scrollable>
      <v-card v-if="editingField" class="setting-dialog">
        <v-card-title class="text-h3 pa-4 pb-0 pl-6">{{
          tm(`fields.${editingField.label}`)
        }}</v-card-title>
        <v-card-text>
          <p v-if="!batchMode" class="text-body-2 text-medium-emphasis mb-4">
            {{ tm("inherits", { name: effectiveDetails.profile.name }) }} ·
            {{
              displayValue(
                effectiveDetails.inherited[editingField.path],
                editingField.path,
              )
            }}
          </p>
          <p
            v-if="editingField.path === blacklistPath"
            class="text-body-2 text-medium-emphasis mb-4"
          >
            {{ tm("sessionStatusHint") }}
          </p>
          <v-radio-group
            v-model="editingMode"
            hide-details
            color="primary"
            :aria-label="tm(`fields.${editingField.label}`)"
          >
            <v-radio :label="tm('follow')" value="inherit" />
            <template v-if="editingField.meta.type === 'bool'">
              <v-radio
                :label="
                  tm(
                    editingField.path === blacklistPath
                      ? 'sessionEnabled'
                      : 'on',
                  )
                "
                :value="true"
              />
              <v-radio
                :label="
                  tm(
                    editingField.path === blacklistPath
                      ? 'sessionStopped'
                      : 'off',
                  )
                "
                :value="false"
              />
            </template>
            <v-radio v-else :label="tm('setForSession')" value="custom" />
          </v-radio-group>
          <div v-if="editingMode === 'custom'" class="setting-dialog__value">
            <ConfigItemRenderer
              :item-meta="editingField.meta"
              v-model="editingValue"
              :config-root="{}"
            />
            <p
              v-if="editingField.meta.type === 'list'"
              class="text-caption text-medium-emphasis mt-3"
            >
              {{
                tm(
                  editingField.path === "wake_prefix"
                    ? "wakePrefixHint"
                    : "listHint",
                )
              }}
            </p>
          </div>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="fieldDialog = false">{{
            tm("cancel")
          }}</v-btn>
          <v-btn
            color="primary"
            variant="tonal"
            @click="
              touchedFields.add(editingField.path);
              editingMode === 'inherit'
                ? delete draft[editingField.path]
                : (draft[editingField.path] = clone(
                    editingField.meta.type === 'bool'
                      ? editingMode
                      : editingValue,
                  ));
              fieldDialog = false;
            "
            >{{ tm("done") }}</v-btn
          >
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="pickerDialog" max-width="640" scrollable>
      <v-card>
        <v-card-title class="text-h3 pa-4 pb-0 pl-6">{{
          tm("chooseSession")
        }}</v-card-title>
        <v-card-text>
          <v-text-field
            v-model="search"
            :placeholder="tm('search')"
            prepend-inner-icon="mdi-magnify"
            variant="outlined"
            density="compact"
            hide-details
            clearable
          />
          <v-select
            v-model="groupId"
            :items="[{ id: '', name: tm('allOverrides') }, ...groups]"
            item-title="name"
            item-value="id"
            variant="outlined"
            density="compact"
            hide-details
            class="mt-3"
            :aria-label="tm('groups')"
          />
          <v-progress-linear
            v-if="listLoading"
            indeterminate
            color="primary"
            class="mt-3"
          />
          <div class="session-index__list">
            <button
              v-for="item in visibleSessions"
              :key="item.umo"
              type="button"
              class="session-row"
              :class="{ 'session-row--active': selectedUmo === item.umo }"
              :aria-pressed="selectedUmo === item.umo"
              :disabled="busy"
              @click="selectSession(item.umo)"
            >
              <span class="session-row__name">{{
                item.display_name || item.umo
              }}</span
              ><span class="session-row__origin">{{ item.umo }}</span
              ><span v-if="item.profile" class="session-row__source"
                >{{ item.profile.name }} ·
                {{
                  tm("count", {
                    count: Object.keys(item.rules?.config_overrides || {})
                      .length,
                  })
                }}</span
              >
            </button>
            <p
              v-if="!listLoading && !visibleSessions.length"
              class="session-index__empty"
            >
              {{ tm("noSessions") }}
            </p>
          </div>
          <v-pagination
            v-if="!groupId && total > 20"
            v-model="page"
            :length="Math.ceil(total / 20)"
            :total-visible="3"
            size="small"
          />
        </v-card-text>
        <v-card-actions
          ><UmoSelector
            :model-value="selectedUmo"
            :multiple="false"
            :disabled="busy"
            @update:model-value="selectSession(String($event || ''))"
            ><template #activator="{ open }"
              ><v-btn variant="tonal" color="primary" @click="open">{{
                tm("otherSession")
              }}</v-btn></template
            ></UmoSelector
          ><v-spacer /><v-btn variant="text" @click="pickerDialog = false">{{
            tm("done")
          }}</v-btn></v-card-actions
        >
      </v-card>
    </v-dialog>
    <v-dialog v-model="aliasDialog" max-width="460">
      <v-card>
        <v-card-title class="text-h3 pa-4 pb-0 pl-6">{{
          tm("alias")
        }}</v-card-title>
        <v-card-text
          ><v-text-field
            v-model="alias"
            :label="tm('alias')"
            maxlength="255"
            variant="outlined"
            hide-details
          />
          <p class="text-caption mt-3">{{ tm("aliasHint") }}</p></v-card-text
        >
        <v-card-actions
          ><v-spacer /><v-btn variant="tonal" @click="aliasDialog = false">{{
            tm("done")
          }}</v-btn></v-card-actions
        >
      </v-card>
    </v-dialog>
    <SessionGroupsDialog v-model="groupDialog" @changed="loadGroups" />
    <v-snackbar v-model="notice" :timeout="3000">{{
      tm("saveSuccess")
    }}</v-snackbar>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { onBeforeRouteLeave, onBeforeRouteUpdate } from "vue-router";
import { sessionApi } from "@/api/v1";
import ConfigItemRenderer from "@/components/shared/ConfigItemRenderer.vue";
import SessionGroupsDialog from "./SessionGroupsDialog.vue";
import UmoSelector from "@/components/shared/UmoSelector.vue";
import { useModuleI18n } from "@/i18n/composables";
import { askForConfirmation, useConfirmDialog } from "@/utils/confirmDialog";

const props = withDefaults(
  defineProps<{
    embedded?: boolean;
    initialUmo?: string;
    targetUmos?: string[];
  }>(),
  { embedded: false, initialUmo: "", targetUmos: () => [] },
);
const emit = defineEmits<{ saved: [] }>();

const { tm: configTm } = useModuleI18n("features.config");
const tm = (key: string, params?: Record<string, any>) =>
  configTm(`overrides.${key}`, params);
const confirmDialog = useConfirmDialog();
const selectedUmo = ref("");
const details = ref<any>(null);
const profileId = ref("");
const profileChoice = ref("");
const profileDialog = ref(false);
const previewLoading = ref(false);
const previewDetails = ref<any>(null);
const blacklistPath = "platform_settings.id_blacklist";
const effectiveDetails = computed(() => {
  const source = previewDetails.value || details.value;
  return source
    ? {
        ...source,
        inherited: editorValues(source.inherited, selectedUmo.value),
      }
    : null;
});
const draft = ref<Record<string, any>>({});
const original = ref<Record<string, any>>({});
const alias = ref("");
const aliasDialog = ref(false);
const pickerDialog = ref(false);
const fieldDialog = ref(false);
const editingMode = ref<string | boolean>("inherit");
const editingValue = ref<any>(null);
const loading = ref(false);
const saving = ref(false);
const listLoading = ref(false);
const error = ref("");
const notice = ref(false);
const onlyOverrides = ref(false);
const search = ref("");
const page = ref(1);
const total = ref(0);
const sessions = ref<any[]>([]);
const groups = ref<any[]>([]);
const groupId = ref("");
const groupDialog = ref(false);
const busy = computed(
  () => loading.value || saving.value || previewLoading.value,
);
const activeGroup = computed(() =>
  groups.value.find((group) => group.id === groupId.value),
);
const batchMode = computed(() => props.embedded && props.targetUmos.length > 1);
const touchedFields = ref(new Set<string>());
const changes = computed(() =>
  batchMode.value
    ? Object.fromEntries(
        [...touchedFields.value].map((key) => [
          key,
          key in draft.value ? draft.value[key] : null,
        ]),
      )
    : Object.fromEntries(
        [
          ...new Set([
            ...Object.keys(original.value),
            ...Object.keys(draft.value),
          ]),
        ]
          .filter(
            (key) =>
              JSON.stringify(original.value[key]) !==
              JSON.stringify(draft.value[key]),
          )
          .map((key) => [key, key in draft.value ? draft.value[key] : null]),
      ),
);
const dirty = computed(
  () =>
    profileId.value !== (details.value?.profile_id || "") ||
    Object.keys(changes.value).length > 0 ||
    alias.value !== (details.value?.user_alias || ""),
);
const canSave = computed(() => !!details.value && dirty.value && !busy.value);
const canReset = computed(
  () =>
    !!details.value &&
    !busy.value &&
    (batchMode.value || Object.keys(draft.value).length > 0),
);
const visibleSessions = computed(() =>
  activeGroup.value
    ? activeGroup.value.umos
        .map(
          (umo: string) =>
            sessions.value.find((item) => item.umo === umo) || { umo },
        )
        .filter((item: any) =>
          `${item.umo} ${item.display_name || ""}`
            .toLowerCase()
            .includes((search.value || "").toLowerCase()),
        )
    : sessions.value,
);
const fields = computed(() => [
  {
    path: "platform_settings.id_blacklist",
    label: "sessionStatus",
    group: "session",
    meta: { type: "bool" },
  },
  {
    path: "wake_prefix",
    label: "wakePrefix",
    group: "session",
    meta: { type: "list" },
  },
  {
    path: "provider_settings.enable",
    label: "aiEnabled",
    group: "ai",
    meta: { type: "bool" },
  },
  ...(effectiveDetails.value?.runtime === "astrbot"
    ? [
        {
          path: "agent.config.model.provider_id",
          label: "chatModel",
          group: "ai",
          meta: { type: "string", _special: "select_provider" },
        },
      ]
    : []),
  {
    path:
      effectiveDetails.value?.runtime === "astrbot"
        ? "agent.config.persona.persona_id"
        : "agent.config.persona_id",
    label: "persona",
    group: "ai",
    meta: { type: "string", _special: "select_persona" },
  },
  {
    path: "provider_stt_settings.enable",
    label: "sttEnabled",
    group: "voice",
    meta: { type: "bool" },
  },
  {
    path: "provider_stt_settings.provider_id",
    label: "sttModel",
    group: "voice",
    meta: { type: "string", _special: "select_provider_stt" },
  },
  {
    path: "provider_tts_settings.enable",
    label: "ttsEnabled",
    group: "voice",
    meta: { type: "bool" },
  },
  {
    path: "provider_tts_settings.provider_id",
    label: "ttsModel",
    group: "voice",
    meta: { type: "string", _special: "select_provider_tts" },
  },
  {
    path: "kb_names",
    label: "knowledgeBases",
    group: "knowledge",
    meta: { type: "list", _special: "select_knowledgebase" },
  },
  {
    path: "kb_final_top_k",
    label: "retrievalCount",
    group: "knowledge",
    meta: { type: "int" },
  },
  {
    path: "plugin_set",
    label: "allowedPlugins",
    group: "plugins",
    meta: { type: "list", _special: "select_plugin_set" },
  },
  {
    path: "disabled_plugins",
    label: "disabledPlugins",
    group: "plugins",
    meta: { type: "list", _special: "select_plugin_set", selection_only: true },
  },
]);
const editingField = ref<(typeof fields.value)[number] | null>(null);
const visibleFields = computed(() =>
  fields.value.filter(
    (field) => !onlyOverrides.value || field.path in draft.value,
  ),
);

const visibleGroups = computed(() =>
  ["session", "ai", "voice", "knowledge", "plugins"]
    .map((key) => ({
      key,
      fields: visibleFields.value.filter((field) => field.group === key),
    }))
    .filter((group) => group.fields.length),
);

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value));
}
function editorValues(values: Record<string, any>, umo: string) {
  const result = { ...values };
  if (blacklistPath in result) {
    const blocked = new Set(
      (result[blacklistPath] || []).map((item: unknown) => String(item).trim()),
    );
    const parts = umo.split(":");
    result[blacklistPath] =
      !blocked.has(umo) &&
      !(parts[1] === "GroupMessage" && blocked.has(parts.slice(2).join(":")));
  }
  return result;
}
function displayValue(value: any, path?: string) {
  if (path === blacklistPath && typeof value === "boolean")
    return tm(value ? "sessionEnabled" : "sessionStopped");
  if (value === true) return tm("on");
  if (value === false) return tm("off");
  if (value == null || value === "" || (Array.isArray(value) && !value.length))
    return tm("emptyValue");
  if (Array.isArray(value))
    return path === "plugin_set" && value.includes("*")
      ? tm("allPlugins")
      : value.join(", ");
  return String(value);
}
async function canLeave() {
  return (
    !busy.value &&
    (!dirty.value ||
      (await askForConfirmation(tm("discardConfirm"), confirmDialog)))
  );
}
if (!props.embedded) {
  onBeforeRouteLeave(canLeave);
  onBeforeRouteUpdate(canLeave);
}
defineExpose({ canLeave, canSave, canReset, saving, save, resetAll });

let listRequest = 0;
async function loadList() {
  const request = ++listRequest;
  listLoading.value = true;
  try {
    const response = await sessionApi.listRules({
      page: page.value,
      page_size: 20,
      search: search.value || "",
    });
    if (request !== listRequest) return;
    if (response.data.status !== "ok")
      throw new Error(response.data.message || tm("error"));
    sessions.value = response.data.data.rules;
    total.value = response.data.data.total;
  } catch (err: any) {
    error.value = err.message || tm("error");
  } finally {
    if (request === listRequest) listLoading.value = false;
  }
}
async function selectSession(umo: string) {
  if (!umo || !(await canLeave())) return;
  loading.value = true;
  error.value = "";
  try {
    const response = await sessionApi.overrides(umo);
    if (response.data.status !== "ok")
      throw new Error(response.data.message || tm("error"));
    details.value = response.data.data;
    profileId.value = details.value.profile_id || "";
    previewDetails.value = null;
    selectedUmo.value = umo;
    pickerDialog.value = false;
    original.value = clone(editorValues(details.value.overrides, umo));
    draft.value = batchMode.value ? {} : clone(original.value);
    touchedFields.value.clear();
    alias.value = details.value.user_alias || "";
  } catch (err: any) {
    error.value = err.message || tm("error");
  } finally {
    loading.value = false;
  }
}
async function chooseProfile() {
  previewLoading.value = true;
  error.value = "";
  try {
    const response = await sessionApi.overrides(
      selectedUmo.value,
      profileChoice.value,
    );
    if (response.data.status !== "ok")
      throw new Error(response.data.message || tm("error"));
    previewDetails.value = response.data.data;
    profileId.value = profileChoice.value;
    profileDialog.value = false;
  } catch (err: any) {
    error.value = err.message || tm("error");
  } finally {
    previewLoading.value = false;
  }
}
async function resetAll() {
  if (await askForConfirmation(tm("resetConfirm"), confirmDialog)) {
    draft.value = {};
    if (batchMode.value)
      touchedFields.value = new Set(fields.value.map((field) => field.path));
  }
}
async function save(toGroup: boolean) {
  const targets: string[] =
    props.embedded && props.targetUmos.length
      ? [...new Set(props.targetUmos)]
      : toGroup
      ? [...new Set<string>(activeGroup.value?.umos || [])]
      : [selectedUmo.value];
  if (
    toGroup &&
    !(await askForConfirmation(
      tm("groupConfirm", { count: targets.length }),
      confirmDialog,
    ))
  )
    return;
  saving.value = true;
  error.value = "";
  const patch = clone(changes.value);
  try {
    let selectedResponse: any = null;
    for (const umo of targets) {
      const sessionPatch = { ...patch };
      if (typeof patch[blacklistPath] === "boolean") {
        // Derive each session's list separately; never copy another session's blacklist.
        const current = await sessionApi.overrides(
          umo,
          profileId.value !== (details.value?.profile_id || "")
            ? profileId.value
            : undefined,
        );
        if (current.data.status !== "ok")
          throw new Error(`${umo}: ${current.data.message}`);
        const source =
          current.data.data.overrides[blacklistPath] ??
          current.data.data.inherited[blacklistPath] ??
          [];
        const blocked = new Set<string>(
          source.map((item: unknown) => String(item).trim()),
        );
        if (patch[blacklistPath]) {
          blocked.delete(umo);
          const parts = umo.split(":");
          if (parts[1] === "GroupMessage")
            blocked.delete(parts.slice(2).join(":"));
        } else {
          blocked.add(umo);
        }
        sessionPatch[blacklistPath] = [...blocked];
      }
      const response = await sessionApi.upsertRule({
        umo,
        rule_key: "config_overrides",
        rule_value: sessionPatch,
        ...(profileId.value !== (details.value?.profile_id || "")
          ? { profile_id: profileId.value || null }
          : {}),
        ...(!toGroup && !props.embedded ? { user_alias: alias.value } : {}),
      });
      if (response.data.status !== "ok")
        throw new Error(`${umo}: ${response.data.message}`);
      if (umo === selectedUmo.value) selectedResponse = response.data.data;
    }
    if (selectedResponse) {
      details.value = selectedResponse;
      profileId.value = selectedResponse.profile_id || "";
      previewDetails.value = null;
      original.value = clone(
        editorValues(selectedResponse.overrides, selectedUmo.value),
      );
      draft.value = batchMode.value ? {} : clone(original.value);
      touchedFields.value.clear();
      if (!toGroup) alias.value = selectedResponse.user_alias || "";
    }
    notice.value = true;
    if (!props.embedded) await loadList();
    emit("saved");
  } catch (err: any) {
    error.value = err.message || tm("error");
  } finally {
    saving.value = false;
  }
}
async function loadGroups() {
  const response = await sessionApi.listGroups();
  if (response.data.status !== "ok")
    throw new Error(response.data.message || tm("error"));
  groups.value = response.data.data.groups;
}
let searchTimer: ReturnType<typeof setTimeout>;
watch(search, () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    if (page.value !== 1) page.value = 1;
    else loadList();
  }, 250);
});
watch(page, loadList);
function beforeUnload(event: BeforeUnloadEvent) {
  if (dirty.value) {
    event.preventDefault();
    event.returnValue = "";
  }
}
onMounted(async () => {
  window.addEventListener("beforeunload", beforeUnload);
  if (props.embedded) {
    await selectSession(props.initialUmo);
    return;
  }
  await loadList();
  if (sessions.value.length) await selectSession(sessions.value[0].umo);
  try {
    await loadGroups();
  } catch (err: any) {
    error.value = err.message || tm("error");
  }
});
onBeforeUnmount(() => {
  clearTimeout(searchTimer);
  ++listRequest;
  window.removeEventListener("beforeunload", beforeUnload);
});
</script>

<style scoped>
.session-workspace--embedded {
  padding: 0 !important;
}

.session-workspace {
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 18px;
}
.session-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 4px 8px 16px;
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  margin-bottom: 8px;
}
.session-picker {
  min-width: 0;
  max-width: 60%;
  padding: 4px 8px;
  border-radius: 8px;
  color: inherit;
  text-align: left;
}
.session-picker:hover {
  background: rgba(var(--v-theme-on-surface), 0.04);
}
.session-picker__text {
  display: grid;
  min-width: 0;
  gap: 4px;
}
.session-picker__name {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.session-picker__name strong {
  font-size: 15px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.session-picker__source {
  font-size: 12px;
  color: rgba(var(--v-theme-on-surface), 0.6);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.session-toolbar__actions {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-left: auto;
  flex-shrink: 0;
}
.session-toolbar__actions :deep(.v-label) {
  font-size: 12px;
}
.override-group-title {
  color: rgb(var(--v-theme-primary));
  font-weight: 600;
  min-height: 36px;
}
.settings-list {
  padding: 0;
}
.override-field {
  width: 100%;
  min-height: 72px;
  padding: 12px 16px;
  text-align: left;
  border-radius: 8px;
}
.override-field :deep(.v-list-item-title) {
  font-size: 15px;
  line-height: 24px;
  font-weight: 500;
}
.override-field :deep(.v-list-item-subtitle) {
  font-size: 13px;
  line-height: 20px;
  margin-top: 2px;
  overflow-wrap: anywhere;
}
.override-field :deep(.v-list-item__append) {
  padding-left: 24px;
}
.setting-dialog__value {
  padding: 16px 0 0 40px;
}
h2 {
  font-size: 15px;
  font-weight: 600;
}
.override-fields--busy {
  opacity: 0.65;
}
.session-editor__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  position: sticky;
  bottom: 0;
  padding: 16px 0;
  border-top: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  background: rgb(var(--v-theme-surface));
  z-index: 2;
}
.session-save-state {
  display: flex;
  align-items: center;
  gap: 8px;
  color: rgb(var(--v-theme-primary));
  font-size: 12px;
}
.save-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
}
.session-save-actions {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}
.session-editor__empty {
  min-height: 360px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  text-align: center;
  gap: 16px;
  color: rgba(var(--v-theme-on-surface), 0.6);
}
.session-editor__empty p {
  max-width: 380px;
  font-size: 14px;
  line-height: 1.8;
}
.session-editor__empty--small {
  min-height: 220px;
}
.session-index__list {
  margin-top: 16px;
  display: grid;
  gap: 6px;
  max-height: 50vh;
  overflow: auto;
}
.session-row {
  text-align: left;
  border: 1px solid transparent;
  border-radius: 8px;
  padding: 12px;
  display: grid;
  gap: 4px;
  width: 100%;
  color: inherit;
}
.session-row:hover {
  background: rgba(var(--v-theme-primary), 0.04);
}
.session-row--active {
  background: rgba(var(--v-theme-primary), 0.07);
  border-color: rgba(var(--v-theme-primary), 0.2);
}
.session-row__name {
  font-size: 14px;
  font-weight: 600;
  overflow-wrap: anywhere;
}
.session-row__origin {
  font-size: 11px;
  opacity: 0.5;
  overflow-wrap: anywhere;
}
.session-row__source {
  font-size: 11px;
  color: rgb(var(--v-theme-primary));
}
.session-index__empty {
  padding: 24px 12px;
  font-size: 13px;
  color: rgba(var(--v-theme-on-surface), 0.5);
  text-align: center;
}
button:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: 3px;
}
@media (max-width: 720px) {
  .session-workspace {
    padding: 0;
  }
  .session-toolbar {
    gap: 4px;
    padding: 4px 0 12px;
  }
  .session-picker {
    max-width: 55%;
  }
  .session-toolbar__actions {
    gap: 4px;
  }
  .session-editor__footer {
    flex-wrap: wrap;
    gap: 10px;
  }
  .session-save-actions {
    flex: 1;
  }
}
@media (max-width: 420px) {
  .session-save-actions {
    flex-basis: 100%;
    justify-content: flex-end;
  }
}
</style>
