<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import {
  authorizationApi,
  type AuthorizationBinding,
  type AuthorizationBindingRequest,
} from '@/api/v1/authorization';
import { useI18n } from '@/i18n/composables';
import { resolveErrorMessage } from '@/utils/errorUtils';
import { useToast } from '@/utils/toast';
import DashboardStepUpDialog from '@/components/shared/DashboardStepUpDialog.vue';

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

type ResourceDescriptor = {
  resourceType: string;
  resourceId: string;
  configId?: string | null;
};

type ProtectedOperation = {
  kind: 'single' | 'batch';
  action: string;
  resource?: ResourceDescriptor;
  bindingIds?: string[];
  execute: (token: string) => Promise<void>;
  successMessage: string;
};

type BindingForm = {
  bindingId: string | null;
  subjectId: string;
  role: AuthorizationBindingRequest['role'];
  scopeType: AuthorizationBindingRequest['scope_type'];
  scopeId: string;
  configId: string;
  expiresAt: string;
};

type AccountForm = {
  accountId: string | null;
  username: string;
  password: string;
  role: 'operator' | 'root';
  isActive: boolean;
};

const { t } = useI18n();
const { success: showSuccess, error: showError } = useToast();
const bindings = ref<AuthorizationBinding[]>([]);
const audit = ref<AuditRecord[]>([]);
const accounts = ref<DashboardAccount[]>([]);
const loading = ref(false);
const submitting = ref(false);
const tab = ref('bindings');
const query = ref('');
const selected = ref<string[]>([]);
const revokeDialog = ref(false);
const bindingDialog = ref(false);
const accountDialog = ref(false);
const stepUpDialog = ref(false);
const stepUpError = ref('');
const pendingOperation = ref<ProtectedOperation | null>(null);
const bindingForm = ref<BindingForm>(emptyBindingForm());
const accountForm = ref<AccountForm>(emptyAccountForm());

const roles: AuthorizationBindingRequest['role'][] = [
  'member',
  'session_admin',
  'session_owner',
  'instance_operator',
  'operator',
  'root',
];
const scopes: AuthorizationBindingRequest['scope_type'][] = [
  'session',
  'instance',
  'resource',
  'global',
];

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

function emptyBindingForm(): BindingForm {
  return {
    bindingId: null,
    subjectId: '',
    role: 'session_admin',
    scopeType: 'session',
    scopeId: '',
    configId: '',
    expiresAt: '',
  };
}

function emptyAccountForm(): AccountForm {
  return {
    accountId: null,
    username: '',
    password: '',
    role: 'operator',
    isActive: true,
  };
}

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

function localDateTime(value?: string | null): string {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}

function bindingResource(binding: AuthorizationBinding): ResourceDescriptor {
  if (binding.scope_type === 'session') {
    return {
      resourceType: 'session',
      resourceId: binding.scope_id,
      configId: binding.config_id,
    };
  }
  if (binding.scope_type === 'instance') {
    return {
      resourceType: 'instance',
      resourceId: binding.config_id || binding.scope_id,
      configId: binding.config_id,
    };
  }
  return {
    resourceType: 'identity',
    resourceId: binding.subject_id,
    configId: binding.config_id,
  };
}

function bindingAction(
  role: AuthorizationBindingRequest['role'],
  scopeType: AuthorizationBindingRequest['scope_type'],
): string {
  if (role === 'root') return 'identity.root.write';
  if (role === 'operator' || scopeType === 'global') {
    return 'identity.operator.write';
  }
  return 'identity.manage';
}

async function refresh() {
  loading.value = true;
  try {
    const [bindingResponse, auditResponse] = await Promise.all([
      authorizationApi.bindings(),
      authorizationApi.audit(),
    ]);
    bindings.value = bindingResponse.data?.data ?? [];
    audit.value = (auditResponse.data?.data ?? []) as AuditRecord[];
    selected.value = selected.value.filter((id) =>
      bindings.value.some((binding) => binding.binding_id === id),
    );
    try {
      const accountResponse = await authorizationApi.accounts();
      accounts.value = (accountResponse.data?.data ?? []) as DashboardAccount[];
    } catch {
      // Account listing is intentionally unavailable to instance-scoped roles.
      accounts.value = [];
    }
  } catch (error) {
    showError(
      resolveErrorMessage(error, t('features.authorization.loadFailed')),
    );
  } finally {
    loading.value = false;
  }
}

function openProtectedOperation(operation: ProtectedOperation) {
  pendingOperation.value = operation;
  stepUpError.value = '';
  stepUpDialog.value = true;
}

