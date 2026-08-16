<template>
  <v-dialog
    v-model="showDialog"
    :max-width="smAndDown ? undefined : '1200px'"
    scrollable
    persistent
  >
    <v-card
      class="persona-form-card"
      :class="{ 'persona-form-card-mobile': smAndDown }"
    >
      <v-card-title class="persona-form-title text-h2 px-6 pt-6 pl-6">
        {{
          editingPersona ? tm('dialog.edit.title') : tm('dialog.create.title')
        }}
      </v-card-title>

      <v-card-text class="persona-form-content">
        <!-- 创建位置提示 -->
        <v-alert
          v-if="!editingPersona"
          type="info"
          variant="tonal"
          density="compact"
          class="mb-4"
          icon="mdi-folder-outline"
        >
          {{ tm('form.createInFolder', { folder: folderDisplayName }) }}
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
              <v-expansion-panels v-model="expandedPanels" multiple>
                <!-- 工具选择面板 -->
                <v-expansion-panel value="tools">
                  <v-expansion-panel-title>
                    <v-icon class="mr-2">mdi-tools</v-icon>
                    {{ tm('form.tools') }}
                    <v-chip
                      v-if="
                        Array.isArray(personaForm.tools) &&
                        personaForm.tools.length > 0
                      "
                      size="small"
                      color="primary"
                      variant="tonal"
                      class="ml-2"
                    >
                      {{ personaForm.tools.length }}
                    </v-chip>
                  </v-expansion-panel-title>

                  <v-expansion-panel-text>
                    <div class="mb-3">
                      <p class="text-body-2 text-medium-emphasis">
                        {{ tm('form.toolsHelp') }}
                      </p>
                    </div>

                    <v-radio-group
                      v-model="toolSelectValue"
                      class="mt-2"
                      :hide-details="true"
                    >
                      <v-radio label="默认使用全部函数工具" value="0"></v-radio>
                      <v-radio label="选择指定函数工具" value="1"> </v-radio>
                    </v-radio-group>

                    <div
                      v-if="toolSelectValue === '1'"
                      class="mt-3 selected-config-area"
                    >
                      <!-- 工具搜索 -->
                      <v-text-field
                        v-model="toolSearch"
                        :label="tm('form.searchTools')"
                        prepend-inner-icon="mdi-magnify"
                        variant="outlined"
                        density="compact"
                        hide-details
                        clearable
                        class="mb-3"
                      />

                      <!-- MCP 服务器 -->
                      <div v-if="mcpServers.length > 0" class="mb-4">
                        <h4 class="text-subtitle-2 mb-2">
                          {{ tm('form.mcpServersQuickSelect') }}
                        </h4>
                        <div class="d-flex flex-wrap ga-2">
                          <v-chip
                            v-for="server in mcpServers"
                            :key="server.name"
                            :color="
                              isServerSelected(server) ? 'primary' : 'default'
                            "
                            :variant="
                              isServerSelected(server) ? 'flat' : 'outlined'
                            "
                            size="small"
                            clickable
                            :disabled="
                              !server.tools || server.tools.length === 0
                            "
                            @click="toggleMcpServer(server)"
                          >
                            <v-icon start size="small">mdi-server</v-icon>
                            {{ server.name }}
                            <span v-if="server.tools" class="ml-1">
                              ({{ server.tools.length }})
                            </span>
                          </v-chip>
                        </div>
                      </div>

                      <!-- 工具选择列表 -->
                      <div
                        v-if="filteredTools.length > 0"
                        class="tools-selection"
                      >
                        <v-virtual-scroll
                          :items="filteredTools"
                          height="300"
                          item-height="72"
                        >
                          <template #default="{ item }">
                            <v-tooltip
                              :disabled="!isBuiltinTool(item)"
                              location="top"
                            >
                              <template #activator="{ props: tooltipProps }">
                                <div v-bind="tooltipProps">
                                  <v-list-item
                                    :key="item.name"
                                    density="comfortable"
                                    :disabled="isBuiltinTool(item)"
                                    @click="toggleTool(item.name)"
                                  >
                                    <template #prepend>
                                      <v-checkbox-btn
                                        v-if="!isBuiltinTool(item)"
                                        :model-value="isToolSelected(item.name)"
                                        @click.stop="toggleTool(item.name)"
                                      />
                                      <div
                                        v-else
                                        class="builtin-tool-checkbox-placeholder"
                                      />
                                    </template>

                                    <v-list-item-title>
                                      {{ item.name }}

                                      <v-chip
                                        v-if="item.origin"
                                        size="x-small"
                                        color="info"
                                        class="mr-2"
                                        variant="tonal"
                                      >
                                        {{ item.origin }}
                                      </v-chip>
                                      <v-chip
                                        v-if="item.origin_name"
                                        size="x-small"
                                        color="info"
                                        variant="outlined"
                                      >
                                        {{ item.origin_name }}
                                      </v-chip>
                                    </v-list-item-title>

                                    <v-list-item-subtitle
                                      v-if="item.description"
                                    >
                                      {{ truncateText(item.description, 100) }}
                                    </v-list-item-subtitle>
                                  </v-list-item>
                                </div>
                              </template>
                              <span>{{
                                tm('form.builtinToolDisabledHint')
                              }}</span>
                            </v-tooltip>
                          </template>
                        </v-virtual-scroll>
                      </div>

                      <div
                        v-else-if="!loadingTools && availableTools.length === 0"
                        class="text-center pa-4"
                      >
                        <v-icon
                          size="48"
                          color="on-surface-variant"
                          class="mb-2"
                          >mdi-tools</v-icon
                        >
                        <p class="text-body-2 text-medium-emphasis">
                          {{ tm('form.noToolsAvailable') }}
                        </p>
                      </div>

                      <div
                        v-else-if="!loadingTools && filteredTools.length === 0"
                        class="text-center pa-4"
                      >
                        <v-icon
                          size="48"
                          color="on-surface-variant"
                          class="mb-2"
                          >mdi-magnify</v-icon
                        >
                        <p class="text-body-2 text-medium-emphasis">
                          {{ tm('form.noToolsFound') }}
                        </p>
                      </div>

                      <!-- 加载状态 -->
                      <div v-if="loadingTools" class="text-center pa-4">
                        <v-progress-circular indeterminate color="primary" />
                        <p class="text-body-2 text-medium-emphasis mt-2">
                          {{ tm('form.loadingTools') }}
                        </p>
                      </div>

                      <!-- 已选择的工具 -->
                      <div class="mt-4">
                        <h4 class="text-subtitle-2 mb-2">
                          {{ tm('form.selectedTools') }}
                          <span
                            v-if="personaForm.tools === null"
                            class="text-success"
                          >
                            ({{ tm('form.allSelected') }})
                          </span>
                          <span v-else-if="Array.isArray(personaForm.tools)">
                            ({{ personaForm.tools.length }})
                          </span>
                        </h4>
                        <div
                          v-if="
                            Array.isArray(personaForm.tools) &&
                            personaForm.tools.length > 0
                          "
                          class="persona-form__selected-list d-flex flex-wrap ga-1"
                        >
                          <v-tooltip
                            v-for="toolName in personaForm.tools"
                            :key="toolName"
                            :disabled="!isBuiltinToolName(toolName)"
                            location="top"
                          >
                            <template #activator="{ props: tooltipProps }">
                              <v-chip
                                v-bind="tooltipProps"
                                size="small"
                                color="primary"
                                variant="tonal"
                                :closable="!isBuiltinToolName(toolName)"
                                @click:close="removeTool(toolName)"
                              >
                                {{ toolName }}
                              </v-chip>
                            </template>
                            <span>{{
                              tm('form.builtinToolDisabledHint')
                            }}</span>
                          </v-tooltip>
                        </div>
                        <div v-else class="text-body-2 text-medium-emphasis">
                          {{ tm('form.noToolsSelected') }}
                        </div>
                      </div>
                    </div>
                  </v-expansion-panel-text>
                </v-expansion-panel>

                <!-- Skills 选择面板 -->
                <v-expansion-panel value="skills">
                  <v-expansion-panel-title>
                    <v-icon class="mr-2">mdi-lightning-bolt</v-icon>
                    {{ tm('form.skills') }}
                    <v-chip
                      v-if="
                        Array.isArray(personaForm.skills) &&
                        personaForm.skills.length > 0
                      "
                      size="small"
                      color="primary"
                      variant="tonal"
                      class="ml-2"
                    >
                      {{ personaForm.skills.length }}
                    </v-chip>
                  </v-expansion-panel-title>

                  <v-expansion-panel-text>
                    <div class="mb-3">
                      <p class="text-body-2 text-medium-emphasis">
                        {{ tm('form.skillsHelp') }}
                      </p>
                    </div>

                    <v-radio-group
                      v-model="skillSelectValue"
                      class="mt-2"
                      :hide-details="true"
                    >
                      <v-radio
                        :label="tm('form.skillsAllAvailable')"
                        value="0"
                      ></v-radio>
                      <v-radio
                        :label="tm('form.skillsSelectSpecific')"
                        value="1"
                      ></v-radio>
                    </v-radio-group>

                    <div
                      v-if="skillSelectValue === '1'"
                      class="mt-3 selected-config-area"
                    >
                      <v-text-field
                        v-model="skillSearch"
                        :label="tm('form.searchSkills')"
                        prepend-inner-icon="mdi-magnify"
                        variant="outlined"
                        density="compact"
                        hide-details
                        clearable
                        class="mb-3"
                      />

                      <div
                        v-if="filteredSkills.length > 0"
                        class="skills-selection"
                      >
                        <v-virtual-scroll
                          :items="filteredSkills"
                          height="240"
                          item-height="48"
                        >
                          <template #default="{ item }">
                            <v-list-item
                              :key="item.name"
                              density="comfortable"
                              @click="toggleSkill(item.name)"
                            >
                              <template #prepend>
                                <v-checkbox-btn
                                  :model-value="isSkillSelected(item.name)"
                                  @click.stop="toggleSkill(item.name)"
                                />
                              </template>
                              <v-list-item-title>
                                {{ item.name }}
                              </v-list-item-title>
                              <v-list-item-subtitle v-if="item.description">
                                {{ truncateText(item.description, 100) }}
                              </v-list-item-subtitle>
                            </v-list-item>
                          </template>
                        </v-virtual-scroll>
                      </div>

                      <div
                        v-else-if="
                          !loadingSkills && availableSkills.length === 0
                        "
                        class="text-center pa-4"
                      >
                        <v-icon
                          size="48"
                          color="on-surface-variant"
                          class="mb-2"
                          >mdi-lightning-bolt</v-icon
                        >
                        <p class="text-body-2 text-medium-emphasis">
                          {{ tm('form.noSkillsAvailable') }}
                        </p>
                      </div>

                      <div
                        v-else-if="
                          !loadingSkills && filteredSkills.length === 0
                        "
                        class="text-center pa-4"
                      >
                        <v-icon
                          size="48"
                          color="on-surface-variant"
                          class="mb-2"
                          >mdi-magnify</v-icon
                        >
                        <p class="text-body-2 text-medium-emphasis">
                          {{ tm('form.noSkillsFound') }}
                        </p>
                      </div>

                      <div v-if="loadingSkills" class="text-center pa-4">
                        <v-progress-circular indeterminate color="primary" />
                        <p class="text-body-2 text-medium-emphasis mt-2">
                          {{ tm('form.loadingSkills') }}
                        </p>
                      </div>

                      <div class="mt-4">
                        <h4 class="text-subtitle-2 mb-2">
                          {{ tm('form.selectedSkills') }}
                          <span
                            v-if="personaForm.skills === null"
                            class="text-success"
                          >
                            ({{ tm('form.allSelected') }})
                          </span>
                          <span v-else-if="Array.isArray(personaForm.skills)">
                            ({{ personaForm.skills.length }})
                          </span>
                        </h4>
                        <div
                          v-if="
                            Array.isArray(personaForm.skills) &&
                            personaForm.skills.length > 0
                          "
                          class="persona-form__selected-list d-flex flex-wrap ga-1"
                        >
                          <v-chip
                            v-for="skillName in personaForm.skills"
                            :key="skillName"
                            size="small"
                            color="primary"
                            variant="tonal"
                            closable
                            @click:close="removeSkill(skillName)"
                          >
                            {{ skillName }}
                          </v-chip>
                        </div>
                        <div v-else class="text-body-2 text-medium-emphasis">
                          {{ tm('form.noSkillsSelected') }}
                        </div>
                      </div>
                    </div>
                  </v-expansion-panel-text>
                </v-expansion-panel>

                <!-- 预设对话面板 -->
                <v-expansion-panel value="dialogs">
                  <v-expansion-panel-title>
                    <v-icon class="mr-2">mdi-chat</v-icon>
                    {{ tm('form.presetDialogs') }}
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
                    <div class="mb-3">
                      <p class="text-body-2 text-medium-emphasis">
                        {{ tm('form.presetDialogsHelp') }}
                      </p>
                    </div>

                    <div
                      v-for="(dialog, index) in personaForm.begin_dialogs"
                      :key="index"
                      class="mb-3"
                    >
                      <v-textarea
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
                    </div>

                    <v-btn
                      variant="outlined"
                      prepend-icon="mdi-plus"
                      block
                      @click="addDialogPair"
                    >
                      {{ tm('buttons.addDialogPair') }}
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
          {{ tm('buttons.delete') }}
        </v-btn>
        <v-spacer />
        <v-btn variant="text" @click="closeDialog">
          {{ tm('buttons.cancel') }}
        </v-btn>
        <v-btn
          color="primary"
          variant="flat"
          :loading="saving"
          :disabled="!formValid"
          @click="savePersona"
        >
          {{ tm('buttons.save') }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue';
import {
  mcpApi,
  personaApi,
  skillApi,
  toolApi,
  type PersonaData,
  type PersonaInput,
} from '@/api/v1';
import type { ToolItem } from '@/domain/tools';
import { useModuleI18n } from '@/i18n/composables';
import {
  askForConfirmation as askForConfirmationDialog,
  useConfirmDialog,
} from '@/utils/confirmDialog';
import { useDisplay } from 'vuetify';

type SelectionMode = '0' | '1';
type PanelKey = 'tools' | 'skills' | 'dialogs';
type RuleResult = true | string;
type PersonaRule = (value: string) => RuleResult;

interface EditablePersona {
  persona_id: PersonaData['persona_id'];
  system_prompt: PersonaData['system_prompt'];
  custom_error_message?: PersonaData['custom_error_message'];
  begin_dialogs?: string[] | null;
  tools?: string[] | null;
  skills?: string[] | null;
  folder_id?: string | null;
}

interface PersonaFormState {
  persona_id: string;
  system_prompt: string;
  custom_error_message: string;
  begin_dialogs: string[];
  tools: string[] | null;
  skills: string[] | null;
  folder_id: string | null;
}

interface McpServerItem {
  name: string;
  tools: string[];
}

interface PersonaToolItem extends Pick<
  ToolItem,
  'name' | 'description' | 'origin' | 'origin_name' | 'readonly'
> {
  mcp_server_name?: string;
}

interface SkillItemOption {
  name: string;
  description: string;
  active: boolean;
  source_type?: string;
  plugin_active?: boolean;
  plugin_display_name?: string;
}

const props = withDefaults(
  defineProps<{
    modelValue?: boolean;
    editingPersona?: EditablePersona | null;
    currentFolderId?: string | null;
    currentFolderName?: string | null;
  }>(),
  {
    modelValue: false,
    editingPersona: null,
    currentFolderId: null,
    currentFolderName: null,
  },
);

const emit = defineEmits<{
  (event: 'update:modelValue', value: boolean): void;
  (event: 'saved', message: string): void;
  (event: 'error', message: string): void;
  (event: 'deleted', message: string): void;
}>();

const { tm } = useModuleI18n('features/persona');
const confirmDialog = useConfirmDialog();
const { smAndDown } = useDisplay();

const toolSelectValue = ref<SelectionMode>('0');
const skillSelectValue = ref<SelectionMode>('0');
const saving = ref(false);
const expandedPanels = ref<PanelKey[]>([]);
const formValid = ref(false);
const mcpServers = ref<McpServerItem[]>([]);
const availableTools = ref<PersonaToolItem[]>([]);
const loadingTools = ref(false);
const availableSkills = ref<SkillItemOption[]>([]);
const loadingSkills = ref(false);
const existingPersonaIds = ref<string[]>([]);
const toolSearch = ref('');
const skillSearch = ref('');
const personaForm = reactive<PersonaFormState>(
  createEmptyPersonaForm(props.currentFolderId),
);

const showDialog = computed({
  get: () => props.modelValue,
  set: (value: boolean) => void emit('update:modelValue', value),
});

const personaIdRules = computed<PersonaRule[]>(() => [
  (value) => Boolean(value) || tm('validation.required'),
  (value) =>
    (value.length >= 1 && true) || tm('validation.minLength', { min: 1 }),
  (value) =>
    props.editingPersona?.persona_id === value ||
    !existingPersonaIds.value.includes(value) ||
    tm('validation.personaIdExists'),
]);

const systemPromptRules = computed<PersonaRule[]>(() => [
  (value) => Boolean(value) || tm('validation.required'),
  (value) =>
    (value.trim().length >= 10 && true) ||
    tm('validation.minLength', { min: 10 }),
]);

const filteredTools = computed(() => {
  const search = toolSearch.value.trim().toLowerCase();
  if (!search) {
    return availableTools.value;
  }
  return availableTools.value.filter(
    (tool) =>
      tool.name.toLowerCase().includes(search) ||
      tool.description.toLowerCase().includes(search) ||
      tool.mcp_server_name?.toLowerCase().includes(search),
  );
});

const filteredSkills = computed(() => {
  const search = skillSearch.value.trim().toLowerCase();
  if (!search) {
    return availableSkills.value;
  }
  return availableSkills.value.filter(
    (skill) =>
      skill.name.toLowerCase().includes(search) ||
      skill.description.toLowerCase().includes(search),
  );
});

const folderDisplayName = computed(() => {
  if (props.currentFolderName) {
    return props.currentFolderName;
  }
  if (!props.currentFolderId) {
    return tm('form.rootFolder');
  }
  return props.currentFolderId;
});

watch(
  () => props.modelValue,
  (newValue) => {
    if (!newValue) {
      return;
    }
    if (props.editingPersona) {
      initFormWithPersona(props.editingPersona);
    } else {
      initForm();
      void loadExistingPersonaIds();
    }
    void loadMcpServers();
    void loadTools();
    void loadSkills();
  },
);

watch(
  () => props.editingPersona,
  (newPersona) => {
    if (!props.modelValue) {
      return;
    }
    if (newPersona) {
      initFormWithPersona(newPersona);
      return;
    }
    initForm();
  },
  { immediate: true },
);

watch(toolSelectValue, (newValue) => {
  if (newValue === '0') {
    personaForm.tools = null;
  } else if (personaForm.tools === null) {
    personaForm.tools = [];
  }
});

watch(skillSelectValue, (newValue) => {
  if (newValue === '0') {
    personaForm.skills = null;
  } else if (personaForm.skills === null) {
    personaForm.skills = [];
  }
});

function createEmptyPersonaForm(
  folderId: string | null | undefined,
): PersonaFormState {
  return {
    persona_id: '',
    system_prompt: '',
    custom_error_message: '',
    begin_dialogs: [],
    tools: [],
    skills: [],
    folder_id: folderId ?? null,
  };
}

function cloneStringList(value: string[] | null | undefined): string[] | null {
  if (value === null) {
    return null;
  }
  return Array.isArray(value) ? [...value] : [];
}

function applyPersonaForm(next: PersonaFormState) {
  personaForm.persona_id = next.persona_id;
  personaForm.system_prompt = next.system_prompt;
  personaForm.custom_error_message = next.custom_error_message;
  personaForm.begin_dialogs = [...next.begin_dialogs];
  personaForm.tools = cloneStringList(next.tools);
  personaForm.skills = cloneStringList(next.skills);
  personaForm.folder_id = next.folder_id;
}

function initForm() {
  applyPersonaForm(createEmptyPersonaForm(props.currentFolderId));
  toolSelectValue.value = '0';
  skillSelectValue.value = '0';
  expandedPanels.value = getDefaultExpandedPanels();
}

function initFormWithPersona(persona: EditablePersona) {
  applyPersonaForm({
    persona_id: persona.persona_id,
    system_prompt: persona.system_prompt,
    custom_error_message: persona.custom_error_message ?? '',
    begin_dialogs: Array.isArray(persona.begin_dialogs)
      ? [...persona.begin_dialogs]
      : [],
    tools: cloneStringList(persona.tools),
    skills: cloneStringList(persona.skills),
    folder_id: persona.folder_id ?? null,
  });
  toolSelectValue.value = persona.tools === null ? '0' : '1';
  skillSelectValue.value = persona.skills === null ? '0' : '1';
  expandedPanels.value = getDefaultExpandedPanels();
}

function getDefaultExpandedPanels(): PanelKey[] {
  return smAndDown.value ? [] : ['tools', 'skills', 'dialogs'];
}

function closeDialog() {
  showDialog.value = false;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return null;
  }
  return value as Record<string, unknown>;
}

