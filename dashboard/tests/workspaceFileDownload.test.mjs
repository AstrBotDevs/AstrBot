import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";
import { effectScope, nextTick, reactive, ref, watch } from "vue";

for (const action of ["close", "refresh", "switch session", "late failure"]) {
  test(`pending workspace download survives ${action} without changing newer UI state`, async (t) => {
    const source = readFileSync(
      new URL(
        "../src/components/chat/WorkspaceFilesPanel.vue",
        import.meta.url,
      ),
      "utf8",
    )
      .split('<script setup lang="ts">')[1]
      .split("</script>")[0];
    const ast = ts.createSourceFile(
      "panel.ts",
      source,
      ts.ScriptTarget.Latest,
      true,
    );
    const names = new Set([
      "close",
      "resetPanel",
      "clearPreview",
      "refreshTree",
      "downloadSelectedFile",
    ]);
    const handlers = ast.statements.filter(
      (node) => ts.isFunctionDeclaration(node) && names.has(node.name?.text),
    );
    const watcher = ast.statements.find(
      (node) =>
        ts.isExpressionStatement(node) &&
        node.getText(ast).startsWith("watch(") &&
        node.getText(ast).includes("props.modelValue"),
    );
    assert.equal(handlers.length, names.size);
    assert.ok(watcher);

    const props = reactive({
      modelValue: true,
      projectId: "project",
      sessionId: "session-a",
      workspaceType: "session",
    });
    const requests = [];
    const saved = [];
    const blobs = new Map();
    const context = vm.createContext({
      props,
      watch,
      emit: (_event, open) => {
        props.modelValue = open;
      },
      loadDirectory: async () => {},
      tm: (key) => key,
      chatApi: {
        downloadProjectWorkspaceFile: (...args) =>
          new Promise((resolve, reject) => {
            requests.push({ args, resolve, reject });
          }),
      },
      URL: {
        createObjectURL: (blob) => {
          const url = `blob:${blobs.size}`;
          blobs.set(url, blob);
          return url;
        },
        revokeObjectURL: (url) => blobs.delete(url),
      },
      document: {
        createElement: () => ({
          click() {
            saved.push({ name: this.download, data: blobs.get(this.href) });
          },
          remove() {},
        }),
        body: { appendChild() {} },
      },
      setTimeout: (callback) => callback(),
    });
    for (const [name, value] of Object.entries({
      treeGeneration: 0,
      fileGeneration: 0,
      rootEntries: [],
      rootLoading: false,
      fileDownloading: false,
      treeError: "",
      filterQuery: "",
      previewDialog: false,
      selectedFilePath: "",
      fileContent: "",
      fileError: "",
      fileLoading: false,
    }))
      context[name] = ref(value);

    const scope = effectScope();
    t.after(() => scope.stop());
    scope.run(() =>
      vm.runInContext(
        ts.transpile(
          [...handlers, watcher].map((node) => node.getText(ast)).join("\n"),
          { target: ts.ScriptTarget.ES2022 },
        ),
        context,
      ),
    );
    await nextTick();
    context.selectedFilePath.value = "reports/original.zip";
    const first = context.downloadSelectedFile();
    assert.deepEqual(requests[0].args, [
      "project",
      "reports/original.zip",
      "session-a",
    ]);

    if (action === "refresh") await context.refreshTree();
    else if (action === "switch session") props.sessionId = "session-b";
    else context.close();
    await nextTick();
    let second;
    if (action !== "close") {
      props.modelValue = true;
      await nextTick();
      context.selectedFilePath.value = "new.zip";
      second = context.downloadSelectedFile();
      assert.equal(requests.length, 2);
      assert.equal(context.fileDownloading.value, true);
    }

    if (action === "late failure")
      requests[0].reject(new Error("Network error"));
    else requests[0].resolve({ data: "original bytes" });
    await first;
    assert.deepEqual(
      saved,
      action === "late failure"
        ? []
        : [{ name: "original.zip", data: "original bytes" }],
    );
    assert.equal(
      context.fileError.value,
      "",
      "old errors must not appear in the new panel",
    );
    assert.equal(
      context.fileDownloading.value,
      action !== "close",
      "old completion must not clear the new download indicator",
    );

    if (action === "close") {
      assert.equal(
        props.modelValue,
        false,
        "the first download finishes while closed",
      );
      props.modelValue = true;
      await nextTick();
      context.selectedFilePath.value = "new.zip";
      second = context.downloadSelectedFile();
    }
    requests[1].resolve({ data: "new bytes" });
    await second;
    assert.deepEqual(saved.at(-1), { name: "new.zip", data: "new bytes" });
    assert.equal(context.fileDownloading.value, false);
    assert.equal(blobs.size, 0, "download object URLs must be released");
  });
}
