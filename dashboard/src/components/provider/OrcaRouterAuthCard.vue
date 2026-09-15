<template>
  <section class="orca-auth-card">
    <div class="orca-auth-card__head">
      <div>
        <h3 class="orca-auth-card__title">{{ tm('providerSources.orcarouter.title') }}</h3>
        <p class="orca-auth-card__subtitle">
          {{ tm('providerSources.orcarouter.subtitle') }}
        </p>
      </div>
      <v-chip
        size="small"
        variant="tonal"
        :color="hasKey ? 'success' : 'warning'"
        label
        class="orca-auth-card__status"
      >
        {{ hasKey ? tm('providerSources.orcarouter.keyPresent') : tm('providerSources.orcarouter.keyMissing') }}
      </v-chip>
    </div>

    <!-- Choice 1: an existing API key -->
    <div class="orca-auth-method" data-testid="orca-auth-method-api-key">
      <div class="orca-auth-method__head">
        <v-icon size="18">mdi-key-variant</v-icon>
        <span class="orca-auth-method__label">
          {{ tm('providerSources.orcarouter.apiKeyLabel') }}
        </span>
      </div>
      <p class="orca-auth-method__hint">{{ tm('providerSources.orcarouter.apiKeyHint') }}</p>
      <div class="orca-auth-method__row">
        <v-text-field
          v-model="apiKeyDraft"
          :type="showApiKey ? 'text' : 'password'"
          :label="tm('providerSources.orcarouter.apiKeyField')"
          :placeholder="tm('providerSources.orcarouter.apiKeyPlaceholder')"
          :append-inner-icon="showApiKey ? 'mdi-eye-off' : 'mdi-eye'"
          density="compact"
          variant="solo-filled"
          flat
          hide-details
          autocomplete="off"
          data-testid="orca-api-key-input"
          @click:append-inner="showApiKey = !showApiKey"
        />
        <v-btn
          color="primary"
          variant="tonal"
          rounded="xl"
          :disabled="!apiKeyDirty"
          data-testid="orca-api-key-save"
          @click="saveApiKey"
        >
          {{ tm('providerSources.orcarouter.apiKeySave') }}
        </v-btn>
        <v-btn
          variant="text"
          rounded="xl"
          :disabled="!hasKey"
          data-testid="orca-api-key-clear"
          @click="clearApiKey"
        >
          {{ tm('providerSources.orcarouter.apiKeyClear') }}
        </v-btn>
      </div>
      <p class="orca-auth-method__meta">
        <span data-testid="orca-key-masked">{{ maskedKey }}</span>
        <a
          :href="keyDashboardUrl"
          target="_blank"
          rel="noopener noreferrer"
          class="orca-auth-method__link"
        >{{ tm('providerSources.orcarouter.keyDashboard') }}</a>
      </p>
    </div>

    <!-- Choice 2: authorize with an OrcaRouter account -->
    <div class="orca-auth-method" data-testid="orca-auth-method-pkce">
      <div class="orca-auth-method__head">
        <v-icon size="18">mdi-account-key-outline</v-icon>
        <span class="orca-auth-method__label">
          {{ tm('providerSources.orcarouter.connectLabel') }}
        </span>
      </div>
      <p class="orca-auth-method__hint">{{ tm('providerSources.orcarouter.connectHint') }}</p>

      <v-btn-toggle
        v-model="flow"
        density="compact"
        variant="outlined"
        divided
        mandatory
        class="orca-auth-flow"
        :disabled="busy"
        data-testid="orca-flow-toggle"
      >
        <v-btn value="loopback" size="small">
          {{ tm('providerSources.orcarouter.flowLoopback') }}
        </v-btn>
        <v-btn value="oob" size="small">
          {{ tm('providerSources.orcarouter.flowOob') }}
        </v-btn>
      </v-btn-toggle>
      <p class="orca-auth-method__hint orca-auth-method__hint--flow">
        {{ flow === 'loopback'
          ? tm('providerSources.orcarouter.flowLoopbackHint')
          : tm('providerSources.orcarouter.flowOobHint') }}
      </p>

      <div class="orca-auth-method__row">
        <v-btn
          color="primary"
          variant="tonal"
          rounded="xl"
          :loading="busy"
          data-testid="orca-connect"
          @click="startLogin"
        >
          {{ busy ? tm('providerSources.orcarouter.waiting') : tm('providerSources.orcarouter.connectButton') }}
        </v-btn>
        <v-btn
          v-if="busy"
          variant="text"
          rounded="xl"
          data-testid="orca-cancel"
          @click="cancelLogin('user')"
        >
          {{ tm('providerSources.orcarouter.cancel') }}
        </v-btn>
      </div>

      <div v-if="authorizeUrl" class="orca-auth-url" data-testid="orca-authorize-url">
        <p class="orca-auth-method__hint">{{ tm('providerSources.orcarouter.browserHint') }}</p>
        <div class="orca-auth-url__row">
          <code class="orca-auth-url__value">{{ authorizeUrl }}</code>
          <v-btn
            icon="mdi-content-copy"
            size="small"
            variant="text"
            :aria-label="tm('providerSources.orcarouter.copyUrl')"
            data-testid="orca-copy-url"
            @click="copyAuthorizeUrl"
          />
        </div>
      </div>

      <div v-if="authorizeUrl && flow === 'oob'" class="orca-auth-code">
        <v-text-field
          v-model="codeDraft"
          :label="tm('providerSources.orcarouter.codeLabel')"
          density="compact"
          variant="solo-filled"
          flat
          hide-details
          autocomplete="off"
          data-testid="orca-code-input"
        />
        <v-btn
          color="primary"
          variant="tonal"
          rounded="xl"
          :disabled="!codeDraft"
          data-testid="orca-code-submit"
          @click="submitCode"
        >
          {{ tm('providerSources.orcarouter.codeSubmit') }}
        </v-btn>
      </div>
    </div>

    <v-alert
      v-if="message"
      :type="messageType"
      density="compact"
      variant="tonal"
      class="orca-auth-alert"
      data-testid="orca-auth-message"
    >
      {{ message }}
    </v-alert>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useModuleI18n } from '@/i18n/composables'