function getString(value: unknown): string | null {
  return typeof value === 'string' ? value : null;
}

function getBoolean(value: unknown): boolean | null {
  return typeof value === 'boolean' ? value : null;
}

function getStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((item): item is string => typeof item === 'string');
}

function getApiErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message) {
    const record = asRecord(error);
    const response = asRecord(record?.response);
    const data = asRecord(response?.data);
    return getString(data?.message) ?? error.message;
  }
  const record = asRecord(error);
  const response = asRecord(record?.response);
  const data = asRecord(response?.data);
  return getString(data?.message) ?? fallback;
}

function normalizeMcpServer(value: unknown): McpServerItem | null {
  const record = asRecord(value);
  if (!record) {
    return null;
  }
  const name = getString(record?.name);
  if (!name) {
    return null;
  }
  return {
    name,
    tools: getStringArray(record.tools),
  };
}

function normalizeToolItem(value: unknown): PersonaToolItem | null {
  const record = asRecord(value);
  if (!record) {
    return null;
  }
  const name = getString(record?.name);
  if (!name) {
    return null;
  }
  return {
    name,
    description: getString(record.description) ?? '',
    mcp_server_name: getString(record.mcp_server_name) ?? undefined,
    origin: getString(record.origin) ?? undefined,
    origin_name: getString(record.origin_name) ?? undefined,
    readonly: getBoolean(record.readonly) ?? undefined,
  };
}

