<template>
  <div class="persona-preview-card">
    <div class="preview-header">
      <div>
        <div class="preview-title">{{ previewTitle }}</div>
        <small v-if="editable && canEdit" class="text-medium-emphasis">
          {{ tm("personaQuickPreview.editHint") }}
        </small>
      </div>
      <div class="preview-save-state" aria-live="polite">
        <template v-if="savingCapability">
          <v-progress-circular indeterminate size="14" width="2" class="mr-1" />
          {{ tm("personaQuickPreview.saving") }}
        </template>
        <template v-else-if="saved">
          <v-icon size="15" color="success">mdi-check-circle</v-icon>
          {{ tm("personaQuickPreview.saved") }}
        </template>
      </div>
    </div>

    <div v-if="loading" class="preview-loading">
      <v-progress-circular
        indeterminate
        size="18"
        width="2"
        color="primary"
        class="mr-2"
      />
      <small class="text-grey">{{ tm("personaQuickPreview.loading") }}</small>
    </div>

    <div v-else-if="!modelValue" class="preview-empty">
      <small class="text-grey">{{
        tm("personaQuickPreview.noPersonaSelected")
      }}</small>
    </div>

    <div v-else-if="!personaData" class="preview-empty">
      <small class="text-grey">{{
        tm("personaQuickPreview.personaNotFound")
      }}</small>
    </div>

    <div v-else class="preview-content">
      <div class="section-title">
        {{ tm("personaQuickPreview.systemPromptLabel") }}
      </div>
      <pre class="prompt-content">{{ personaData.system_prompt || "" }}</pre>

      <v-alert
        v-if="editable && isDefaultPersona"
        type="info"
        variant="tonal"
        density="compact"
        class="mt-3"
      >
        {{ tm("personaQuickPreview.defaultPersonaReadonly") }}
      </v-alert>

      <v-alert
        v-if="saveError"
        type="error"
        variant="tonal"
        density="compact"
        class="mt-3"
      >
        {{ tm("personaQuickPreview.saveFailed", { message: saveError }) }}
      </v-alert>

      <PersonaCapabilitiesEditor
        class="mt-3"
        :tools="personaData.tools"
        :skills="personaData.skills"
        :available-tools="availableTools"
        :available-skills="availableSkills"
        :readonly="!canEdit"
        :saving="savingCapability"
        :error="saveError"
        :update-capability="persistCapabilities"
      />
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { personaApi, skillApi, toolApi } from "@/api/v1";
import { useModuleI18n } from "@/i18n/composables";
import PersonaCapabilitiesEditor from "./PersonaCapabilitiesEditor.vue";

const props = defineProps({
  modelValue: {
    type: String,
    default: "",
  },
  editable: {
    type: Boolean,
    default: false,
  },
});

const { tm } = useModuleI18n("core.shared");

const loading = ref(false);
const personaData = ref(null);
const availableTools = ref([]);
const availableSkills = ref([]);
const savingCapability = ref("");
const saveError = ref("");
const saved = ref(false);
let savedTimer;
let personaLoadVersion = 0;

const defaultPersonaData = {
  persona_id: "default",
  system_prompt: "You are a helpful and friendly assistant.",
  tools: null,
  skills: null,
};

const isDefaultPersona = computed(() => props.modelValue === "default");
const previewTitle = computed(() => {
  if (!props.modelValue) {
    return tm("personaQuickPreview.title");
  }
  const personaName = isDefaultPersona.value
    ? tm("personaSelector.defaultPersona")
    : props.modelValue;
  return tm("personaQuickPreview.titleWithName", { name: personaName });
});
const canEdit = computed(
  () => props.editable && Boolean(personaData.value) && !isDefaultPersona.value,
);
async function persistCapabilities(field, nextValue, previousValue) {
  const personaId = props.modelValue;
  personaData.value = { ...personaData.value, [field]: nextValue };
  savingCapability.value = field;
  saveError.value = "";
  saved.value = false;

  try {
    const response = await personaApi.update(personaId, { [field]: nextValue });
    if (response.data?.status !== "ok") {
      throw new Error(
        response.data?.message || tm("personaQuickPreview.unknownError"),
      );
    }
    if (props.modelValue === personaId) {
      saved.value = true;
      window.clearTimeout(savedTimer);
      savedTimer = window.setTimeout(() => {
        saved.value = false;
      }, 1600);
    }
    return true;
  } catch (error) {
    if (props.modelValue === personaId) {
      personaData.value = { ...personaData.value, [field]: previousValue };
      saveError.value =
        error?.response?.data?.message ||
        error?.message ||
        tm("personaQuickPreview.unknownError");
    }
    return false;
  } finally {
    savingCapability.value = "";
  }
}

