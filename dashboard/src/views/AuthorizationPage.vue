<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import {
  authorizationApi,
  type AuthorizationBinding,
} from '@/api/v1/authorization';
import { useI18n } from '@/i18n/composables';

type AuditRecord = {
  audit_id: string;
  timestamp: string;
  subject_id: string;
  action: string;
  resource_id: string;
  decision: string;
  reason: string;
  source?: string;
};

type DashboardAccount = {
  account_id: string;
  username: string;
  is_active: boolean;
  created_at?: string;
  last_login_at?: string | null;
};

const { t } = useI18n();
const bindings = ref<AuthorizationBinding[]>([]);
const audit = ref<AuditRecord[]>([]);
const accounts = ref<DashboardAccount[]>([]);
const loading = ref(false);
const tab = ref('bindings');
const query = ref('');
const selected = ref<string[]>([]);
const revokeDialog = ref(false);
const stepUpDialog = ref(false);
const stepUpPassword = ref('');
const stepUpToken = ref<string | null>(null);
const stepUpTarget = ref<{
  action: string;
  resourceType: string;
  resourceId: string;
} | null>(null);

const filteredBindings = computed(() => {
  const needle = query.value.trim().toLowerCase();
  if (!needle) return bindings.value;
  return bindings.value.filter((binding) =>
    [
      binding.subject_id,
      binding.role,
      binding.scope_type,
      binding.scope_id,
      binding.source,
    ]
      .filter(Boolean)
      .join(' ')
      .toLowerCase()
      .includes(needle),
  );
});

function isExpired(binding: AuthorizationBinding): boolean {
  return Boolean(
    binding.expires_at && new Date(binding.expires_at) <= new Date(),
  );
}

function isAutoFact(binding: AuthorizationBinding): boolean {
  return binding.source === 'adapter' || binding.source === 'platform';
}

function canRevoke(binding: AuthorizationBinding): boolean {
  return !isAutoFact(binding) && !isExpired(binding);
}

async function refresh() {
  loading.value = true;
  try {
    const [bindingResponse, auditResponse, accountResponse] = await Promise.all(
      [
        authorizationApi.bindings(),
        authorizationApi.audit(),
        authorizationApi.accounts(),
      ],
    );
    bindings.value = bindingResponse.data?.data ?? [];
    audit.value = (auditResponse.data?.data ?? []) as AuditRecord[];
    accounts.value = (accountResponse.data?.data ?? []) as DashboardAccount[];
    selected.value = selected.value.filter((id) =>
      bindings.value.some((binding) => binding.binding_id === id),
    );
  } finally {
    loading.value = false;
  }
}

function openStepUp(action: string, resourceType: string, resourceId: string) {
  stepUpTarget.value = { action, resourceType, resourceId };
  stepUpPassword.value = '';
  stepUpToken.value = null;
  stepUpDialog.value = true;
}

async function issueStepUp() {
  if (!stepUpTarget.value || !stepUpPassword.value) return;
  const response = await authorizationApi.stepUp({
    action: stepUpTarget.value.action,
    resource_type: stepUpTarget.value.resourceType,
    resource_id: stepUpTarget.value.resourceId,
    password: stepUpPassword.value,
  });
  stepUpToken.value = response.data?.data?.token ?? null;
}

async function revokeSelected() {
  if (!stepUpToken.value) return;
  const targets = bindings.value.filter(
    (binding) =>
      selected.value.includes(binding.binding_id) && canRevoke(binding),
  );
  for (const binding of targets) {
    await authorizationApi.revoke(binding.binding_id, stepUpToken.value);
  }
  revokeDialog.value = false;
  stepUpDialog.value = false;
  await refresh();
}

function beginBulkRevoke() {
  if (!selected.value.length) return;
  revokeDialog.value = true;
}

function confirmBulkRevoke() {
  openStepUp('identity.manage', 'identity', 'bindings');
}

onMounted(refresh);
</script>