function normalizeSkillItem(value: unknown): SkillItemOption | null {
  const record = asRecord(value);
  if (!record) {
    return null;
  }
  const name = getString(record?.name);
  if (!name) {
    return null;
  }
  return {
    name,
    description: getString(record.description) ?? '',
    active: getBoolean(record.active) ?? true,
    source_type: getString(record.source_type) ?? undefined,
    plugin_active: getBoolean(record.plugin_active) ?? undefined,
    plugin_display_name: getString(record.plugin_display_name) ?? undefined,
  };
}

function normalizePersonaSummary(value: unknown): EditablePersona | null {
  const record = asRecord(value);
  if (!record) {
    return null;
  }
  const personaId = getString(record?.persona_id);
  const systemPrompt = getString(record?.system_prompt);
  if (!personaId || !systemPrompt) {
    return null;
  }
  return {
    persona_id: personaId,
    system_prompt: systemPrompt,
    custom_error_message: getString(record.custom_error_message),
    begin_dialogs: getStringArray(record.begin_dialogs),
    tools:
      record.tools === null ? null : getStringArray(record.tools ?? undefined),
    skills:
      record.skills === null
        ? null
        : getStringArray(record.skills ?? undefined),
    folder_id: getString(record.folder_id),
  };
}

async function loadMcpServers() {
  try {
    const response = await mcpApi.list();
    if (response.data.status !== 'ok') {
      emit('error', response.data.message || 'Failed to load MCP servers');
      return;
    }
    const payload = Array.isArray(response.data.data) ? response.data.data : [];
    mcpServers.value = payload
      .map(normalizeMcpServer)
      .filter((server): server is McpServerItem => server !== null);
  } catch (error) {
    emit('error', getApiErrorMessage(error, 'Failed to load MCP servers'));
    mcpServers.value = [];
  }
}

