import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const skillsSectionSource = readFileSync(
  new URL("../src/components/extension/SkillsSection.vue", import.meta.url),
  "utf8",
);

function instantiateHandler(name, scope) {
  const startMarker = `    const ${name} =`;
  const start = skillsSectionSource.indexOf(startMarker);
  assert.notEqual(start, -1, `Missing ${name} handler`);

  const endMarker = "\n    };";
  const end = skillsSectionSource.indexOf(endMarker, start);
  assert.notEqual(end, -1, `Missing end of ${name} handler`);

  const declaration = skillsSectionSource.slice(start, end + endMarker.length);
  const scopeNames = Object.keys(scope);
  const factory = new Function(
    ...scopeNames,
    `"use strict";\n${declaration}\nreturn ${name};`,
  );
  return factory(...scopeNames.map((scopeName) => scope[scopeName]));
}

test("batch deletion runs serially and resets selection after success", async () => {
  const calls = [];
  const messages = [];
  const skills = { value: [{ name: "alpha" }, { name: "beta" }] };
  let activeRequests = 0;
  let maxActiveRequests = 0;
  let fetchCount = 0;

  const scope = {
    batchDeleting: { value: false },
    batchDeleteTargets: { value: ["alpha", "beta"] },
    skillApi: {
      delete: async (name) => {
        calls.push(name);
        activeRequests += 1;
        maxActiveRequests = Math.max(maxActiveRequests, activeRequests);
        await new Promise((resolve) => setImmediate(resolve));
        activeRequests -= 1;
        return { data: { status: "ok" } };
      },
    },
    fetchSkills: async () => {
      fetchCount += 1;
      skills.value = [];
      return true;
    },
    skills,
    isReadOnlySourceSkill: () => false,
    selectedSkillNames: { value: ["alpha", "beta"] },
    batchDeleteDialog: { value: true },
    batchSelectionEnabled: { value: true },
    showMessage: (message, color) => messages.push({ message, color }),
    tm: (key, params) => `${key}:${JSON.stringify(params)}`,
  };
  const deleteSelectedSkills = instantiateHandler(
    "deleteSelectedSkills",
    scope,
  );

  await deleteSelectedSkills();

  assert.deepEqual(calls, ["alpha", "beta"]);
  assert.equal(maxActiveRequests, 1);
  assert.equal(fetchCount, 1);
  assert.deepEqual(scope.selectedSkillNames.value, []);
  assert.deepEqual(scope.batchDeleteTargets.value, []);
  assert.equal(scope.batchDeleteDialog.value, false);
  assert.equal(scope.batchSelectionEnabled.value, false);
  assert.equal(scope.batchDeleting.value, false);
  assert.deepEqual(messages, [
    {
      message: 'skills.batchDeleteSuccess:{"count":2}',
      color: "success",
    },
  ]);
});

test("batch deletion continues after failures and retains retryable names", async () => {
  const calls = [];
  const messages = [];
  const skills = {
    value: [{ name: "alpha" }, { name: "beta" }, { name: "gamma" }],
  };

  const scope = {
    batchDeleting: { value: false },
    batchDeleteTargets: { value: ["alpha", "beta", "gamma"] },
    skillApi: {
      delete: async (name) => {
        calls.push(name);
        if (name === "beta") return { data: { status: "error" } };
        if (name === "gamma") throw new Error("network unavailable");
        return { data: { status: "ok" } };
      },
    },
    fetchSkills: async () => {
      skills.value = [{ name: "beta" }, { name: "gamma" }];
      return true;
    },
    skills,
    isReadOnlySourceSkill: () => false,
    selectedSkillNames: { value: ["alpha", "beta", "gamma"] },
    batchDeleteDialog: { value: true },
    batchSelectionEnabled: { value: true },
    showMessage: (message, color) => messages.push({ message, color }),
    tm: (key, params) => `${key}:${JSON.stringify(params)}`,
  };
  const deleteSelectedSkills = instantiateHandler(
    "deleteSelectedSkills",
    scope,
  );

  await deleteSelectedSkills();

  assert.deepEqual(calls, ["alpha", "beta", "gamma"]);
  assert.deepEqual(scope.selectedSkillNames.value, ["beta", "gamma"]);
  assert.equal(scope.batchSelectionEnabled.value, true);
  assert.equal(scope.batchDeleteDialog.value, false);
  assert.equal(scope.batchDeleting.value, false);
  assert.deepEqual(messages, [
    {
      message: 'skills.batchDeletePartial:{"succeeded":1,"failed":2}',
      color: "warning",
    },
  ]);
});

