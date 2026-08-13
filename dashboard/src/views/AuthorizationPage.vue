<script setup lang="ts">
import { onMounted, ref } from 'vue';
import {
  authorizationApi,
  type AuthorizationBinding,
} from '@/api/v1/authorization';

const bindings = ref<AuthorizationBinding[]>([]);
const audit = ref<Record<string, unknown>[]>([]);
const accounts = ref<Record<string, unknown>[]>([]);
const loading = ref(false);
const tab = ref('bindings');
const elevation = ref({
  action: '',
  resource_type: 'dashboard-api',
  resource_id: 'global',
  config_id: '',
});
const elevationResult = ref<string | null>(null);

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
    audit.value = auditResponse.data?.data ?? [];
    accounts.value = accountResponse.data?.data ?? [];
  } finally {
    loading.value = false;
  }
}

async function requestElevation() {
  const response = await authorizationApi.requestElevation({
    ...elevation.value,
    config_id: elevation.value.config_id || null,
    approval_channel: 'dashboard',
  });
  const data = response.data?.data as
    { request_id?: string; nonce?: string } | undefined;
  elevationResult.value =
    data?.request_id && data?.nonce
      ? `Request ${data.request_id} created. Share the one-time approval nonce through a trusted channel.`
      : 'Elevation request created.';
}

async function revoke(bindingId: string) {
  await authorizationApi.revoke(bindingId);
  await refresh();
}

onMounted(refresh);
</script>

<template>
  <v-container fluid class="pa-6">
    <div class="d-flex align-center mb-5">
      <h1 class="text-h5">Authorization</h1>
      <v-spacer />
      <v-btn icon="mdi-refresh" :loading="loading" @click="refresh" />
    </div>
    <v-tabs v-model="tab" color="primary">
      <v-tab value="bindings">Bindings</v-tab>
      <v-tab value="accounts">Accounts</v-tab>
      <v-tab value="elevation">Elevation</v-tab>
      <v-tab value="audit">Audit</v-tab>
    </v-tabs>
    <v-window v-model="tab" class="mt-4">
      <v-window-item value="bindings">
        <v-table density="compact">
          <thead>
            <tr>
              <th>Subject</th>
              <th>Role</th>
              <th>Scope</th>
              <th>Source</th>
              <th />
            </tr>
          </thead>
          <tbody>
            <tr v-for="binding in bindings" :key="binding.binding_id">
              <td>{{ binding.subject_id }}</td>
              <td>{{ binding.role }}</td>
              <td>{{ binding.scope_type }}: {{ binding.scope_id }}</td>
              <td>{{ binding.source }}</td>
              <td>
                <v-btn
                  icon="mdi-delete-outline"
                  size="small"
                  @click="revoke(binding.binding_id)"
                />
              </td>
            </tr>
          </tbody>
        </v-table>
      </v-window-item>
      <v-window-item value="audit">
        <v-table density="compact">
          <thead>
            <tr>
              <th>Time</th>
              <th>Subject</th>
              <th>Action</th>
              <th>Decision</th>
              <th>Reason</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="record in audit" :key="String(record.audit_id)">
              <td>{{ record.timestamp }}</td>
              <td>{{ record.subject_id }}</td>
              <td>{{ record.action }}</td>
              <td>{{ record.decision }}</td>
              <td>{{ record.reason }}</td>
            </tr>
          </tbody>
        </v-table>
      </v-window-item>
      <v-window-item value="accounts">
        <v-table density="compact">
          <thead>
            <tr>
              <th>Account</th>
              <th>Username</th>
              <th>Status</th>
              <th>Last login</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="account in accounts" :key="String(account.account_id)">
              <td>{{ account.account_id }}</td>
              <td>{{ account.username }}</td>
              <td>{{ account.is_active ? 'active' : 'disabled' }}</td>
              <td>{{ account.last_login_at || '—' }}</td>
            </tr>
          </tbody>
        </v-table>
      </v-window-item>
      <v-window-item value="elevation">
        <v-card max-width="640" variant="outlined" class="pa-4">
          <v-text-field
            v-model="elevation.action"
            label="Action"
            hint="Exact authorization action"
          />
          <v-text-field
            v-model="elevation.resource_type"
            label="Resource type"
          />
          <v-text-field v-model="elevation.resource_id" label="Resource id" />
          <v-text-field
            v-model="elevation.config_id"
            label="Config id (optional)"
          />
          <v-btn
            color="primary"
            :disabled="!elevation.action"
            @click="requestElevation"
            >Request elevation</v-btn
          >
          <v-alert v-if="elevationResult" class="mt-3" type="info">{{
            elevationResult
          }}</v-alert>
        </v-card>
      </v-window-item>
    </v-window>
  </v-container>
</template>
