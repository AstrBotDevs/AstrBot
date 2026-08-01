<template>
  <v-dialog
    v-model="showDialog"
    :max-width="$vuetify.display.smAndDown ? undefined : '1200px'"
    scrollable
    persistent
  >
    <v-card
      class="persona-form-card"
      :class="{ 'persona-form-card-mobile': $vuetify.display.smAndDown }"
    >
      <v-card-title class="persona-form-title text-h3 pa-4 pb-0 pl-6">
        {{
          editingPersona ? tm("dialog.edit.title") : tm("dialog.create.title")
        }}
      </v-card-title>

      <v-card-text class="persona-form-content">
        <v-alert
          v-if="!editingPersona"
          type="info"
          variant="tonal"
          density="compact"
          class="mb-4"
          icon="mdi-folder-outline"
        >
          {{ tm("form.createInFolder", { folder: folderDisplayName }) }}
        </v-alert>

        <v-form v-model="formValid">
          <v-row class="persona-form-layout">
            <v-col cols="12" md="6" class="persona-basic-col">
              <v-text-field
                v-model="personaForm.persona_id"
                :label="tm('form.personaId')"
                :rules="personaIdRules"
                :disabled="Boolean(editingPersona)"
                variant="outlined"
                density="comfortable"
                class="mb-4"
              />

              <v-textarea
                v-model="personaForm.system_prompt"
                :label="tm('form.systemPrompt')"
                :rules="systemPromptRules"
                variant="outlined"
                rows="16"
                class="mb-4"
              />

              <v-textarea
                v-model="personaForm.custom_error_message"
                :label="tm('form.customErrorMessage')"
                :hint="tm('form.customErrorMessageHelp')"
                variant="outlined"
                rows="4"
                persistent-hint
                clearable
                class="mb-4"
              />
            </v-col>

            <v-col cols="12" md="6" class="persona-panels-col">
              <section class="persona-capabilities-section">
                <h3 class="persona-section-title">
                  {{ tm("form.capabilities") }}
                </h3>
                <p class="persona-section-description">
                  {{ tm("form.capabilitiesHelp") }}
                </p>
                <PersonaCapabilitiesEditor
                  v-model:tools="personaForm.tools"
                  v-model:skills="personaForm.skills"
                  :available-tools="availableTools"
                  :available-skills="availableSkills"
                  :loading-tools="loadingTools"
                  :loading-skills="loadingSkills"
                />
              </section>

              <v-expansion-panels
                v-model="expandedPanels"
                multiple
                class="persona-dialogs-panels"
              >
                <v-expansion-panel value="dialogs" elevation="0">
                  <v-expansion-panel-title>
                    <v-icon class="mr-2">mdi-chat</v-icon>
                    {{ tm("form.presetDialogs") }}
                    <v-chip
                      v-if="personaForm.begin_dialogs.length > 0"
                      size="small"
                      color="primary"
                      variant="tonal"
                      class="ml-2"
                    >
                      {{ personaForm.begin_dialogs.length / 2 }}
                    </v-chip>
                  </v-expansion-panel-title>

                  <v-expansion-panel-text>
                    <p class="text-body-2 text-medium-emphasis mb-3">
                      {{ tm("form.presetDialogsHelp") }}
                    </p>

                    <v-textarea
                      v-for="(dialog, index) in personaForm.begin_dialogs"
                      :key="index"
                      v-model="personaForm.begin_dialogs[index]"
                      :label="
                        index % 2 === 0
                          ? tm('form.userMessage')
                          : tm('form.assistantMessage')
                      "
                      :rules="getDialogRules(index)"
                      variant="outlined"
                      rows="2"
                      density="comfortable"
                      class="mb-3"
                    >
                      <template #append>
                        <v-btn
                          icon="mdi-delete"
                          variant="text"
                          size="small"
                          color="error"
                          @click="removeDialog(index)"
                        />
                      </template>
                    </v-textarea>

                    <v-btn
                      color="primary"
                      variant="tonal"
                      prepend-icon="mdi-plus"
                      block
                      @click="addDialogPair"
                    >
                      {{ tm("buttons.addDialogPair") }}
                    </v-btn>
                  </v-expansion-panel-text>
                </v-expansion-panel>
              </v-expansion-panels>
            </v-col>
          </v-row>
        </v-form>
      </v-card-text>

      <v-card-actions class="persona-form-actions">
        <v-btn
          v-if="editingPersona"
          color="error"
          variant="text"
          @click="deletePersona"
        >
          {{ tm("buttons.delete") }}
        </v-btn>
        <v-spacer />
        <v-btn color="grey" variant="text" @click="closeDialog">
          {{ tm("buttons.cancel") }}
        </v-btn>
        <v-btn
          color="primary"
          variant="tonal"
          :loading="saving"
          :disabled="!formValid"
          @click="savePersona"
        >
          {{ tm("buttons.save") }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup>
import { computed, reactive, ref, watch } from "vue";
import { useDisplay } from "vuetify";
import { personaApi, skillApi, toolApi } from "@/api/v1";
import { useModuleI18n } from "@/i18n/composables";
import {
  askForConfirmation as askForConfirmationDialog,
  useConfirmDialog,
} from "@/utils/confirmDialog";
import PersonaCapabilitiesEditor from "./PersonaCapabilitiesEditor.vue";

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false,
  },
  editingPersona: {
    type: Object,
    default: null,
  },
  currentFolderId: {
    type: String,
    default: null,
  },
  currentFolderName: {
    type: String,
    default: null,
  },
});

