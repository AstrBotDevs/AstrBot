import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";
import { ref } from "vue";

function getFunction(source, name, fileName) {
  const ast = ts.createSourceFile(
    fileName,
    source,
    ts.ScriptTarget.Latest,
    true,
  );
  let definition;
  const visit = (node) => {
    if (
      (ts.isFunctionDeclaration(node) || ts.isMethodDeclaration(node)) &&
      node.name?.getText(ast).replaceAll(/['"]/g, "") === name
    ) {
      definition = node;
    }
    ts.forEachChild(node, visit);
  };
  visit(ast);
  assert.ok(definition, `${name} must exist in ${fileName}`);
  const parameters = definition.parameters.map((parameter) =>
    parameter.getText(ast),
  );
  return ts.transpile(
    `async function ${name}(${parameters.join(", ")}) ${definition.body.getText(
      ast,
    )}`,
    { target: ts.ScriptTarget.ES2020 },
  );
}

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function ok(data) {
  return { data: { status: "ok", data } };
}

test("persona store ignores stale folder responses and preserves current loading state", async () => {
  const source = readFileSync(
    new URL("../src/stores/personaStore.ts", import.meta.url),
    "utf8",
  );
  const requests = [];
  const context = vm.createContext({
    personaApi: {
      folders: (folderId) => {
        const request = deferred();
        requests.push({ folderId, type: "folders", ...request });
        return request.promise;
      },
      list: (folderId) => {
        const request = deferred();
        requests.push({ folderId, type: "personas", ...request });
        return request.promise;
      },
    },
  });
  vm.runInContext(
    getFunction(source, "navigateToFolder", "personaStore.ts"),
    context,
  );
  const state = {
    folderNavigationRequestId: 0,
    loading: false,
    currentFolderId: null,
    currentFolders: [],
    currentPersonas: [],
    breadcrumbPath: [],
    updateBreadcrumb(folderId) {
      this.breadcrumbPath = [folderId];
    },
  };

  const oldNavigation = context.navigateToFolder.call(state, "old");
  const currentNavigation = context.navigateToFolder.call(state, "current");
  for (const request of requests.filter(
    ({ folderId }) => folderId === "current",
  )) {
    request.resolve(
      ok(request.type === "folders" ? ["current-folder"] : ["current-persona"]),
    );
  }
  await currentNavigation;
  assert.equal(state.loading, false);

  for (const request of requests.filter(({ folderId }) => folderId === "old")) {
    request.resolve(
      ok(request.type === "folders" ? ["old-folder"] : ["old-persona"]),
    );
  }
  await oldNavigation;

  assert.equal(state.currentFolderId, "current");
  assert.deepEqual(state.currentFolders, ["current-folder"]);
  assert.deepEqual(state.currentPersonas, ["current-persona"]);
  assert.deepEqual(state.breadcrumbPath, ["current"]);
  assert.equal(state.loading, false);
});

test("persona store ignores stale request failures without clearing the active loading flag", async () => {
  const source = readFileSync(
    new URL("../src/stores/personaStore.ts", import.meta.url),
    "utf8",
  );
  const requests = [];
  const context = vm.createContext({
    personaApi: {
      folders: (folderId) => {
        const request = deferred();
        requests.push({ folderId, type: "folders", ...request });
        return request.promise;
      },
      list: (folderId) => {
        const request = deferred();
        requests.push({ folderId, type: "personas", ...request });
        return request.promise;
      },
    },
  });
  vm.runInContext(
    getFunction(source, "navigateToFolder", "personaStore.ts"),
    context,
  );
  const state = {
    folderNavigationRequestId: 0,
    loading: false,
    currentFolderId: null,
    currentFolders: [],
    currentPersonas: [],
    breadcrumbPath: [],
    updateBreadcrumb(folderId) {
      this.breadcrumbPath = [folderId];
    },
  };

  const staleNavigation = context.navigateToFolder.call(state, "old");
  const activeNavigation = context.navigateToFolder.call(state, "active");
  const staleFolders = requests.find(
    ({ folderId, type }) => folderId === "old" && type === "folders",
  );
  staleFolders.reject(new Error("stale request failed"));
  await staleNavigation;
  assert.equal(state.loading, true);

  for (const request of requests.filter(
    ({ folderId }) => folderId === "active",
  )) {
    request.resolve(ok([]));
  }
  await activeNavigation;
  assert.equal(state.loading, false);
  assert.equal(state.currentFolderId, "active");
});

test("persona selector ignores an older response and its loading cleanup", async () => {
  const source = readFileSync(
    new URL("../src/components/shared/PersonaSelector.vue", import.meta.url),
    "utf8",
  )
    .split('<script setup lang="ts">')[1]
    .split("</script>")[0];
  const requests = [];
  const context = vm.createContext({
    personaApi: {
      list: (folderId) => {
        const request = deferred();
        requests.push({ folderId, ...request });
        return request.promise;
      },
    },
    currentPersonas: ref([]),
    itemsLoading: ref(false),
    console: { error() {} },
  });
  vm.runInContext("let personaRequestId = 0;", context);
  vm.runInContext(
    getFunction(source, "loadPersonasInFolder", "PersonaSelector.ts"),
    context,
  );

  const stale = context.loadPersonasInFolder("old");
  const active = context.loadPersonasInFolder("active");
  requests[1].resolve(ok(["active-persona"]));
  await active;
  requests[0].resolve(ok(["old-persona"]));
  await stale;

  assert.deepEqual(context.currentPersonas.value, ["active-persona"]);
  assert.equal(context.itemsLoading.value, false);
});
