import assert from "node:assert/strict";
import { flushPromises } from "@vue/test-utils";
import { test, vi } from "vitest";
import { nextTick } from "vue";
import { statsApi } from "../src/api/v1.ts";
import LocalPermissionMatrix from "../src/components/shared/LocalPermissionMatrix.vue";
import { useModuleI18n } from "../src/i18n/composables.ts";
import { mountDashboard } from "./helpers/components.mjs";

async function setup(status, modelValue = {}, os = "linux") {
  vi.spyOn(statsApi, "version").mockResolvedValue({
    data: {
      data: {
        runtime: { os, sandbox: { status, backend: os === "windows" ? "appcontainer" : "bubblewrap" } },
      },
    },
  });
  let wrapper;
  const mounted = await mountDashboard(LocalPermissionMatrix, {
    props: {
      modelValue,
      "onUpdate:modelValue": (value) => wrapper.setProps({ modelValue: value }),
    },
  });
  wrapper = mounted.wrapper;
  await flushPromises();
  return {
    component: wrapper.vm,
    policy: (role) => JSON.parse(JSON.stringify(wrapper.vm.policy(role))),
    saved: () => JSON.parse(JSON.stringify(wrapper.emitted("update:modelValue").at(-1)[0])),
  };
}

test("default effective permissions are identical with or without Local isolation", async () => {
  for (const status of ["detected", "missing", "unavailable", "unsupported"]) {
    const { policy } = await setup(status);
    assert.deepEqual(policy("member"), { filesystem_scope: "workspace", allow_execution: false, allow_network: false });
    assert.deepEqual(policy("admin"), { filesystem_scope: "host", allow_execution: true, allow_network: true });
  }
});

test("unavailable isolation preserves compatible policies and disabled access", async () => {
  for (const role of ["member", "admin"]) {
    for (const configured of [
      { filesystem_scope: "host", allow_execution: true, allow_network: true },
      { filesystem_scope: "workspace", allow_execution: false, allow_network: false },
      { filesystem_scope: "host", allow_execution: false, allow_network: false },
      { filesystem_scope: "none", allow_execution: false, allow_network: false },
    ]) {
      assert.deepEqual((await setup("unsupported", { [role]: configured })).policy(role), configured);
    }
  }
});

test("unavailable isolation disables execution without widening any saved policy", async () => {
  for (const status of ["missing", "unavailable", "unsupported"]) {
    for (const [scope, network] of [
      ["workspace", false],
      ["workspace", true],
      ["host", false],
    ]) {
      const configured = { filesystem_scope: scope, allow_execution: true, allow_network: network };
      const original = structuredClone(configured);
      const { component, policy } = await setup(status, { member: configured, admin: configured });
      for (const role of ["member", "admin"]) {
        assert.deepEqual(policy(role), { filesystem_scope: scope, allow_execution: false, allow_network: false });
        assert.equal(component.policy(role, false).allow_execution, true);
        assert.equal(component.permissionLocks[role].execution, false);
      }
      assert.deepEqual(Array.from(component.executionBlockedRoles), ["member", "admin"]);
      component.runtime.sandbox.error = "Probe timed out after 5 seconds";
      assert.match(component.isolationFailureReason, /Probe timed out after 5 seconds/);
      assert.deepEqual(configured, original);
      component.runtime.sandbox.status = "detected";
      assert.deepEqual(policy("admin"), original);
      assert.deepEqual(Array.from(component.executionBlockedRoles), []);
    }
  }
});

test("a saved execution grant can be unchecked while isolation is unavailable", async () => {
  for (const status of ["missing", "unavailable", "unsupported"]) {
    for (const role of ["member", "admin"]) {
      const { component, saved } = await setup(status, {
        [role]: { filesystem_scope: "workspace", allow_execution: true, allow_network: true },
      });
      assert.equal(component.permissionLocks[role].execution, false);
      component.updatePermission(role, { allow_execution: false });
      await nextTick();
      assert.deepEqual(saved()[role], { filesystem_scope: "workspace", allow_execution: false, allow_network: false });
      assert.deepEqual(Array.from(component.executionBlockedRoles), []);
      assert.equal(component.permissionLocks[role].execution, true);
    }
  }
});