async function loadTools() {
  loadingTools.value = true;
  try {
    const response = await toolApi.list();
    if (response.data.status !== 'ok') {
      emit('error', response.data.message || 'Failed to load tools');
      return;
    }
    const payload = Array.isArray(response.data.data) ? response.data.data : [];
    availableTools.value = payload
      .map(normalizeToolItem)
      .filter((tool): tool is PersonaToolItem => tool !== null);
  } catch (error) {
    emit('error', getApiErrorMessage(error, 'Failed to load tools'));
    availableTools.value = [];
  } finally {
    loadingTools.value = false;
  }
}

async function loadSkills() {
  loadingSkills.value = true;
  try {
    const response = await skillApi.list();
    if (response.data.status !== 'ok') {
      emit('error', response.data.message || 'Failed to load skills');
      return;
    }
    const payload = response.data.data;
    const payloadRecord = asRecord(payload);
    let rawSkills: unknown[] = [];
    if (Array.isArray(payload)) {
      rawSkills = payload;
    } else if (Array.isArray(payloadRecord?.skills)) {
      rawSkills = payloadRecord.skills;
    }
    availableSkills.value = rawSkills
      .map(normalizeSkillItem)
      .filter(
        (skill): skill is SkillItemOption =>
          skill !== null &&
          skill.active !== false &&
          skill.plugin_active !== false,
      );
  } catch (error) {
    emit('error', getApiErrorMessage(error, 'Failed to load skills'));
    availableSkills.value = [];
  } finally {
    loadingSkills.value = false;
  }
}

