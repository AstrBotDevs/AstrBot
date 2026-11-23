<template>
  <div class="native-config-form">
    <div class="native-config-fields">
      <v-autocomplete
        v-model="personaId"
        :items="personas"
        :label="tm('form.personaLabel')"
        :placeholder="tm('form.inheritPersona')"
        :hint="tm('form.inheritPersona')"
        :loading="loading"
        variant="outlined"
        density="comfortable"
        hide-details="auto"
        persistent-hint
        clearable
      />
      <v-autocomplete
        v-model="providerId"
        :items="providers"
        :label="tm('form.providerLabel')"
        :placeholder="tm('form.inheritProvider')"
        :hint="tm('form.inheritProvider')"
        :loading="loading"
        variant="outlined"
        density="comfortable"
        hide-details="auto"
        persistent-hint
        clearable
      />
    </div>
    <p class="native-config-hint text-medium-emphasis">{{ tm('form.inheritSettings') }}</p>
    <v-alert v-if="error" type="error" variant="tonal" class="mt-3">{{ error }}</v-alert>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { personaApi, providerApi } from '@/api/v1';
import { useModuleI18n } from '@/i18n/composables';

const props = defineProps<{ modelValue: Record<string, any> }>();
const emit = defineEmits<{ 'update:modelValue': [value: Record<string, any>] }>();
const { tm } = useModuleI18n('features/subagent');
const personas = ref<string[]>([]);
const providers = ref<string[]>([]);
const loading = ref(false);
const error = ref('');
const personaId = computed<string>({
  get: () => props.modelValue.persona?.persona_id || '',
  set: value => emit('update:modelValue', {
    model: { provider_id: props.modelValue.model?.provider_id || '' }, persona: { persona_id: value || '' }
  })
});
const providerId = computed<string>({
  get: () => props.modelValue.model?.provider_id || '',
  set: value => emit('update:modelValue', {
    model: { provider_id: value || '' }, persona: { persona_id: props.modelValue.persona?.persona_id || '' }
  })
});

onMounted(async () => {
  loading.value = true;
  try {
    const [personaResponse, providerResponse] = await Promise.all([
      personaApi.list(), providerApi.listByProviderType('chat_completion')
    ]);
    personas.value = personaResponse.data.data.map((persona: { persona_id: string }) => persona.persona_id);
    providers.value = providerResponse.data.data
      .filter(provider => provider.enable !== false)
      .flatMap(provider => typeof provider.id === 'string' ? [provider.id] : []);
  } catch (err: any) {
    error.value = err.response?.data?.message || String(err);
  } finally {
    loading.value = false;
  }
});
</script>

<style scoped>
.native-config-fields { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.native-config-hint { margin: 16px 0 0; font-size: .8125rem; line-height: 1.6; }
@media (max-width: 599px) { .native-config-fields { grid-template-columns: 1fr; } }
</style>