<template>
  <v-container fluid class="pa-6">
    <div class="d-flex align-center mb-5">
      <div>
        <h1 class="text-h5">{{ t('features.authorization.title') }}</h1>
        <p class="text-body-2 text-medium-emphasis mb-0">
          {{ t('features.authorization.description') }}
        </p>
      </div>
      <v-spacer />
      <v-btn icon="mdi-refresh" :loading="loading" @click="refresh" />
    </div>

    <v-tabs v-model="tab" color="primary">
      <v-tab value="bindings">{{ t('features.authorization.bindings') }}</v-tab>
      <v-tab value="accounts">{{ t('features.authorization.accounts') }}</v-tab>
      <v-tab value="audit">{{ t('features.authorization.audit') }}</v-tab>
    </v-tabs>

    <v-window v-model="tab" class="mt-4">
      <v-window-item value="bindings">
        <div class="d-flex align-center ga-3 mb-3">
          <v-text-field
            v-model="query"
            density="compact"
            hide-details
            prepend-inner-icon="mdi-magnify"
            :label="t('features.authorization.filter')"
          />
          <v-btn
            color="error"
            variant="tonal"
            :disabled="!selected.length"
            @click="beginBulkRevoke"
          >
            {{ t('features.authorization.revokeSelected') }}
          </v-btn>
        </div>
        <v-table density="compact">
          <thead>
            <tr>
              <th />
              <th>{{ t('features.authorization.subject') }}</th>
              <th>{{ t('features.authorization.role') }}</th>
              <th>{{ t('features.authorization.scope') }}</th>
              <th>{{ t('features.authorization.source') }}</th>
              <th>{{ t('features.authorization.status') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="binding in filteredBindings" :key="binding.binding_id">
              <td>
                <v-checkbox-btn
                  v-if="canRevoke(binding)"
                  v-model="selected"
                  :value="binding.binding_id"
                />
                <v-tooltip
                  v-else
                  :text="t('features.authorization.readOnlyFact')"
                >
                  <template #activator="{ props }">
                    <v-icon
                      v-bind="props"
                      icon="mdi-lock-outline"
                      size="small"
                    />
                  </template>
                </v-tooltip>
              </td>
              <td class="text-break">{{ binding.subject_id }}</td>
              <td>{{ binding.role }}</td>
              <td>{{ binding.scope_type }}: {{ binding.scope_id }}</td>
              <td>{{ binding.source }}</td>
              <td>
                <v-chip
                  v-if="isExpired(binding)"
                  size="x-small"
                  color="warning"
                >
                  {{ t('features.authorization.expired') }}
                </v-chip>
                <v-chip v-else size="x-small" color="success">
                  {{ t('features.authorization.active') }}
                </v-chip>
              </td>
            </tr>
          </tbody>
        </v-table>
      </v-window-item>

      <v-window-item value="accounts">
        <v-table density="compact">
          <thead>
            <tr>
              <th>{{ t('features.authorization.account') }}</th>
              <th>{{ t('features.authorization.username') }}</th>
              <th>{{ t('features.authorization.status') }}</th>
              <th>{{ t('features.authorization.lastLogin') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="account in accounts" :key="account.account_id">
              <td>{{ account.account_id }}</td>
              <td>{{ account.username }}</td>
              <td>
                {{
                  account.is_active
                    ? t('features.authorization.active')
                    : t('features.authorization.disabled')
                }}
              </td>
              <td>{{ account.last_login_at || '—' }}</td>
            </tr>
          </tbody>
        </v-table>
      </v-window-item>

      <v-window-item value="audit">
        <v-table density="compact">
          <thead>
            <tr>
              <th>{{ t('features.authorization.time') }}</th>
              <th>{{ t('features.authorization.subject') }}</th>
              <th>{{ t('features.authorization.action') }}</th>
              <th>{{ t('features.authorization.source') }}</th>
              <th>{{ t('features.authorization.status') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="record in audit" :key="record.audit_id">
              <td>{{ record.timestamp }}</td>
              <td class="text-break">{{ record.subject_id }}</td>
              <td>{{ record.action }}</td>
              <td>{{ record.source || '—' }}</td>
              <td>{{ record.decision }}</td>
            </tr>
          </tbody>
        </v-table>
      </v-window-item>
    </v-window>

    <v-dialog v-model="revokeDialog" max-width="460">
      <v-card>
        <v-card-title>{{
          t('features.authorization.confirmRevokeTitle')
        }}</v-card-title>
        <v-card-text>{{
          t('features.authorization.confirmRevokeText', {
            count: selected.length,
          })
        }}</v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="revokeDialog = false">{{
            t('features.authorization.cancel')
          }}</v-btn>
          <v-btn color="error" @click="confirmBulkRevoke">{{
            t('features.authorization.continue')
          }}</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="stepUpDialog" max-width="460">
      <v-card>
        <v-card-title>{{
          t('features.authorization.stepUpTitle')
        }}</v-card-title>
        <v-card-text>
          {{ t('features.authorization.stepUpText') }}
          <v-text-field
            v-model="stepUpPassword"
            class="mt-4"
            type="password"
            autocomplete="current-password"
            :label="t('features.authorization.password')"
          />
          <v-alert v-if="stepUpToken" type="success" variant="tonal">
            {{ t('features.authorization.stepUpReady') }}
          </v-alert>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="stepUpDialog = false">{{
            t('features.authorization.cancel')
          }}</v-btn>
          <v-btn
            v-if="!stepUpToken"
            color="primary"
            :disabled="!stepUpPassword"
            @click="issueStepUp"
          >
            {{ t('features.authorization.verify') }}
          </v-btn>
          <v-btn v-else color="error" @click="revokeSelected">{{
            t('features.authorization.revokeSelected')
          }}</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-container>
</template>