async function loadExistingPersonaIds() {
  try {
    const response = await personaApi.list();
    if (response.data.status !== 'ok') {
      existingPersonaIds.value = [];
      return;
    }
    const payload = Array.isArray(response.data.data) ? response.data.data : [];
    existingPersonaIds.value = payload
      .map(normalizePersonaSummary)
      .filter((persona): persona is EditablePersona => persona !== null)
      .map((persona) => persona.persona_id);
  } catch {
    existingPersonaIds.value = [];
  }
}

function buildPersonaPayload(): PersonaInput {
  return {
    persona_id: personaForm.persona_id,
    system_prompt: personaForm.system_prompt,
    custom_error_message: personaForm.custom_error_message || null,
    begin_dialogs: [...personaForm.begin_dialogs],
    tools: cloneStringList(personaForm.tools),
    skills: cloneStringList(personaForm.skills),
    folder_id: personaForm.folder_id,
  };
}

async function savePersona() {
  if (!formValid.value) {
    return;
  }
  for (let index = 0; index < personaForm.begin_dialogs.length; index += 1) {
    const dialog = personaForm.begin_dialogs[index];
    if (!dialog || dialog.trim() === '') {
      const dialogType =
        index % 2 === 0 ? tm('form.userMessage') : tm('form.assistantMessage');
      emit('error', tm('validation.dialogRequired', { type: dialogType }));
      return;
    }
  }

  saving.value = true;
  try {
    const payload = buildPersonaPayload();
    const response = props.editingPersona
      ? await personaApi.update(payload.persona_id, {
          system_prompt: payload.system_prompt,
          custom_error_message: payload.custom_error_message,
          begin_dialogs: payload.begin_dialogs,
          tools: payload.tools,
          skills: payload.skills,
          folder_id: payload.folder_id,
        })
      : await personaApi.create(payload);

    if (response.data.status === 'ok') {
      emit('saved', response.data.message || tm('messages.saveSuccess'));
      closeDialog();
    } else {
      emit('error', response.data.message || tm('messages.saveError'));
    }
  } catch (error) {
    emit('error', getApiErrorMessage(error, tm('messages.saveError')));
  } finally {
    saving.value = false;
  }
}

