<template>
  <div class="d-flex align-center ga-3">
    <div class="d-flex flex-wrap ga-1 flex-grow-1" style="min-width: 0">
      <span v-if="!modelValue.length" class="text-medium-emphasis text-body-2">
        {{ t("core.common.list.noItems") }}
      </span>
      <v-chip
        v-for="id in modelValue.slice(0, 3)"
        :key="id"
        :title="id"
        size="small"
        color="primary"
        variant="tonal"
        class="sender-chip"
      >
        <span class="text-truncate">{{ known[id]?.sender_name || id }}</span>
      </v-chip>
      <v-chip v-if="modelValue.length > 3" size="small" variant="tonal">
        +{{ modelValue.length - 3 }}
      </v-chip>
    </div>
    <v-btn
      :disabled="readonly"
      size="small"
      variant="tonal"
      color="primary"
      @click="openDialog"
    >
      {{ t("core.common.list.senderManage") }}
    </v-btn>
  </div>

  <v-dialog v-model="dialog" max-width="860px" scrollable>
    <v-card>
      <v-card-title class="text-h3 pa-4 pb-0 pl-6">
        {{ t("core.common.list.senderTitle") }}
      </v-card-title>
      <v-card-text class="pt-4">
        <p class="text-body-2 text-medium-emphasis mb-4">
          {{ t("core.common.list.senderHint") }}
        </p>
        <v-row>
          <v-col cols="12" md="5">
            <div class="text-subtitle-1 mb-2">
              {{
                t("core.common.list.senderSelected", { count: draft.length })
              }}
            </div>
            <v-list
              v-if="draft.length"
              class="sender-list sender-selection rounded-lg"
              density="compact"
            >
              <v-list-item v-for="id in draft" :key="id" class="py-2">
                <v-list-item-title class="sender-title">
                  {{ known[id]?.sender_name || id }}
                  <span
                    v-if="known[id]?.sender_name"
                    class="sender-id text-caption"
                    >({{ id }})</span
                  >
                </v-list-item-title>
                <div
                  class="d-flex align-center ga-1 text-caption text-medium-emphasis text-break"
                >
                  <PlatformLogo
                    :platform-type="
                      botTypes[known[id]?.platform] || known[id]?.platform || ''
                    "
                  />
                  <span>
                    {{
                      known[id]?.platform || t("core.common.list.senderUnknown")
                    }}
                  </span>
                </div>
                <template #append>
                  <v-btn
                    icon="mdi-close"
                    variant="text"
                    size="x-small"
                    :disabled="readonly"
                    :aria-label="t('core.common.list.senderRemove', { id })"
                    @click="draft = draft.filter((value) => value !== id)"
                  />
                </template>
              </v-list-item>
            </v-list>
            <div
              v-else
              class="sender-selection rounded-lg pa-6 text-body-2 text-medium-emphasis text-center"
            >
              {{ t("core.common.list.noItems") }}
            </div>
          </v-col>

          <v-col cols="12" md="7">
            <div>
              <v-text-field
                v-model="search"
                :label="t('core.common.list.senderSearch')"
                prepend-inner-icon="mdi-magnify"
                variant="outlined"
                density="compact"
                hide-details
                clearable
                maxlength="512"
              >
                <template #append-inner>
                  <v-btn
                    icon="mdi-refresh"
                    variant="text"
                    size="x-small"
                    :loading="loading"
                    :disabled="loading"
                    :aria-label="t('core.common.list.senderRefresh')"
                    :title="t('core.common.list.senderRefresh')"
                    @click.stop="refreshVersion++"
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
                {{ t("core.common.list.senderLoadError") }}
              </v-alert>
              <v-list
                v-if="suggestions.length"
                class="sender-list mt-2"
                density="compact"
              >
                <v-list-item
                  v-for="sender in suggestions"
                  :key="JSON.stringify([sender.umo, sender.sender_id])"
                  :active="draft.includes(sender.sender_id)"
                  :disabled="readonly"
                  color="primary"
                  rounded="lg"
                  class="py-2 mb-1"
                  @click="toggleSender(sender)"
                >
                  <template #prepend>
                    <v-checkbox-btn
                      :model-value="draft.includes(sender.sender_id)"
                      :disabled="readonly"
                      :aria-label="`${
                        sender.sender_name || sender.sender_id
                      } (${sender.sender_id})`"
                      color="primary"
                      @click.stop="toggleSender(sender)"
                    />
                  </template>
                  <v-list-item-title class="sender-title">
                    {{ sender.sender_name || sender.sender_id }}
                    <span
                      v-if="sender.sender_name"
                      class="sender-id text-caption"
                      >({{ sender.sender_id }})</span
                    >
                  </v-list-item-title>
                  <div
                    class="d-flex align-center ga-1 text-caption text-medium-emphasis text-break"
                  >
                    <PlatformLogo
                      :platform-type="
                        botTypes[sender.platform] || sender.platform
                      "
                    />
                    <span>{{ sender.platform }}</span>
                  </div>
                </v-list-item>
              </v-list>
              <div v-else-if="!loading" class="py-6 text-center">
                <p v-if="!failed" class="text-body-2 text-medium-emphasis">
                  {{ t("core.common.list.senderEmpty") }}
                </p>
                <v-btn
                  v-if="canAddSearch"
                  variant="tonal"
                  color="primary"
                  class="mt-4 sender-add-button"
                  @click="addSearchId"
                >
                  {{ t("core.common.list.senderAddId", { id: search.trim() }) }}
                </v-btn>
              </div>
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
          :disabled="readonly"
          variant="tonal"
          color="primary"
          @click="confirmSelection"
        >
          {{ t("core.common.confirm") }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup>
import { computed, ref, watch } from "vue";
import { conversationApi, sessionApi } from "@/api/v1";
import { useI18n } from "@/i18n/composables";
import PlatformLogo from "./PlatformLogo.vue";

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  readonly: { type: Boolean, default: false },
});
const emit = defineEmits(["update:modelValue"]);
const { t } = useI18n();
const dialog = ref(false);
const draft = ref([]);
const search = ref("");
const known = ref({});
const suggestions = ref([]);
const loading = ref(false);
const failed = ref(false);
const refreshVersion = ref(0);
const botTypes = ref({});

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

const canAddSearch = computed(
  () =>
    dialog.value &&
    !props.readonly &&
    !loading.value &&
    !suggestions.value.length &&
    Boolean((search.value || "").trim()) &&
    !draft.value.includes(search.value.trim()),
);

// Resolve saved IDs in batches; manually entered or unknown IDs remain usable.
watch(
  () => props.modelValue,
  async (ids, _previous, onCleanup) => {
    let active = true;
    onCleanup(() => {
      active = false;
    });
    const uniqueIds = [...new Set(ids.map(String))];
    for (let offset = 0; offset < uniqueIds.length; offset += 100) {
      try {
        const response = await sessionApi.senders({
          sender_ids: uniqueIds.slice(offset, offset + 100),
          limit: 100,
        });
        if (!active || response.data.status !== "ok") return;
        for (const sender of response.data.data.senders)
          known.value[sender.sender_id] = sender;
      } catch {
        return;
      }
    }
  },
  { immediate: true, deep: true },
);

watch(
  [dialog, search, refreshVersion],
  ([opened, value, version], previous, onCleanup) => {
    if (!opened) return;
    let active = true;
    loading.value = true;
    failed.value = false;
    suggestions.value = [];
    const timer = setTimeout(
      async () => {
        try {
          const response = await sessionApi.senders({
            search: value || "",
            limit: 50,
          });
          if (!active) return;
          if (response.data.status !== "ok")
            throw new Error(response.data.message);
          suggestions.value = response.data.data.senders;
        } catch {
          if (active) failed.value = true;
        } finally {
          if (active) loading.value = false;
        }
      },
      value && version === previous[2] ? 250 : 0,
    );
    onCleanup(() => {
      active = false;
      clearTimeout(timer);
    });
  },
);

function openDialog() {
  if (props.readonly) return;
  draft.value = [
    ...new Set(
      props.modelValue.map((id) => String(id ?? "").trim()).filter(Boolean),
    ),
  ];
  search.value = "";
  dialog.value = true;
}

function toggleSender(sender) {
  if (props.readonly) return;
  known.value[sender.sender_id] = sender;
  draft.value = draft.value.includes(sender.sender_id)
    ? draft.value.filter((id) => id !== sender.sender_id)
    : [...draft.value, sender.sender_id];
}

function addSearchId() {
  if (!canAddSearch.value) return;
  draft.value.push(search.value.trim());
  search.value = "";
}

function confirmSelection() {
  if (props.readonly) return;
  emit("update:modelValue", [...draft.value]);
  dialog.value = false;
}
</script>

<style scoped>
.sender-selection {
  border: 1px solid rgba(var(--v-theme-on-surface), 0.16);
}

.sender-add-button {
  max-width: 100%;
  height: auto;
  min-height: 36px;
  white-space: normal;
  overflow-wrap: anywhere;
}

.sender-chip {
  max-width: 180px;
}

.sender-list {
  max-height: 360px;
  overflow-y: auto;
}

.sender-title {
  white-space: normal;
  overflow-wrap: anywhere;
}

.sender-id {
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity));
}
</style>
