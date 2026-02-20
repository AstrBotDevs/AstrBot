<template>
  <div class="persona-preview-card">
    <div class="preview-header">
      <small>{{ tm('personaQuickPreview.title') }}</small>
    </div>

    <div v-if="loading" class="preview-loading">
      <v-progress-circular indeterminate size="18" width="2" color="primary" class="mr-2" />
      <small class="text-grey">{{ tm('personaQuickPreview.loading') }}</small>
    </div>

    <div v-else-if="!modelValue" class="preview-empty">
      <small class="text-grey">{{ tm('personaQuickPreview.noPersonaSelected') }}</small>
    </div>

    <div v-else-if="!personaData" class="preview-empty">
      <small class="text-grey">{{ tm('personaQuickPreview.personaNotFound') }}</small>
    </div>

    <div v-else class="preview-content">
      <div class="section-title">{{ tm('personaQuickPreview.systemPromptLabel') }}</div>
      <pre class="prompt-content">{{ personaData.system_prompt || '' }}</pre>

      <div class="section-title mt-3">{{ tm('personaQuickPreview.toolsLabel') }}</div>
      <div class="chip-wrap tools-wrap">
        <v-chip
          v-if="personaData.tools === null"
          size="small"
          color="success"
          variant="tonal"
          label
        >
          {{ tm('personaQuickPreview.allToolsWithCount', { count: allToolsCount }) }}
        </v-chip>
        <div v-for="tool in resolvedTools" v-else :key="tool.name" class="tool-item">
          <v-chip
            size="small"
            color="primary"
            variant="outlined"
            label
          >
            {{ tool.name }}
          </v-chip>
          <small v-if="tool.origin || tool.origin_name" class="text-grey tool-meta">
            <span v-if="tool.origin">{{ tm('personaQuickPreview.originLabel') }}: {{ tool.origin }}</span>
            <span v-if="tool.origin_name"> | {{ tm('personaQuickPreview.originNameLabel') }}: {{ tool.origin_name }}</span>
          </small>
        </div>
        <small v-if="personaData.tools !== null && normalizedTools.length === 0" class="text-grey">
          {{ tm('personaQuickPreview.noTools') }}
        </small>
      </div>

      <div class="section-title mt-3">{{ tm('personaQuickPreview.skillsLabel') }}</div>
      <div class="chip-wrap">
        <v-chip
          v-if="personaData.skills === null"
          size="small"
          color="success"
          variant="tonal"
          label
        >
          {{ tm('personaQuickPreview.allSkillsWithCount', { count: allSkillsCount }) }}
        </v-chip>
        <v-chip
          v-for="skillName in normalizedSkills"
          v-else
          :key="skillName"
          size="small"
          color="primary"
          variant="outlined"
          label
        >
          {{ skillName }}
        </v-chip>
        <small v-if="personaData.skills !== null && normalizedSkills.length === 0" class="text-grey">
          {{ tm('personaQuickPreview.noSkills') }}
        </small>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch, onMounted, onBeforeUnmount } from 'vue'
import axios from 'axios'
import { useModuleI18n } from '@/i18n/composables'

const props = defineProps({
  modelValue: {
    type: String,
    default: ''
  }
})

const { tm } = useModuleI18n('core.shared')

const loading = ref(false)
const personaData = ref(null)
const toolMetaMap = ref({})
const availableSkills = ref([])

const defaultPersonaData = {
  persona_id: 'default',
  system_prompt: 'You are a helpful and friendly assistant.',
  tools: null,
  skills: null
}

const normalizedTools = computed(() => (Array.isArray(personaData.value?.tools) ? personaData.value.tools : []))
const normalizedSkills = computed(() => (Array.isArray(personaData.value?.skills) ? personaData.value.skills : []))
const allToolsCount = computed(() => Object.keys(toolMetaMap.value).length)
const allSkillsCount = computed(() => availableSkills.value.length)
const resolvedTools = computed(() =>
  normalizedTools.value.map((toolName) => {
    const meta = toolMetaMap.value[toolName] || {}
    return {
      name: toolName,
      origin: meta.origin || '',
      origin_name: meta.origin_name || ''
    }
  })
)

async function loadToolsMeta() {
  try {
    const response = await axios.get('/api/tools/list')
    if (response.data?.status === 'ok') {
      const tools = response.data?.data || []
      const nextMap = {}
      for (const tool of tools) {
        if (!tool?.name) {
          continue
        }
        nextMap[tool.name] = {
          origin: tool.origin || '',
          origin_name: tool.origin_name || ''
        }
      }
      toolMetaMap.value = nextMap
    }
  } catch (error) {
    console.error('Failed to load tools metadata:', error)
    toolMetaMap.value = {}
  }
}

async function loadSkillsMeta() {
  try {
    const response = await axios.get('/api/skills')
    if (response.data?.status === 'ok') {
      const payload = response.data?.data || []
      if (Array.isArray(payload)) {
        availableSkills.value = payload.filter((skill) => skill.active !== false)
      } else {
        const skills = payload.skills || []
        availableSkills.value = skills.filter((skill) => skill.active !== false)
      }
    } else {
      availableSkills.value = []
    }
  } catch (error) {
    console.error('Failed to load skills metadata:', error)
    availableSkills.value = []
  }
}

async function loadPersonaPreview(personaId) {
  if (!personaId) {
    personaData.value = null
    return
  }

  if (personaId === 'default') {
    personaData.value = defaultPersonaData
    return
  }

  loading.value = true
  try {
    const response = await axios.get('/api/persona/list')
    if (response.data?.status === 'ok') {
      const personas = response.data?.data || []
      personaData.value = personas.find((item) => item.persona_id === personaId) || null
    } else {
      personaData.value = null
    }
  } catch (error) {
    console.error('Failed to load persona preview:', error)
    personaData.value = null
  } finally {
    loading.value = false
  }
}

function handlePersonaSaved() {
  if (props.modelValue) {
    loadPersonaPreview(props.modelValue)
  }
}

watch(
  () => props.modelValue,
  (newValue) => {
    loadPersonaPreview(newValue)
  },
  { immediate: true }
)

loadToolsMeta()
loadSkillsMeta()

onMounted(() => {
  window.addEventListener('astrbot:persona-saved', handlePersonaSaved)
})

onBeforeUnmount(() => {
  window.removeEventListener('astrbot:persona-saved', handlePersonaSaved)
})
</script>

<style scoped>
.persona-preview-card {
  background-color: rgba(var(--v-theme-primary), 0.05);
  border: 1px solid rgba(var(--v-theme-primary), 0.1);
  border-radius: 8px;
  padding: 12px;
}

.preview-header {
  margin-bottom: 8px;
}

.preview-loading,
.preview-empty {
  display: flex;
  align-items: center;
  min-height: 24px;
}

.section-title {
  font-size: 0.75rem;
  color: rgb(var(--v-theme-primaryText));
  opacity: 0.85;
}

.prompt-content {
  margin-top: 6px;
  max-height: 180px;
  overflow: auto;
  font-size: 0.78rem;
  line-height: 1.45;
  white-space: pre-wrap;
  word-break: break-word;
  background: rgba(0, 0, 0, 0.03);
  border-radius: 6px;
  padding: 8px;
}

.chip-wrap {
  display: grid;
  gap: 6px;
  margin-top: 6px;
}

.tools-wrap {
  max-height: 160px;
  overflow: auto;
}

.tool-item {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}

.tool-meta {
  font-size: 0.74rem;
}

@media (max-width: 600px) {
  .tools-wrap {
    max-height: 120px;
  }
}
</style>