async function loadToolsMeta() {
  try {
    const response = await toolApi.list();
    availableTools.value =
      response.data?.status === "ok" ? response.data?.data || [] : [];
  } catch (error) {
    console.error("Failed to load tools metadata:", error);
    availableTools.value = [];
  }
}

async function loadSkillsMeta() {
  try {
    const response = await skillApi.list();
    if (response.data?.status === "ok") {
      const payload = response.data?.data || [];
      const skills = Array.isArray(payload) ? payload : payload.skills || [];
      availableSkills.value = skills.filter((skill) => skill.active !== false);
    } else {
      availableSkills.value = [];
    }
  } catch (error) {
    console.error("Failed to load skills metadata:", error);
    availableSkills.value = [];
  }
}

async function loadPersonaPreview(personaId) {
  const loadVersion = ++personaLoadVersion;
  if (!personaId) {
    loading.value = false;
    personaData.value = null;
    return;
  }

  if (personaId === "default") {
    loading.value = false;
    personaData.value = defaultPersonaData;
    return;
  }

  loading.value = true;
  try {
    const response = await personaApi.get(personaId);
    if (loadVersion === personaLoadVersion) {
      personaData.value =
        response.data?.status === "ok" ? response.data?.data || null : null;
    }
  } catch (error) {
    console.error("Failed to load persona preview:", error);
    if (loadVersion === personaLoadVersion) {
      personaData.value = null;
    }
  } finally {
    if (loadVersion === personaLoadVersion) {
      loading.value = false;
    }
  }
}

function handlePersonaSaved() {
  if (props.modelValue) {
    loadPersonaPreview(props.modelValue);
  }
}

watch(
  () => props.modelValue,
  (newValue) => {
    saveError.value = "";
    saved.value = false;
    loadPersonaPreview(newValue);
  },
  { immediate: true },
);

loadToolsMeta();
loadSkillsMeta();

onMounted(() => {
  window.addEventListener("astrbot:persona-saved", handlePersonaSaved);
});

onBeforeUnmount(() => {
  window.clearTimeout(savedTimer);
  window.removeEventListener("astrbot:persona-saved", handlePersonaSaved);
});
</script>

<style scoped>
.persona-preview-card {
  padding: 14px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.12);
  border-radius: 10px;
  background: rgba(var(--v-theme-on-surface), 0.015);
}

.preview-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  min-height: 24px;
  margin-bottom: 10px;
  gap: 12px;
}

.preview-title {
  font-size: 0.86rem;
  font-weight: 600;
}

.preview-save-state {
  display: flex;
  align-items: center;
  min-height: 20px;
  color: rgb(var(--v-theme-on-surface));
  font-size: 0.74rem;
  gap: 4px;
  opacity: 0.65;
}

.preview-loading,
.preview-empty {
  display: flex;
  align-items: center;
  min-height: 48px;
}

.section-title {
  color: rgb(var(--v-theme-on-surface));
  font-size: 0.75rem;
  font-weight: 500;
  opacity: 0.7;
}

.prompt-content {
  max-height: 120px;
  padding: 9px 10px;
  margin-top: 6px;
  overflow: auto;
  border-radius: 7px;
  background: rgba(var(--v-theme-on-surface), 0.035);
  font-size: 0.78rem;
  line-height: 1.45;
  white-space: pre-wrap;
  word-break: break-word;
}

@media (max-width: 600px) {
  .persona-preview-card {
    padding: 12px;
  }

  .preview-header {
    flex-direction: column;
    gap: 4px;
  }
}
</style>