test("editing file scope preserves saved execution and network restrictions", async () => {
  for (const network of [false, true]) {
    const { component, saved, policy } = await setup("unsupported", {
      admin: { filesystem_scope: "workspace", allow_execution: true, allow_network: network },
    });
    component.updatePermission("admin", { filesystem_scope: "host" });
    await nextTick();
    assert.deepEqual(saved().admin, { filesystem_scope: "host", allow_execution: true, allow_network: network });
    assert.equal(policy("admin").allow_execution, network);
    component.runtime.sandbox.status = "detected";
    assert.equal(policy("admin").allow_execution, true);
    component.updatePermission("admin", { filesystem_scope: "none" });
    await nextTick();
    assert.deepEqual(saved().admin, { filesystem_scope: "none", allow_execution: false, allow_network: false });
  }
});

test("editing another role does not overwrite an execution policy blocked by isolation", async () => {
  const configured = { filesystem_scope: "workspace", allow_execution: true, allow_network: false };
  const { component, saved } = await setup("missing", { admin: configured });
  component.updatePermission("member", { filesystem_scope: "none" });
  await nextTick();
  assert.deepEqual(saved().admin, configured);
});

test("choosing entire-environment execution synchronizes the hidden network permission", async () => {
  const { component, policy, saved } = await setup("unsupported", {
    member: { filesystem_scope: "host", allow_execution: true, allow_network: false },
  });
  assert.equal(policy("member").allow_execution, false);
  component.updatePermission("member", { filesystem_scope: "host" });
  await nextTick();
  component.updatePermission("member", { allow_execution: true });
  await nextTick();
  assert.deepEqual(saved().member, { filesystem_scope: "host", allow_execution: true, allow_network: true });
  assert.deepEqual(policy("member"), saved().member);
});

test("Windows entire-environment execution always enables and locks networking", async () => {
  for (const status of ["detected", "unavailable"]) {
    const { component, saved } = await setup(
      status,
      {
        admin: { filesystem_scope: "workspace", allow_execution: true, allow_network: false },
      },
      "windows",
    );
    component.updatePermission("admin", { filesystem_scope: "host" });
    await nextTick();
    assert.deepEqual(saved().admin, { filesystem_scope: "host", allow_execution: true, allow_network: true });
    assert.equal(component.permissionLocks.admin.network, true);
    component.updatePermission("admin", { allow_network: false });
    await nextTick();
    assert.equal(saved().admin.allow_network, true);
    component.updatePermission("admin", { allow_execution: false });
    await nextTick();
    assert.equal(saved().admin.allow_network, false);
    component.updatePermission("admin", { allow_execution: true });
    await nextTick();
    assert.equal(saved().admin.allow_network, true);
  }
});

test("Windows workspace execution keeps independent network permission", async () => {
  const { component, saved } = await setup("detected", {}, "windows");
  component.updatePermission("member", { allow_execution: true });
  await nextTick();
  assert.equal(saved().member.allow_network, false);
  assert.equal(component.permissionLocks.member.network, false);
  component.updatePermission("member", { allow_network: true });
  await nextTick();
  assert.equal(saved().member.allow_network, true);
  component.updatePermission("member", { allow_network: false });
  await nextTick();
  assert.equal(saved().member.allow_network, false);
});

test("Windows startup failures retain saved workspace grants and identify AppContainer", async () => {
  const configured = { filesystem_scope: "workspace", allow_execution: true, allow_network: false };
  const { component, policy, saved } = await setup("unavailable", { admin: configured }, "windows");
  assert.deepEqual(policy("admin"), { ...configured, allow_execution: false });
  assert.equal(component.policy("admin", false).allow_execution, true);
  assert.deepEqual(Array.from(component.executionBlockedRoles), ["admin"]);
  assert.match(component.isolationFailureReason, /AppContainer/);
  assert.doesNotMatch(component.isolationFailureReason, /bubblewrap/);
  assert.equal(
    component.executionUnavailableHint,
    useModuleI18n("features/config-metadata.ai_group.agent_computer_use.local_permissions").tm(
      "runtime.windowsSetupHint",
    ),
  );
  component.updatePermission("member", { filesystem_scope: "none" });
  await nextTick();
  assert.deepEqual(saved().admin, configured);
  component.runtime.sandbox.status = "detected";
  assert.deepEqual(policy("admin"), configured);
});
