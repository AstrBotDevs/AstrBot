import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';
import { computed, ref } from 'vue';
import { parse } from 'vue/compiler-sfc';

function setup(status, modelValue = {}) {
  const source = readFileSync(new URL('../src/components/shared/LocalPermissionMatrix.vue', import.meta.url), 'utf8');
  const { descriptor } = parse(source);
  const props = { modelValue };
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
  const component = vm.runInContext(`${script}\n${setupScript}\n;({ policy, updatePermission, runtime })`, scope);
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

test('only incompatible execution policies show the role fallback', () => {
  for (const scope of ['workspace', 'host']) {
    const configured = { filesystem_scope: scope, allow_execution: true, allow_network: false };
    const original = structuredClone(configured);
    const { policy } = setup('unavailable', { member: configured, admin: configured });
    assert.deepEqual(policy('member'), { filesystem_scope: 'workspace', allow_execution: false, allow_network: false });
    assert.deepEqual(policy('admin'), { filesystem_scope: 'host', allow_execution: true, allow_network: true });
    assert.deepEqual(configured, original);
  }
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