async function deletePersona() {
  if (!props.editingPersona) {
    return;
  }
  const confirmed = await askForConfirmationDialog(
    tm('messages.deleteConfirm', {
      id: props.editingPersona.persona_id,
    }),
    confirmDialog,
  );
  if (!confirmed) {
    return;
  }

  saving.value = true;
  try {
    const response = await personaApi.delete(props.editingPersona.persona_id);
    if (response.data.status === 'ok') {
      emit('deleted', response.data.message || tm('messages.deleteSuccess'));
      closeDialog();
    } else {
      emit('error', response.data.message || tm('messages.deleteError'));
    }
  } catch (error) {
    emit('error', getApiErrorMessage(error, tm('messages.deleteError')));
  } finally {
    saving.value = false;
  }
}

function addDialogPair() {
  personaForm.begin_dialogs.push('', '');
  if (!expandedPanels.value.includes('dialogs')) {
    expandedPanels.value.push('dialogs');
  }
}

function removeDialog(index: number) {
  if (index % 2 === 0 && index + 1 < personaForm.begin_dialogs.length) {
    personaForm.begin_dialogs.splice(index, 2);
  } else if (index % 2 === 1 && index - 1 >= 0) {
    personaForm.begin_dialogs.splice(index - 1, 2);
  }
}

