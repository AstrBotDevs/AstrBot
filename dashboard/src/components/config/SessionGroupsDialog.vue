<template>
  <v-dialog
    :model-value="modelValue"
    @update:model-value="emit('update:modelValue', $event)"
    :persistent="groupSaving"
    max-width="640"
    scrollable
  >
    <v-card>
      <v-card-title class="text-h3 pa-4 pb-0 pl-6">{{
        tm("groups")
      }}</v-card-title>
      <v-card-text>
        <v-alert v-if="error" type="error" variant="tonal" class="mb-4">{{
          error
        }}</v-alert>
        <p class="text-body-2 mb-4">{{ tm("groupHint") }}</p>
        <v-list v-if="!editingGroup">
          <v-list-item
            v-for="group in groups"
            :key="group.id"
            :title="group.name"
            :subtitle="tm('members', { count: group.umos.length })"
          >
            <template #append
              ><v-btn
                icon="mdi-pencil-outline"
                variant="text"
                :aria-label="tm('edit')"
                @click="
                  editingGroup = JSON.parse(JSON.stringify(group))
                " /><v-btn
                icon="mdi-delete-outline"
                variant="text"
                :aria-label="tm('delete')"
                @click="deleteGroup(group)"
            /></template>
          </v-list-item>
        </v-list>
        <template v-if="editingGroup">
          <v-text-field
            v-model="editingGroup.name"
            :label="tm('groupName')"
            variant="outlined"
          />
          <UmoSelector v-model="editingGroup.umos" :multiple="true" />
        </template>
      </v-card-text>
      <v-card-actions
        ><v-btn
          v-if="!editingGroup"
          variant="tonal"
          @click="editingGroup = { name: '', umos: [] }"
          >{{ tm("newGroup") }}</v-btn
        ><v-spacer /><v-btn
          variant="text"
          @click="
            editingGroup
              ? (editingGroup = null)
              : emit('update:modelValue', false)
          "
          >{{ tm("cancel") }}</v-btn
        ><v-btn
          v-if="editingGroup"
          variant="tonal"
          color="primary"
          :disabled="!editingGroup.name.trim() || groupSaving"
          :loading="groupSaving"
          @click="saveGroup"
          >{{ tm("save") }}</v-btn
        ></v-card-actions
      >
    </v-card>
  </v-dialog>
</template>
<script setup lang="ts">
import { ref, watch } from "vue";
import { sessionApi } from "@/api/v1";
import UmoSelector from "@/components/shared/UmoSelector.vue";
import { useModuleI18n } from "@/i18n/composables";
import { askForConfirmation, useConfirmDialog } from "@/utils/confirmDialog";
const props = defineProps<{ modelValue: boolean }>();
const emit = defineEmits<{
  "update:modelValue": [value: boolean];
  changed: [];
}>();
const { tm: configTm } = useModuleI18n("features.config");
const tm = (key: string, params?: Record<string, any>) =>
  configTm(`overrides.${key}`, params);
const confirmDialog = useConfirmDialog();
const groups = ref<any[]>([]);
const editingGroup = ref<any>(null);
const groupSaving = ref(false);
const error = ref("");
async function loadGroups() {
  const response = await sessionApi.listGroups();
  if (response.data.status !== "ok")
    throw new Error(response.data.message || tm("error"));
  groups.value = response.data.data.groups;
}
async function saveGroup() {
  groupSaving.value = true;
  try {
    const group = editingGroup.value;
    const response = group.id
      ? await sessionApi.updateGroup(group.id, {
          name: group.name,
          umos: group.umos,
        })
      : await sessionApi.createGroup({ name: group.name, umos: group.umos });
    if (response.data.status !== "ok")
      throw new Error(response.data.message || tm("error"));
    await loadGroups();
    emit("changed");
    editingGroup.value = null;
  } catch (err: any) {
    error.value = err.message || tm("error");
  } finally {
    groupSaving.value = false;
  }
}
async function deleteGroup(group: any) {
  if (
    !(await askForConfirmation(
      tm("deleteGroupConfirm", { name: group.name }),
      confirmDialog,
    ))
  )
    return;
  try {
    const response = await sessionApi.deleteGroup(group.id);
    if (response.data.status !== "ok")
      throw new Error(response.data.message || tm("error"));
    await loadGroups();
    emit("changed");
  } catch (err: any) {
    error.value = err.message || tm("error");
  }
}

watch(
  () => props.modelValue,
  async (open) => {
    if (!open) return;
    error.value = "";
    editingGroup.value = null;
    try {
      await loadGroups();
    } catch (err: any) {
      error.value = err.message || tm("error");
    }
  },
);
</script>