async function executeProtectedOperation(credentials: {
  password?: string;
  code?: string;
}) {
  const operation = pendingOperation.value;
  if (!operation || (!credentials.password && !credentials.code)) return;

  submitting.value = true;
  stepUpError.value = '';
  try {
    let token: string | undefined;
    if (operation.kind === 'batch') {
      const response = await authorizationApi.issueBatchRevokeStepUp({
        binding_ids: operation.bindingIds || [],
        password: credentials.password,
        code: credentials.code,
      });
      token = response.data?.data?.token;
    } else if (operation.resource) {
      const response = await authorizationApi.stepUp({
        action: operation.action,
        resource_type: operation.resource.resourceType,
        resource_id: operation.resource.resourceId,
        config_id: operation.resource.configId || undefined,
        password: credentials.password,
        code: credentials.code,
      });
      token = response.data?.data?.token;
    }
    if (!token) {
      showError(t('features.authorization.stepUpRequired'));
      return;
    }
    await operation.execute(token);
    stepUpDialog.value = false;
    pendingOperation.value = null;
    showSuccess(operation.successMessage);
    await refresh();
  } catch (error) {
    stepUpError.value = resolveErrorMessage(
      error,
      t('features.authorization.actionFailed'),
    );
  } finally {
    submitting.value = false;
  }
}

function cancelProtectedOperation() {
  if (submitting.value) return;
  stepUpDialog.value = false;
  stepUpError.value = '';
  pendingOperation.value = null;
}

function openCreateBinding() {
  bindingForm.value = emptyBindingForm();
  bindingDialog.value = true;
}

function openEditBinding(binding: AuthorizationBinding) {
  bindingForm.value = {
    bindingId: binding.binding_id,
    subjectId: binding.subject_id,
    role: binding.role as AuthorizationBindingRequest['role'],
    scopeType: binding.scope_type as AuthorizationBindingRequest['scope_type'],
    scopeId: binding.scope_id,
    configId: binding.config_id || '',
    expiresAt: localDateTime(binding.expires_at),
  };
  bindingDialog.value = true;
}

function submitBinding() {
  const form = bindingForm.value;
  if (!form.subjectId || !form.scopeId) return;
  const payload: AuthorizationBindingRequest = {
    subject_id: form.subjectId.trim(),
    role: form.role,
    scope_type: form.scopeType,
    scope_id: form.scopeId.trim(),
    config_id: form.configId.trim() || null,
    expires_at: form.expiresAt ? new Date(form.expiresAt).toISOString() : null,
  };
  const resource = bindingResource({
    binding_id: form.bindingId || 'new-binding',
    subject_id: payload.subject_id,
    role: payload.role,
    scope_type: payload.scope_type,
    scope_id: payload.scope_id,
    config_id: payload.config_id,
    source: 'explicit',
  });
  openProtectedOperation({
    kind: 'single',
    action: bindingAction(payload.role, payload.scope_type),
    resource,
    execute: async (token) => {
      await authorizationApi.grant(payload, token);
      bindingDialog.value = false;
    },
    successMessage: form.bindingId
      ? t('features.authorization.bindingUpdated')
      : t('features.authorization.bindingGranted'),
  });
}

function beginBulkRevoke() {
  const ids = bindings.value
    .filter(
      (binding) =>
        selected.value.includes(binding.binding_id) && canRevoke(binding),
    )
    .map((binding) => binding.binding_id);
  if (!ids.length) return;
  selected.value = ids;
  revokeDialog.value = true;
}

function confirmBulkRevoke() {
  const bindingIds = [...selected.value];
  revokeDialog.value = false;
  openProtectedOperation({
    kind: 'batch',
    action: 'identity.manage',
    bindingIds,
    execute: async (token) => {
      await authorizationApi.revokeBatch(bindingIds, token);
    },
    successMessage: t('features.authorization.bindingsRevoked'),
  });
}

function openCreateAccount() {
  accountForm.value = emptyAccountForm();
  accountDialog.value = true;
}

function openEditAccount(account: DashboardAccount) {
  accountForm.value = {
    accountId: account.account_id,
    username: account.username,
    password: '',
    role: 'operator',
    isActive: account.is_active,
  };
  accountDialog.value = true;
}