function toggleMcpServer(server: McpServerItem) {
  if (server.tools.length === 0) {
    return;
  }
  if (personaForm.tools === null) {
    personaForm.tools = availableTools.value
      .map((tool) => tool.name)
      .filter((toolName) => !server.tools.includes(toolName));
    toolSelectValue.value = '1';
    return;
  }
  if (!Array.isArray(personaForm.tools)) {
    personaForm.tools = [];
    toolSelectValue.value = '1';
  }

  const allSelected = server.tools.every((toolName) =>
    personaForm.tools?.includes(toolName),
  );
  if (allSelected) {
    personaForm.tools = personaForm.tools.filter(
      (toolName) => !server.tools.includes(toolName),
    );
    return;
  }
  for (const toolName of server.tools) {
    if (!personaForm.tools.includes(toolName)) {
      personaForm.tools.push(toolName);
    }
  }
}

function toggleTool(toolName: string) {
  if (isBuiltinToolName(toolName)) {
    return;
  }
  if (personaForm.tools === null) {
    personaForm.tools = availableTools.value
      .map((tool) => tool.name)
      .filter((name) => name !== toolName);
    toolSelectValue.value = '1';
    return;
  }
  if (Array.isArray(personaForm.tools)) {
    const index = personaForm.tools.indexOf(toolName);
    if (index !== -1) {
      personaForm.tools.splice(index, 1);
    } else {
      personaForm.tools.push(toolName);
    }
    return;
  }
  personaForm.tools = [toolName];
  toolSelectValue.value = '1';
}