import { orcaRouterApi } from '@/api/v1'
import { redactSecret } from '@/utils/secretMask'
const props = defineProps({
  source: { type: Object, required: true },
  saveSource: { type: Function, required: true }
})

const { tm } = useModuleI18n('features/provider')

const keyDashboardUrl = 'https://www.orcarouter.ai/console/tokens'

const apiKeyDraft = ref('')
const showApiKey = ref(false)
const flow = ref('loopback')
const busy = ref(false)
const authorizeUrl = ref('')
const codeDraft = ref('')
const message = ref('')
const messageType = ref('info')

// Monotonic attempt id. Every async response must still belong to the current
// generation before it is allowed to touch credentials or the UI.
let generation = 0
let activeAttemptId = ''

const keys = computed(() => {
  const value = props.source?.key
  if (Array.isArray(value)) return value.filter((item) => typeof item === 'string' && item)
  if (typeof value === 'string' && value) return [value]
  return []
})

const hasKey = computed(() => keys.value.length > 0)
const maskedKey = computed(() =>
  hasKey.value ? redactSecret(keys.value[0]) : tm('providerSources.orcarouter.keyMissing')
)
const apiKeyDirty = computed(() => apiKeyDraft.value.trim().length > 0)

function setMessage(text, type = 'info') {
  message.value = text
  messageType.value = type
}

function clearMessage() {
  message.value = ''
  messageType.value = 'info'
}

/** Release every UI-side trace of an in-flight login. */
function resetLoginState() {
  busy.value = false
  authorizeUrl.value = ''
  codeDraft.value = ''
  activeAttemptId = ''
}

async function saveApiKey() {
  const key = apiKeyDraft.value.trim()
  if (!key) return
  props.source.key = [key]
  const saved = await props.saveSource()
  if (saved) {
    apiKeyDraft.value = ''
    setMessage(tm('providerSources.orcarouter.apiKeySaved'), 'success')
  }
}

async function clearApiKey() {
  props.source.key = []
  const saved = await props.saveSource()
  if (saved) {
    setMessage(tm('providerSources.orcarouter.apiKeyCleared'), 'success')
  }
}

async function startLogin() {
  generation += 1
  const attempt = generation
  clearMessage()
  busy.value = true
  authorizeUrl.value = ''
  codeDraft.value = ''

  let payload
  try {
    payload = await orcaRouterApi.startLogin({ flow: flow.value, app_name: 'AstrBot' })
  } catch (error) {
    if (attempt !== generation) return
    busy.value = false
    setMessage(loginErrorText(error), 'error')
    return
  }

  // A newer attempt (or a pagehide) superseded this one while it was in flight.
  if (attempt !== generation) {
    const supersededId = payload?.data?.attempt_id || payload?.attempt_id
    if (supersededId) orcaRouterApi.cancelLogin(supersededId)
    return
  }

  const data = payload?.data || payload || {}
  activeAttemptId = data.attempt_id || ''
  authorizeUrl.value = data.authorize_url || ''

  if (flow.value === 'loopback') {
    pollUntilSettled(attempt)
  }
}

/**
 * Poll a loopback attempt until the redirect listener settles it. Loopback
 * login is completed server-side by the redirect, so polling is what collects
 * the key for a local browser.
 */
async function pollUntilSettled(attempt) {
  while (attempt === generation && busy.value) {
    await new Promise((resolve) => setTimeout(resolve, 1000))
    if (attempt !== generation || !busy.value) return

    let response
    try {
      response = await orcaRouterApi.loginStatus(activeAttemptId)
    } catch (error) {
      if (attempt !== generation) return
      resetLoginState()
      setMessage(loginErrorText(error), 'error')
      return
    }
    if (attempt !== generation) return

    const state = response?.data || response || {}
    if (state.status === 'completed') {
      if (attempt !== generation) return
      await adoptCredential(state)
      return
    }
    if (state.status === 'failed' || state.status === 'expired') {
      resetLoginState()
      setMessage(state.error || tm('providerSources.orcarouter.errorGeneric'), 'error')
      return
    }
    if (state.status === 'cancelled' || state.status === 'unknown') {
      resetLoginState()
      return
    }
  }
}