function submitAccount() {
  const form = accountForm.value;
  if (!form.username || (!form.accountId && !form.password)) return;
  if (form.accountId) {
    openProtectedOperation({
      kind: 'single',
      action: 'dashboard.account.manage',
      resource: {
        resourceType: 'dashboard-account',
        resourceId: form.accountId,
      },
      execute: async (token) => {
        await authorizationApi.updateAccount(
          form.accountId as string,
          {
            username: form.username.trim(),
            password: form.password || undefined,
            is_active: form.isActive,
          },
          token,
        );
        accountDialog.value = false;
      },
      successMessage: t('features.authorization.accountUpdated'),
    });
    return;
  }
  openProtectedOperation({
    kind: 'single',
    action:
      form.role === 'root' ? 'identity.root.write' : 'identity.operator.write',
    resource: {
      resourceType: 'dashboard-account',
      resourceId: form.username.trim(),
    },
    execute: async (token) => {
      await authorizationApi.createAccount(
        {
          username: form.username.trim(),
          password: form.password,
          role: form.role,
        },
        token,
      );
      accountDialog.value = false;
    },
    successMessage: t('features.authorization.accountCreated'),
  });
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
      <v-btn
        icon="mdi-refresh"
        :loading="loading"
        :aria-label="t('features.authorization.refresh')"
        @click="refresh"
      />
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
          <v-btn color="primary" @click="openCreateBinding">
            {{ t('features.authorization.grantBinding') }}
          </v-btn>
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
              <th>{{ t('features.authorization.actions') }}</th>
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
              <td>
                <v-btn
                  v-if="canRevoke(binding)"
                  size="small"
                  variant="text"
                  @click="openEditBinding(binding)"
                >
                  {{ t('features.authorization.edit') }}
                </v-btn>
              </td>
            </tr>
          </tbody>
        </v-table>
      </v-window-item>

      <v-window-item value="accounts">
        <div class="d-flex justify-end mb-3">
          <v-btn color="primary" @click="openCreateAccount">
            {{ t('features.authorization.createAccount') }}
          </v-btn>
        </div>
        <v-table density="compact">
          <thead>
            <tr>
              <th>{{ t('features.authorization.account') }}</th>
              <th>{{ t('features.authorization.username') }}</th>
              <th>{{ t('features.authorization.status') }}</th>
              <th>{{ t('features.authorization.lastLogin') }}</th>
              <th>{{ t('features.authorization.actions') }}</th>
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
              <td>
                <v-btn
                  size="small"
                  variant="text"
                  @click="openEditAccount(account)"
                >
                  {{ t('features.authorization.edit') }}
                </v-btn>
              </td>
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

    <v-dialog v-model="bindingDialog" max-width="600">
      <v-card>
        <v-card-title>
          {{
            bindingForm.bindingId
              ? t('features.authorization.editBinding')
              : t('features.authorization.grantBinding')
          }}
        </v-card-title>
        <v-card-text>
          <v-text-field
            v-model="bindingForm.subjectId"
            :label="t('features.authorization.subject')"
          />
          <v-select
            v-model="bindingForm.role"
            :items="roles"
            :label="t('features.authorization.role')"
          />
          <v-select
            v-model="bindingForm.scopeType"
            :items="scopes"
            :label="t('features.authorization.scopeType')"
          />
          <v-text-field
            v-model="bindingForm.scopeId"
            :label="t('features.authorization.scopeId')"
            :hint="t('features.authorization.scopeIdHint')"
            persistent-hint
          />
          <v-text-field
            v-model="bindingForm.configId"
            :label="t('features.authorization.configId')"
          />
          <v-text-field
            v-model="bindingForm.expiresAt"
            type="datetime-local"
            :label="t('features.authorization.expiresAt')"
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="bindingDialog = false">
            {{ t('features.authorization.cancel') }}
          </v-btn>
          <v-btn
            color="primary"
            :disabled="!bindingForm.subjectId || !bindingForm.scopeId"
            @click="submitBinding"
          >
            {{ t('features.authorization.continue') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="accountDialog" max-width="560">
      <v-card>
        <v-card-title>
          {{
            accountForm.accountId
              ? t('features.authorization.editAccount')
              : t('features.authorization.createAccount')
          }}
        </v-card-title>
        <v-card-text>
          <v-text-field
            v-model="accountForm.username"
            :label="t('features.authorization.username')"
          />
          <v-text-field
            v-model="accountForm.password"
            type="password"
            autocomplete="new-password"
            :label="
              accountForm.accountId
                ? t('features.authorization.newPasswordOptional')
                : t('features.authorization.password')
            "
          />
          <v-select
            v-if="!accountForm.accountId"
            v-model="accountForm.role"
            :items="['operator', 'root']"
            :label="t('features.authorization.role')"
          />
          <v-switch
            v-if="accountForm.accountId"
            v-model="accountForm.isActive"
            color="primary"
            :label="t('features.authorization.accountActive')"
            hide-details
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn @click="accountDialog = false">
            {{ t('features.authorization.cancel') }}
          </v-btn>
          <v-btn
            color="primary"
            :disabled="
              !accountForm.username ||
              (!accountForm.accountId && !accountForm.password)
            "
            @click="submitAccount"
          >
            {{ t('features.authorization.continue') }}
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

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

    <DashboardStepUpDialog
      v-model="stepUpDialog"
      :loading="submitting"
      :error-message="stepUpError"
      @confirm="executeProtectedOperation"
      @cancel="cancelProtectedOperation"
    />
  </v-container>
</template>