function removeTool(toolName: string) {
  if (isBuiltinToolName(toolName)) {
    return;
  }
  if (personaForm.tools === null) {
    personaForm.tools = availableTools.value
      .map((tool) => tool.name)
      .filter((name) => name !== toolName);
    toolSelectValue.value = '1';
    return;
  }
  if (!Array.isArray(personaForm.tools)) {
    return;
  }
  const index = personaForm.tools.indexOf(toolName);
  if (index !== -1) {
    personaForm.tools.splice(index, 1);
  }
}

function toggleSkill(skillName: string) {
  if (personaForm.skills === null) {
    personaForm.skills = availableSkills.value
      .map((skill) => skill.name)
      .filter((name) => name !== skillName);
    skillSelectValue.value = '1';
    return;
  }
  if (Array.isArray(personaForm.skills)) {
    const index = personaForm.skills.indexOf(skillName);
    if (index !== -1) {
      personaForm.skills.splice(index, 1);
    } else {
      personaForm.skills.push(skillName);
    }
    return;
  }
  personaForm.skills = [skillName];
  skillSelectValue.value = '1';
}

function removeSkill(skillName: string) {
  if (personaForm.skills === null) {
    personaForm.skills = availableSkills.value
      .map((skill) => skill.name)
      .filter((name) => name !== skillName);
    skillSelectValue.value = '1';
    return;
  }
  if (!Array.isArray(personaForm.skills)) {
    return;
  }
  const index = personaForm.skills.indexOf(skillName);
  if (index !== -1) {
    personaForm.skills.splice(index, 1);
  }
}

function truncateText(text: string | null | undefined, maxLength: number) {
  if (!text) {
    return '';
  }
  return text.length > maxLength ? `${text.substring(0, maxLength)}...` : text;
}

function isBuiltinTool(tool: PersonaToolItem) {
  return tool.origin === 'builtin' || tool.readonly === true;
}

function isBuiltinToolName(toolName: string) {
  return availableTools.value.some(
    (tool) => tool.name === toolName && isBuiltinTool(tool),
  );
}

function getDialogRules(index: number): PersonaRule[] {
  const dialogType =
    index % 2 === 0 ? tm('form.userMessage') : tm('form.assistantMessage');
  return [
    (value) =>
      Boolean(value) || tm('validation.dialogRequired', { type: dialogType }),
    (value) =>
      (value.trim().length > 0 && true) ||
      tm('validation.dialogRequired', { type: dialogType }),
  ];
}

function isToolSelected(toolName: string) {
  if (personaForm.tools === null) {
    return true;
  }
  return (
    Array.isArray(personaForm.tools) && personaForm.tools.includes(toolName)
  );
}

function isSkillSelected(skillName: string) {
  if (personaForm.skills === null) {
    return true;
  }
  return (
    Array.isArray(personaForm.skills) && personaForm.skills.includes(skillName)
  );
}

function isServerSelected(server: McpServerItem) {
  if (server.tools.length === 0) {
    return false;
  }
  if (personaForm.tools === null) {
    return true;
  }
  return (
    Array.isArray(personaForm.tools) &&
    server.tools.every((toolName) => personaForm.tools?.includes(toolName))
  );
}
</script>

<style scoped>
.persona-form-card {
  border-radius: 12px;
  overflow: hidden;
}

.persona-form__selected-list {
  max-height: 100px;
  overflow-y: auto;
}

.persona-form-content {
  max-height: min(78vh, 760px);
  overflow-y: auto;
}

.persona-form-title {
  line-height: 1.3;
}

.persona-form-actions {
  position: sticky;
  bottom: 0;
  z-index: 2;
  background: rgb(var(--v-theme-surface));
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.selected-config-area {
  margin-left: 32px;
}

.persona-form-layout {
  align-items: flex-start;
}

.tools-selection {
  max-height: 300px;
  overflow-y: auto;
}

.builtin-tool-checkbox-placeholder {
  width: 40px;
  height: 40px;
  flex: 0 0 40px;
}

.skills-selection {
  max-height: 300px;
  overflow-y: auto;
}

.v-virtual-scroll {
  padding-bottom: 16px;
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

  .persona-form-title {
    font-size: 1.15rem !important;
    padding: 12px 16px !important;
  }

  .selected-config-area {
    margin-left: 0;
  }

  .tools-selection,
  .skills-selection {
    max-height: 38vh;
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