async function submitCode() {
  const attempt = generation
  const code = codeDraft.value.trim()
  if (!code) return
  busy.value = true
  try {
    const response = await orcaRouterApi.completeLogin(activeAttemptId, code)
    if (attempt !== generation) return
    await adoptCredential(response?.data || response || {})
  } catch (error) {
    if (attempt !== generation) return
    busy.value = false
    setMessage(loginErrorText(error), 'error')
  }
}

/** Store a PKCE-issued key through the same path a pasted key takes. */
async function adoptCredential(state) {
  if (!state.key) {
    resetLoginState()
    setMessage(tm('providerSources.orcarouter.errorGeneric'), 'error')
    return
  }
  props.source.key = [state.key]
  const saved = await props.saveSource()
  resetLoginState()
  if (saved) {
    setMessage(
      tm('providerSources.orcarouter.connectSuccess', {
        scope: state.scope || 'api'
      }),
      'success'
    )
  }
}

async function cancelLogin(reason) {
  // Invalidate first so any in-flight response is refused, then release the
  // server-side lock.
  generation += 1
  const attemptId = activeAttemptId
  resetLoginState()
  clearMessage()
  if (attemptId) {
    orcaRouterApi.cancelLogin(attemptId).catch(() => {})
  }
}

function copyAuthorizeUrl() {
  if (!authorizeUrl.value) return
  navigator.clipboard?.writeText(authorizeUrl.value)
  setMessage(tm('providerSources.orcarouter.copied'), 'success')
}

function loginErrorText(error) {
  const text = String(error?.response?.data?.message || error?.message || '')
  if (/denied|access_denied/i.test(text)) return tm('providerSources.orcarouter.errorDenied')
  if (/state/i.test(text)) return tm('providerSources.orcarouter.errorState')
  if (/expired/i.test(text)) return tm('providerSources.orcarouter.errorExpired')
  if (/24 hours|429|rate/i.test(text)) return tm('providerSources.orcarouter.errorRateLimited')
  if (/reach|network|timeout/i.test(text)) return tm('providerSources.orcarouter.errorNetwork')
  return text || tm('providerSources.orcarouter.errorGeneric')
}

/**
 * A page can be put into the back-forward cache on pagehide. The generation
 * guard would correctly refuse to mutate state afterwards, which would leave
 * the restored page permanently busy — so busy and hint state are cleared
 * synchronously here, and the server-side attempt is released with keepalive.
 */
function handlePageHide() {
  if (!busy.value && !authorizeUrl.value) return
  generation += 1
  const attemptId = activeAttemptId
  busy.value = false
  authorizeUrl.value = ''
  codeDraft.value = ''
  activeAttemptId = ''
  if (attemptId) orcaRouterApi.cancelLogin(attemptId, { keepalive: true }).catch(() => {})
}

onMounted(() => {
  window.addEventListener('pagehide', handlePageHide)
})

onBeforeUnmount(() => {
  window.removeEventListener('pagehide', handlePageHide)
  // Unmount releases the server-side work without writing UI state.
  generation += 1
  const attemptId = activeAttemptId
  activeAttemptId = ''
  if (attemptId) orcaRouterApi.cancelLogin(attemptId).catch(() => {})
})

// Switching authentication method abandons any login already in progress.
watch(flow, () => {
  if (busy.value || authorizeUrl.value) cancelLogin('flow-switch')
})

defineExpose({ startLogin, cancelLogin, submitCode, saveApiKey, clearApiKey, handlePageHide })
</script>

<style scoped>
.orca-auth-card {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.orca-auth-card__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}
.orca-auth-card__title {
  font-size: 1rem;
  font-weight: 600;
}
.orca-auth-card__subtitle {
  font-size: 0.8rem;
  opacity: 0.75;
}
.orca-auth-method {
  border: 1px solid rgba(var(--v-border-color), 0.24);
  border-radius: 10px;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.orca-auth-method__head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.orca-auth-method__label {
  font-weight: 600;
  font-size: 0.9rem;
}
.orca-auth-method__hint {
  font-size: 0.78rem;
  opacity: 0.75;
  margin: 0;
}
.orca-auth-method__hint--flow {
  margin-top: 4px;
}
.orca-auth-method__row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.orca-auth-method__row :deep(.v-field) {
  min-width: 260px;
}
.orca-auth-method__meta {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 0.78rem;
  opacity: 0.8;
  margin: 0;
}
.orca-auth-url__row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.orca-auth-url__value {
  font-size: 0.72rem;
  word-break: break-all;
  opacity: 0.85;
}
.orca-auth-code {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.orca-auth-code :deep(.v-field) {
  min-width: 220px;
}
</style>
