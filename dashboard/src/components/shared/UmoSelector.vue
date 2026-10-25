<template>
  <div class="umo-selector">
    <slot name="activator" :open="openDialog">
      <v-text-field
        :model-value="selectionText"
        :label="label || t('core.common.umoSelector.title')"
        :title="selectedValues.join('\n')"
        :disabled="disabled"
        readonly
        hide-details
        variant="outlined"
        density="compact"
        @click="openDialog"
        @keydown.enter.prevent="openDialog"
        @keydown.space.prevent="openDialog"
      >
        <template #append-inner>
          <v-btn
            v-if="clearable && selectedValues.length && !readonly"
            icon="mdi-close"
            variant="text"
            size="x-small"
            :disabled="disabled"
            :aria-label="t('core.common.umoSelector.clear')"
            @click.stop="emit('update:modelValue', multiple ? [] : '')"
          />
          <v-icon>mdi-unfold-more-horizontal</v-icon>
        </template>
      </v-text-field>
    </slot>

    <v-dialog v-model="dialog" max-width="900px" scrollable>
      <v-card>
        <v-card-title class="text-h3 pa-4 pb-0 pl-6">{{
          t("core.common.umoSelector.title")
        }}</v-card-title>
        <v-card-text class="pt-4">
          <p class="text-body-2 text-medium-emphasis mb-4">
            {{ t("core.common.umoSelector.hint") }}
          </p>
          <v-chip v-if="platformId" size="small" variant="tonal" class="mb-4">{{
            platformId
          }}</v-chip>
          <v-row>
            <v-col cols="12" md="5">
              <div class="d-flex align-center justify-space-between mb-2">
                <span class="text-subtitle-1">{{
                  t("core.common.umoSelector.selected", { count: draft.length })
                }}</span>
                <v-btn
                  v-if="draft.length"
                  variant="text"
                  size="small"
                  @click="draft = []"
                >
                  {{ t("core.common.umoSelector.clear") }}
                </v-btn>
              </div>
              <v-list
                v-if="draft.length"
                class="umo-selector-list umo-selection rounded-lg"
                density="compact"
              >
                <v-list-item v-for="umo in draft" :key="umo" class="py-2">
                  <UmoDisplay
                    :umo="umo"
                    :platform-type="botTypes[umo.split(':')[0]] || ''"
                    :auto-name="infos[umo]?.auto_name || ''"
                    :user-alias="infos[umo]?.user_alias || ''"
                    :show-platform="umo.includes(':')"
                    compact
                    :show-info="false"
                  />
                  <template #append>
                    <v-btn
                      icon="mdi-close"
                      variant="text"
                      size="x-small"
                      :aria-label="t('core.common.umoSelector.remove', { umo })"
                      @click="draft = draft.filter((value) => value !== umo)"
                    />
                  </template>
                </v-list-item>
              </v-list>
              <div
                v-else
                class="umo-selection rounded-lg pa-6 text-medium-emphasis text-center"
              >
                {{ t("core.common.list.noItems") }}
              </div>
            </v-col>
            <v-col cols="12" md="7">
              <v-tabs
                v-model="mode"
                color="primary"
                density="compact"
                class="mb-4"
              >
                <v-tab value="known">{{
                  t("core.common.umoSelector.known")
                }}</v-tab>
                <v-tab v-if="allowManual" value="manual">{{
                  t("core.common.umoSelector.manual")
                }}</v-tab>
              </v-tabs>
              <div v-if="mode === 'known'">
                <v-text-field
                  v-model="search"
                  :label="t('core.common.umoSelector.search')"
                  prepend-inner-icon="mdi-magnify"
                  variant="outlined"
                  density="compact"
                  hide-details
                  clearable
                >
                  <template #append-inner>
                    <v-btn
                      icon="mdi-refresh"
                      variant="text"
                      size="x-small"
                      :loading="loading"
                      :disabled="loading"
                      :aria-label="t('core.common.umoSelector.refresh')"
                      :title="t('core.common.umoSelector.refresh')"
                      @click.stop="loadUmos"
                    />
                  </template>
                </v-text-field>
                <v-progress-linear
                  v-if="loading"
                  indeterminate
                  color="primary"
                  class="mt-2"
                />
                <v-alert
                  v-if="failed"
                  type="warning"
                  variant="tonal"
                  density="compact"
                  class="mt-3"
                >
                  {{ t("core.common.umoSelector.loadError") }}
                  <v-btn variant="text" size="small" @click="loadUmos">{{
                    t("core.common.reload")
                  }}</v-btn>
                </v-alert>
                <v-list
                  v-if="filteredUmos.length"
                  class="umo-selector-list mt-2"
                  density="compact"
                >
                  <v-list-item
                    v-for="umo in filteredUmos.slice(0, visibleLimit)"
                    :key="umo"
                    :active="draft.includes(umo)"
                    color="primary"
                    rounded="lg"
                    class="py-2 mb-1"
                    @click="toggleUmo(umo)"
                  >
                    <template #prepend>
                      <v-checkbox-btn
                        v-if="multiple"
                        :model-value="draft.includes(umo)"
                        :aria-label="umo"
                        color="primary"
                        @click.stop="toggleUmo(umo)"
                      />
                      <v-icon
                        v-else
                        class="mr-3"
                        :color="draft.includes(umo) ? 'primary' : undefined"
                      >
                        {{
                          draft.includes(umo)
                            ? "mdi-radiobox-marked"
                            : "mdi-radiobox-blank"
                        }}
                      </v-icon>
                    </template>
                    <UmoDisplay
                      :umo="umo"
                      :platform-type="botTypes[umo.split(':')[0]] || ''"
                      :auto-name="infos[umo]?.auto_name || ''"
                      :user-alias="infos[umo]?.user_alias || ''"
                      compact
                      :show-info="false"
                    />
                  </v-list-item>
                  <v-btn
                    v-if="filteredUmos.length > visibleLimit"
                    block
                    variant="text"
                    @click="visibleLimit += 50"
                  >
                    {{ t("core.common.umoSelector.loadMore") }}
                  </v-btn>
                </v-list>
                <p
                  v-else-if="!loading && !failed"
                  class="text-body-2 text-medium-emphasis py-6 text-center"
                >
                  {{ t("core.common.umoSelector.empty") }}
                </p>
              </div>
              <div v-else>
                <v-textarea
                  v-model="manual"
                  :label="t('core.common.umoSelector.manualLabel')"
                  :hint="t('core.common.umoSelector.manualHint')"
                  :error-messages="manualError"
                  variant="outlined"
                  rows="5"
                  persistent-hint
                />
                <v-btn
                  :disabled="!manual.trim()"
                  variant="tonal"
                  color="primary"
                  class="mt-4"
                  @click="addManual"
                >
                  {{ t("core.common.list.addButton") }}
                </v-btn>
              </div>
            </v-col>
          </v-row>
        </v-card-text>
        <v-card-actions class="pa-4">
          <v-spacer />
          <v-btn variant="text" @click="dialog = false">{{
            t("core.common.cancel")
          }}</v-btn>
          <v-btn
            :disabled="disabled || readonly"
            variant="tonal"
            color="primary"
            @click="confirmSelection"
          >
            {{ t("core.common.confirm") }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { conversationApi, sessionApi } from "@/api/v1";
import { useI18n } from "@/i18n/composables";
import UmoDisplay from "./UmoDisplay.vue";

const props = defineProps({
  modelValue: { type: [String, Array], default: "" },
  multiple: { type: Boolean, default: false },
  label: { type: String, default: "" },
  platformId: { type: String, default: "" },
  excludedUmos: { type: Array, default: () => [] },
  items: { type: Array, default: null },
  allowManual: { type: Boolean, default: true },
  clearable: { type: Boolean, default: true },
  readonly: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
});
const emit = defineEmits(["update:modelValue", "loaded"]);
const { t } = useI18n();
const dialog = ref(false);
const draft = ref([]);
const umos = ref([]);
const infos = ref({});
const search = ref("");
const mode = ref("known");
const manual = ref("");
const manualError = ref("");
const loading = ref(false);
const failed = ref(false);
const visibleLimit = ref(50);
const botTypes = ref({});
let loadVersion = 0;

watch(dialog, async (opened, _previous, onCleanup) => {
  if (!opened) return;
  let active = true;
  onCleanup(() => {
    active = false;
  });
  try {
    const response = await conversationApi.filterOptions();
    if (active && response.data.status === "ok") {
      botTypes.value = Object.fromEntries(
        (response.data.data?.bots || []).map((bot) => [bot.id, bot.type]),
      );
    }
  } catch {
    // Platform logos are optional; selection remains available without metadata.
  }
});

const selectedValues = computed(() =>
  (Array.isArray(props.modelValue)
    ? props.modelValue
    : props.modelValue
    ? [props.modelValue]
    : []
  )
    .map((value) => String(value ?? "").trim())
    .filter(Boolean),
);
const selectionText = computed(() =>
  selectedValues.value
    .map(
      (umo) =>
        infos.value[umo]?.user_alias || infos.value[umo]?.auto_name || umo,
    )
    .join(", "),
);
const filteredUmos = computed(() => {
  const query = (search.value || "").toLowerCase().trim();
  const excluded = new Set(props.excludedUmos);
  const allowed = new Set(props.items ?? umos.value);
  return [...new Set([...umos.value, ...allowed])].filter((umo) => {
    if (
      !allowed.has(umo) ||
      excluded.has(umo) ||
      (props.platformId && umo.split(":")[0] !== props.platformId)
    )
      return false;
    const info = infos.value[umo] || {};
    return (
      !query ||
      [umo, info.auto_name, info.user_alias, info.display_name].some((value) =>
        String(value || "")
          .toLowerCase()
          .includes(query),
      )
    );
  });
});

watch(search, () => {
  visibleLimit.value = 50;
});
watch(
  () => props.platformId,
  (_value, previous) => {
    loadVersion++;
    infos.value = {};
    umos.value = [];
    if (previous !== undefined) dialog.value = false;
    void loadUmos();
  },
  { immediate: true },
);
onBeforeUnmount(() => {
  loadVersion++;
});

async function loadUmos() {
  const version = ++loadVersion;
  const platformId = props.platformId;
  loading.value = true;
  failed.value = false;
  try {
    const response = await sessionApi.activeUmos(
      platformId ? { platform_id: platformId } : undefined,
    );
    if (version !== loadVersion) return;
    if (response.data.status !== "ok") throw new Error(response.data.message);
    const data = response.data.data;
    umos.value = (data.umos || []).filter(
      (umo) => !platformId || umo.split(":")[0] === platformId,
    );
    infos.value = Object.fromEntries(
      (data.umo_infos || [])
        .filter((info) => !platformId || info.umo?.split(":")[0] === platformId)
        .map((info) => [info.umo, info]),
    );
    emit("loaded", Object.values(infos.value));
  } catch {
    if (version === loadVersion) failed.value = true;
  } finally {
    if (version === loadVersion) loading.value = false;
  }
}

function openDialog() {
  if (props.disabled || props.readonly) return;
  draft.value = [...new Set(selectedValues.value)];
  search.value = "";
  mode.value = "known";
  manual.value = "";
  manualError.value = "";
  visibleLimit.value = 50;
  dialog.value = true;
  void loadUmos();
}

function toggleUmo(umo) {
  if (props.disabled || props.readonly || !filteredUmos.value.includes(umo))
    return;
  draft.value = props.multiple
    ? draft.value.includes(umo)
      ? draft.value.filter((value) => value !== umo)
      : [...draft.value, umo]
    : [umo];
}

function addManual() {
  if (props.disabled || props.readonly || !props.allowManual) return;
  const values = [
    ...new Set(
      manual.value
        .split("\n")
        .map((value) => value.trim())
        .filter(Boolean),
    ),
  ];
  if (
    (!props.multiple && values.length > 1) ||
    values.some(
      (umo) =>
        props.excludedUmos.includes(umo) ||
        (props.platformId &&
          (umo.split(":")[0] !== props.platformId ||
            umo.split(":").length < 3)),
    )
  ) {
    manualError.value = t("core.common.umoSelector.invalidManual");
    return;
  }
  draft.value = props.multiple
    ? [...new Set([...draft.value, ...values])]
    : values;
  manual.value = "";
  manualError.value = "";
}

function confirmSelection() {
  if (
    props.disabled ||
    props.readonly ||
    draft.value.some(
      (umo) => props.platformId && umo.split(":")[0] !== props.platformId,
    )
  )
    return;
  emit(
    "update:modelValue",
    props.multiple ? [...draft.value] : draft.value[0] || "",
  );
  dialog.value = false;
}

defineExpose({ openDialog });
</script>

<style scoped>
.umo-selector {
  min-width: 0;
  width: 100%;
}

.umo-selector-list {
  max-height: 360px;
  overflow-y: auto;
}

.umo-selection {
  border: 1px solid rgba(var(--v-theme-on-surface), 0.16);
}
</style>