const emit = defineEmits(["update:modelValue", "saved", "error", "deleted"]);
const { tm } = useModuleI18n("features/persona");
const confirmDialog = useConfirmDialog();
const { smAndDown } = useDisplay();

const saving = ref(false);
const formValid = ref(false);
const expandedPanels = ref([]);
const availableTools = ref([]);
const availableSkills = ref([]);
const loadingTools = ref(false);
const loadingSkills = ref(false);
const existingPersonaIds = ref([]);
const personaForm = reactive({
  persona_id: "",
  system_prompt: "",
  custom_error_message: "",
  begin_dialogs: [],
  tools: null,
  skills: null,
  folder_id: null,
});

const showDialog = computed({
  get: () => props.modelValue,
  set: (value) => emit("update:modelValue", value),
});
const folderDisplayName = computed(
  () =>
    props.currentFolderName || props.currentFolderId || tm("form.rootFolder"),
);
const personaIdRules = computed(() => [
  (value) => Boolean(value) || tm("validation.required"),
  (value) =>
    (value && value.length >= 1) || tm("validation.minLength", { min: 1 }),
  (value) =>
    props.editingPersona?.persona_id === value ||
    !existingPersonaIds.value.includes(value) ||
    tm("validation.personaIdExists"),
]);
const systemPromptRules = computed(() => [
  (value) => Boolean(value) || tm("validation.required"),
  (value) =>
    (value && value.length >= 10) || tm("validation.minLength", { min: 10 }),
]);

function initializeForm(persona = null) {
  Object.assign(personaForm, {
    persona_id: persona?.persona_id || "",
    system_prompt: persona?.system_prompt || "",
    custom_error_message: persona?.custom_error_message || "",
    begin_dialogs: [...(persona?.begin_dialogs || [])],
    tools:
      persona?.tools === null || !persona ? null : [...(persona.tools || [])],
    skills:
      persona?.skills === null || !persona ? null : [...(persona.skills || [])],
    folder_id: persona?.folder_id ?? props.currentFolderId,
  });
  expandedPanels.value = smAndDown.value ? [] : ["dialogs"];
}

function closeDialog() {
  showDialog.value = false;
}

async function loadTools() {
  loadingTools.value = true;
  try {
    const response = await toolApi.list();
    if (response.data?.status === "ok") {
      availableTools.value = response.data?.data || [];
    } else {
      availableTools.value = [];
      emit("error", response.data?.message || "Failed to load tools");
    }
  } catch (error) {
    availableTools.value = [];
    emit("error", error?.response?.data?.message || "Failed to load tools");
  } finally {
    loadingTools.value = false;
  }
}

async function loadSkills() {
  loadingSkills.value = true;
  try {
    const response = await skillApi.list();
    if (response.data?.status === "ok") {
      const payload = response.data?.data || [];
      const skills = Array.isArray(payload) ? payload : payload.skills || [];
      availableSkills.value = skills.filter((skill) => skill.active !== false);
    } else {
      availableSkills.value = [];
      emit("error", response.data?.message || "Failed to load skills");
    }
  } catch (error) {
    availableSkills.value = [];
    emit("error", error?.response?.data?.message || "Failed to load skills");
  } finally {
    loadingSkills.value = false;
  }
}

async function loadExistingPersonaIds() {
  try {
    const response = await personaApi.list();
    existingPersonaIds.value =
      response.data?.status === "ok"
        ? (response.data?.data || []).map((persona) => persona.persona_id)
        : [];
  } catch {
    existingPersonaIds.value = [];
  }
}

