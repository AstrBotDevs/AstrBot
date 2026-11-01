import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';
import { computed, ref, shallowReactive } from 'vue';
import { parse } from 'vue/compiler-sfc';

function setup(status, modelValue = {}) {
  const source = readFileSync(new URL('../src/components/shared/LocalPermissionMatrix.vue', import.meta.url), 'utf8');
  const { descriptor } = parse(source);
  const props = shallowReactive({ modelValue });
  let saved;
  const scope = vm.createContext({
    computed, ref,
    defineProps: () => props,
    defineEmits: () => (_event, value) => { saved = value; props.modelValue = value; },
    onMounted() {},
    useModuleI18n: () => ({ tm: key => key }),
  });
  const script = descriptor.script.content.replace('export const', 'const');
  const setupScript = descriptor.scriptSetup.content.replace(/^import .*$/gm, '');
  const component = vm.runInContext(`${script}\n${setupScript}\n;({ policy, updatePermission, runtime, executionBlockedRoles, isolationFailureReason, permissionLocks })`, scope);
  component.runtime.value = { os: status === 'unsupported' ? 'windows' : 'linux', sandbox: { status } };
  return {
    component,
    policy: role => JSON.parse(JSON.stringify(component.policy(role))),
    saved: () => JSON.parse(JSON.stringify(saved)),
  };
}

test('default effective permissions are identical with or without Local isolation', () => {
  for (const status of ['detected', 'missing', 'unavailable', 'unsupported']) {
    const { policy } = setup(status);
    assert.deepEqual(policy('member'), { filesystem_scope: 'workspace', allow_execution: false, allow_network: false });
    assert.deepEqual(policy('admin'), { filesystem_scope: 'host', allow_execution: true, allow_network: true });
  }
});

test('unavailable isolation preserves compatible policies and disabled access', () => {
  for (const role of ['member', 'admin']) {
    for (const configured of [
      { filesystem_scope: 'host', allow_execution: true, allow_network: true },
      { filesystem_scope: 'workspace', allow_execution: false, allow_network: false },
      { filesystem_scope: 'host', allow_execution: false, allow_network: false },
      { filesystem_scope: 'none', allow_execution: false, allow_network: false },
    ]) {
      assert.deepEqual(setup('unsupported', { [role]: configured }).policy(role), configured);
    }
  }
});

test('unavailable isolation disables execution without widening any saved policy', () => {
  for (const status of ['missing', 'unavailable', 'unsupported']) {
    for (const [scope, network] of [['workspace', false], ['workspace', true], ['host', false]]) {
      const configured = { filesystem_scope: scope, allow_execution: true, allow_network: network };
      const original = structuredClone(configured);
      const { component, policy } = setup(status, { member: configured, admin: configured });
      for (const role of ['member', 'admin']) {
        assert.deepEqual(policy(role), { filesystem_scope: scope, allow_execution: false, allow_network: false });
        assert.equal(component.policy(role, false).allow_execution, true);
        assert.equal(component.permissionLocks.value[role].execution, false);
      }
      assert.deepEqual(Array.from(component.executionBlockedRoles.value), ['member', 'admin']);
      component.runtime.value.sandbox.error = 'Probe timed out after 5 seconds';
      assert.match(component.isolationFailureReason.value, /Probe timed out after 5 seconds/);
      assert.deepEqual(configured, original);
      component.runtime.value.sandbox.status = 'detected';
      assert.deepEqual(policy('admin'), original);
      assert.deepEqual(Array.from(component.executionBlockedRoles.value), []);
    }
  }
});

test('a saved execution grant can be unchecked while isolation is unavailable', () => {
  for (const status of ['missing', 'unavailable', 'unsupported']) {
    for (const role of ['member', 'admin']) {
      const { component, saved } = setup(status, {
        [role]: { filesystem_scope: 'workspace', allow_execution: true, allow_network: true },
      });
      assert.equal(component.permissionLocks.value[role].execution, false);
      component.updatePermission(role, { allow_execution: false });
      assert.deepEqual(saved()[role], { filesystem_scope: 'workspace', allow_execution: false, allow_network: false });
      assert.deepEqual(Array.from(component.executionBlockedRoles.value), []);
      assert.equal(component.permissionLocks.value[role].execution, true);
    }
  }
});

test('editing file scope preserves saved execution and network restrictions', () => {
  for (const network of [false, true]) {
    const { component, saved, policy } = setup('unsupported', {
      admin: { filesystem_scope: 'workspace', allow_execution: true, allow_network: network },
    });
    component.updatePermission('admin', { filesystem_scope: 'host' });
    assert.deepEqual(saved().admin, { filesystem_scope: 'host', allow_execution: true, allow_network: network });
    assert.equal(policy('admin').allow_execution, network);
    component.runtime.value.sandbox.status = 'detected';
    assert.equal(policy('admin').allow_execution, true);
    component.updatePermission('admin', { filesystem_scope: 'none' });
    assert.deepEqual(saved().admin, { filesystem_scope: 'none', allow_execution: false, allow_network: false });
  }
});

test('editing another role does not overwrite an execution policy blocked by isolation', () => {
  const configured = { filesystem_scope: 'workspace', allow_execution: true, allow_network: false };
  const { component, saved } = setup('missing', { admin: configured });
  component.updatePermission('member', { filesystem_scope: 'none' });
  assert.deepEqual(saved().admin, configured);
});

test('choosing entire-environment execution synchronizes the hidden network permission', () => {
  const { component, policy, saved } = setup('unsupported', {
    member: { filesystem_scope: 'host', allow_execution: true, allow_network: false },
  });
  assert.equal(policy('member').allow_execution, false);
  component.updatePermission('member', { filesystem_scope: 'host' });
  component.updatePermission('member', { allow_execution: true });
  assert.deepEqual(saved().member, { filesystem_scope: 'host', allow_execution: true, allow_network: true });
  assert.deepEqual(policy('member'), saved().member);
});