test("batch deletion preserves refresh errors and retryable targets", async () => {
  const calls = [];
  const messages = [];
  const scope = {
    batchDeleting: { value: false },
    batchDeleteTargets: { value: ["alpha", "beta"] },
    skillApi: {
      delete: async (name) => {
        calls.push(name);
        if (name === "beta") return { data: { status: "error" } };
        return { data: { status: "ok" } };
      },
    },
    fetchSkills: async () => {
      messages.push({ message: "skills.loadFailed", color: "error" });
      return false;
    },
    skills: { value: [{ name: "alpha" }, { name: "beta" }] },
    isReadOnlySourceSkill: () => false,
    selectedSkillNames: { value: ["alpha", "beta"] },
    batchDeleteDialog: { value: true },
    batchSelectionEnabled: { value: true },
    showMessage: (message, color) => messages.push({ message, color }),
    tm: (key, params) => `${key}:${JSON.stringify(params)}`,
  };
  const deleteSelectedSkills = instantiateHandler(
    "deleteSelectedSkills",
    scope,
  );

  await deleteSelectedSkills();

  assert.deepEqual(calls, ["alpha", "beta"]);
  assert.deepEqual(scope.selectedSkillNames.value, ["beta"]);
  assert.equal(scope.batchSelectionEnabled.value, true);
  assert.equal(scope.batchDeleteDialog.value, false);
  assert.deepEqual(scope.batchDeleteTargets.value, []);
  assert.equal(scope.batchDeleting.value, false);
  assert.deepEqual(messages, [
    { message: "skills.loadFailed", color: "error" },
  ]);
});

test("batch confirmation excludes names outside the deletable inventory", () => {
  const scope = {
    selectedSkillNames: {
      value: ["local", "synced-local", "plugin", "sandbox-preset"],
    },
    batchDeleteTargets: { value: [] },
    deletableSkills: {
      value: [{ name: "local" }, { name: "synced-local" }],
    },
    batchDeleteDialog: { value: false },
  };
  const confirmBatchDelete = instantiateHandler("confirmBatchDelete", scope);

  confirmBatchDelete();

  assert.deepEqual(scope.batchDeleteTargets.value, ["local", "synced-local"]);
  assert.equal(scope.batchDeleteDialog.value, true);
  assert.match(
    skillsSectionSource,
    /batchSelectionEnabled\s*&&\s*!isReadOnlySourceSkill\(skill\)/,
  );

  scope.selectedSkillNames.value = [];
  scope.batchDeleteDialog.value = false;
  confirmBatchDelete();
  assert.deepEqual(scope.batchDeleteTargets.value, []);
  assert.equal(scope.batchDeleteDialog.value, false);
});

test("existing single-skill deletion remains compatible", async () => {
  const calls = [];
  let fetchCount = 0;
  const scope = {
    skillToDelete: { value: { name: "legacy-skill" } },
    deleting: { value: false },
    skillApi: {
      delete: async (name) => {
        calls.push(name);
        return { data: { status: "ok" } };
      },
    },
    handleApiResponse: (res, _success, _failure, onSuccess) => {
      assert.equal(res.data.status, "ok");
      onSuccess();
    },
    tm: (key) => key,
    deleteDialog: { value: true },
    fetchSkills: async () => {
      fetchCount += 1;
    },
    showMessage: () => assert.fail("Unexpected single-delete failure"),
  };
  const deleteSkill = instantiateHandler("deleteSkill", scope);

  await deleteSkill();

  assert.deepEqual(calls, ["legacy-skill"]);
  assert.equal(fetchCount, 1);
  assert.equal(scope.deleteDialog.value, false);
  assert.equal(scope.deleting.value, false);
  assert.match(skillsSectionSource, /@click\.stop="confirmDelete\(skill\)"/);
});