async function savePersona() {
  if (!formValid.value) {
    return;
  }
  for (let index = 0; index < personaForm.begin_dialogs.length; index += 1) {
    if (!personaForm.begin_dialogs[index]?.trim()) {
      const dialogType =
        index % 2 === 0 ? tm("form.userMessage") : tm("form.assistantMessage");
      emit("error", tm("validation.dialogRequired", { type: dialogType }));
      return;
    }
  }

  saving.value = true;
  const payload = {
    ...personaForm,
    begin_dialogs: [...personaForm.begin_dialogs],
    tools: personaForm.tools === null ? null : [...personaForm.tools],
    skills: personaForm.skills === null ? null : [...personaForm.skills],
  };
  try {
    const response = props.editingPersona
      ? await personaApi.update(personaForm.persona_id, payload)
      : await personaApi.create(payload);
    if (response.data?.status === "ok") {
      emit("saved", response.data?.message || tm("messages.saveSuccess"));
      window.dispatchEvent(new CustomEvent("astrbot:persona-saved"));
      closeDialog();
    } else {
      emit("error", response.data?.message || tm("messages.saveError"));
    }
  } catch (error) {
    emit("error", error?.response?.data?.message || tm("messages.saveError"));
  } finally {
    saving.value = false;
  }
}

async function deletePersona() {
  if (!props.editingPersona) {
    return;
  }
  if (
    !(await askForConfirmationDialog(
      tm("messages.deleteConfirm", { id: props.editingPersona.persona_id }),
      confirmDialog,
    ))
  ) {
    return;
  }

  saving.value = true;
  try {
    const response = await personaApi.delete(props.editingPersona.persona_id);
    if (response.data?.status === "ok") {
      emit("deleted", response.data?.message || tm("messages.deleteSuccess"));
      closeDialog();
    } else {
      emit("error", response.data?.message || tm("messages.deleteError"));
    }
  } catch (error) {
    emit("error", error?.response?.data?.message || tm("messages.deleteError"));
  } finally {
    saving.value = false;
  }
}

function addDialogPair() {
  personaForm.begin_dialogs.push("", "");
  if (!expandedPanels.value.includes("dialogs")) {
    expandedPanels.value.push("dialogs");
  }
}

function removeDialog(index) {
  personaForm.begin_dialogs.splice(index % 2 === 0 ? index : index - 1, 2);
}

function getDialogRules(index) {
  const dialogType =
    index % 2 === 0 ? tm("form.userMessage") : tm("form.assistantMessage");
  return [
    (value) =>
      Boolean(value) || tm("validation.dialogRequired", { type: dialogType }),
    (value) =>
      Boolean(value?.trim()) ||
      tm("validation.dialogRequired", { type: dialogType }),
  ];
}

watch(
  () => props.modelValue,
  (open) => {
    if (!open) {
      return;
    }
    initializeForm(props.editingPersona);
    if (!props.editingPersona) {
      loadExistingPersonaIds();
    }
    loadTools();
    loadSkills();
  },
  { immediate: true },
);

watch(
  () => props.editingPersona,
  (persona) => {
    if (props.modelValue) {
      initializeForm(persona);
    }
  },
);
</script>

<style scoped>
.persona-form-card {
  overflow: hidden;
  border-radius: 12px;
}

.persona-form-content {
  max-height: min(82vh, 860px);
  overflow-y: auto;
}

.persona-form-actions {
  position: sticky;
  z-index: 2;
  bottom: 0;
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  background: rgb(var(--v-theme-surface));
}

.persona-form-layout {
  align-items: flex-start;
}

.persona-capabilities-section {
  min-width: 0;
}

.persona-panels-col {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.persona-section-title {
  margin-bottom: 4px;
  font-size: 1rem;
  font-weight: 600;
  line-height: 1.5;
}

.persona-section-description {
  margin-bottom: 12px;
  color: rgb(var(--v-theme-on-surface));
  font-size: 0.82rem;
  opacity: 0.65;
}

.persona-dialogs-panels :deep(.v-expansion-panel) {
  overflow: hidden;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  border-radius: 8px !important;
  box-shadow: none !important;
}

.persona-dialogs-panels :deep(.v-expansion-panel-title) {
  min-height: 48px;
  padding: 4px 16px;
  font-size: 0.9rem;
  font-weight: 600;
}

.persona-dialogs-panels :deep(.v-expansion-panel-text__wrapper) {
  padding: 16px;
  border-top: 1px solid rgba(var(--v-theme-on-surface), 0.12);
}

@media (max-width: 600px) {
  .persona-form-card-mobile {
    border-radius: 0;
  }

  .persona-form-content {
    max-height: calc(100vh - 128px);
    padding: 16px !important;
  }

  .persona-basic-col,
  .persona-panels-col {
    padding-top: 0 !important;
  }

  .persona-form-actions {
    padding: 12px 16px !important;
    gap: 8px;
  }

  .persona-form-actions .v-btn {
    min-width: 0;
  }
}
</style>
