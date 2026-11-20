import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { compileFunction, createContext } from "node:vm";
import ts from "typescript";
import * as vue from "vue";
import { compileScript, parse } from "vue/compiler-sfc";

const documentsFile = "components/DocumentsTab.vue";
const detailFile = "KBDetail.vue";
const ok = (data) => ({ data: { status: "ok", data } });
const completed = () =>
  ok({ status: "completed", result: { success_count: 1 } });
const deferred = () => Promise.withResolvers();

function clock() {
  const jobs = new Map();
  let sequence = 0;
  const add = (fn, repeat) => {
    jobs.set(++sequence, { fn, repeat });
    return sequence;
  };
  return {
    setTimeout: (fn) => add(fn, false),
    setInterval: (fn) => add(fn, true),
    clearTimeout: (id) => jobs.delete(id),
    clearInterval: (id) => jobs.delete(id),
    get pending() {
      return jobs.size;
    },
    fire() {
      return Array.from(jobs).flatMap(([id, { fn, repeat }]) => {
        if (!jobs.has(id)) return [];
        if (!repeat) jobs.delete(id);
        return [fn()];
      });
    },
    async tick() {
      await Promise.all(this.fire());
    },
  };
}

function setup(file, knowledgeApi, timers = clock()) {
  const source = new URL(
    `../src/views/knowledge-base/${file}`,
    import.meta.url,
  );
  const { descriptor, errors } = parse(readFileSync(source, "utf8"), {
    filename: file,
  });
  assert.deepEqual(errors, []);
  const script = compileScript(descriptor, { id: file });
  const compiled = ts.transpileModule(script.content, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
    },
  }).outputText;
  const unmount = [];
  const events = [];
  const imports = {
    vue: { ...vue, onMounted() {}, onUnmounted: (fn) => unmount.push(fn) },
    "vue-router": {
      useRouter: () => ({}),
      useRoute: () => ({ params: { kbId: "docs" } }),
    },
    "@/api/v1": { knowledgeApi, configProfileApi: {}, providerApi: {} },
    "@/i18n/composables": {
      useI18n: () => ({ locale: vue.ref("en-US") }),
      useModuleI18n: () => ({ tm: (key) => key }),
    },
  };
  const module = { exports: {} };
  const context = createContext(
    {
      window: timers,
      clearInterval: timers.clearInterval,
      clearTimeout: timers.clearTimeout,
      FormData: class {
        append() {}
      },
      console: { error() {} },
    },
    { codeGeneration: { strings: false, wasm: false } },
  );
  compileFunction(compiled, ["require", "module", "exports"], {
    parsingContext: context,
  })(
    (name) => {
      if (Object.hasOwn(imports, name)) return imports[name];
      if (name.startsWith("./") && name.endsWith(".vue"))
        return { default: {} };
      throw new Error(`Unexpected component dependency: ${name}`);
    },
    module,
    module.exports,
  );
  const scope = vue.effectScope();
  const state = scope.run(() =>
    module.exports.default.setup(
      { kbId: "docs", kb: {} },
      {
        expose() {},
        emit: (...args) => events.push(args),
      },
    ),
  );
  return {
    state,
    events,
    timers,
    rows: () => (state.displayDocuments ?? state.documents).value,
    refresh(component, event) {
      const handler = descriptor.template.content.match(
        new RegExp(
          `<${component}\\s[^>]*@${event}="([A-Za-z_$][\\w$]*)(?:\\(\\))?"`,
        ),
      )?.[1];
      assert.ok(handler, `expected the ${event} handler on ${component}`);
      return state[handler]();
    },
    dispose() {
      scope.stop();
      for (const fn of unmount.splice(0)) fn();
    },
  };
}

async function uploadFiles(view, ...names) {
  view.state.selectedFiles.value = names.map((name) => ({ name, size: 6 }));
  await view.state.startUpload();
}

async function importUrl(view) {
  view.state.uploadMode.value = "url";
  view.state.uploadUrl.value = "https://example.invalid/notes";
  await view.state.startUpload();
}

test("a URL import can finish while a file batch keeps its own progress and polling", async () => {
  const status = {
    A: ok({
      status: "processing",
      progress: { file_index: 1, stage: "chunking", current: 37, total: 100 },
    }),
    B: completed(),
  };
  const polls = [];
  const items = [{ doc_id: "stored-b" }];
  const pages = [];
  const view = setup(documentsFile, {
    uploadDocument: async () => ok({ task_id: "A", file_count: 2 }),
    importDocumentFromUrl: async () =>
      ok({ task_id: "B", url: "https://example.invalid/notes" }),
    task: async (id) => {
      polls.push(id);
      return status[id];
    },
    documents: async (_id, params) => {
      pages.push(params.page);
      return ok({ items: [...items], total: 24 });
    },
  });
  try {
    await uploadFiles(view, "a.txt", "a2.txt");
    await view.timers.tick();
    await importUrl(view);
    view.state.page.value = 2;
    await view.state.loadDocuments();
    await view.timers.tick();
    const pending = Array.from(view.rows()).filter((row) => row.taskId === "A");
    assert.deepEqual(polls, ["A", "A", "B"]);
    assert.deepEqual(
      pending.map((row) => row.uploadProgress.current),
      [0, 37],
    );
    assert.deepEqual(
      Array.from(view.rows(), (row) => row.doc_id),
      ["uploading_A_0", "uploading_A_1", "stored-b"],
    );
    assert.equal(view.state.total.value, 24);
    assert.deepEqual(pages, [2, 2]);
    status.A = completed();
    items.push({ doc_id: "stored-a" });
    await view.timers.tick();
    await view.timers.tick();
    assert.deepEqual(polls, ["A", "A", "B", "A"]);
    assert.deepEqual(
      Array.from(view.rows(), (row) => row.doc_id),
      ["stored-b", "stored-a"],
    );
    assert.deepEqual(view.events, [["refresh"], ["refresh"]]);
  } finally {
    view.dispose();
  }
});

test("a slow task never has overlapping polls and cannot finish the view after unmount", async () => {
  const pending = deferred();
  const polls = [];
  let refreshes = 0;
  const view = setup(documentsFile, {
    uploadDocument: async () => ok({ task_id: "A", file_count: 1 }),
    task: (id) => {
      polls.push(id);
      return pending.promise;
    },
    documents: async () => {
      refreshes++;
      return ok({ items: [], total: 0 });
    },
  });
  await uploadFiles(view, "a.txt");
  const inFlight = [
    ...view.timers.fire(),
    ...view.timers.fire(),
    ...view.timers.fire(),
  ];
  try {
    assert.deepEqual(polls, ["A"]);
  } finally {
    view.dispose();
    pending.resolve(completed());
    await Promise.all(inFlight);
  }
  await view.timers.tick();
  assert.equal(view.timers.pending, 0);
  assert.equal(refreshes, 0);
  assert.deepEqual(view.events, []);
});

test("an upload accepted after unmount does not start a polling timer", async () => {
  const pending = deferred();
  const view = setup(documentsFile, { uploadDocument: () => pending.promise });
  const submit = uploadFiles(view, "a.txt");
  view.dispose();
  pending.resolve(ok({ task_id: "A", file_count: 1 }));
  await submit;
  assert.equal(view.timers.pending, 0);
  assert.equal(view.rows().length, 0);
});

test("a late list response cannot finish an upload in an unmounted view", async () => {
  const page = deferred();
  const requested = deferred();
  const view = setup(documentsFile, {
    uploadDocument: async () => ok({ task_id: "A", file_count: 1 }),
    task: async () => completed(),
    documents: () => {
      requested.resolve();
      return page.promise;
    },
  });
  await uploadFiles(view, "a.txt");
  const completion = view.timers.tick();
  await requested.promise;
  view.dispose();
  page.resolve(ok({ items: [{ doc_id: "stored-a" }], total: 1 }));
  await completion;
  assert.deepEqual(view.events, []);
  assert.equal(view.rows().length, 0);
  assert.equal(view.timers.pending, 0);
});

test("temporary poll errors retry and a missing task only clears its own rows", async () => {
  let attempts = 0;
  const view = setup(documentsFile, {
    uploadDocument: async () => ok({ task_id: "A", file_count: 1 }),
    importDocumentFromUrl: async () =>
      ok({ task_id: "B", url: "https://example.invalid/notes" }),
    task: async (id) => {
      if (id === "B")
        return { data: { status: "error", message: "task not found" } };
      if (++attempts === 1) throw new Error("temporary connection failure");
      return ok({ status: "processing", progress: { current: 21 } });
    },
  });
  try {
    await uploadFiles(view, "a.txt");
    await importUrl(view);
    await view.timers.tick();
    assert.equal(view.timers.pending, 1);
    await view.timers.tick();
    assert.deepEqual(
      Array.from(view.rows(), (row) => row.taskId),
      ["A"],
    );
    assert.equal(view.rows()[0].uploadProgress.current, 21);
    assert.equal(attempts, 2);
    assert.deepEqual(view.events, []);
  } finally {
    view.dispose();
  }
});

test("document and settings refreshes leave loaded detail visible and ignore stale responses", async () => {
  const older = deferred();
  const newer = deferred();
  const failure = deferred();
  const responses = [
    Promise.resolve(ok({ kb_name: "Notes", doc_count: 0 })),
    older.promise,
    newer.promise,
    failure.promise,
  ];
  const view = setup(detailFile, { get: () => responses.shift() });
  try {
    await view.state.loadKB();
    const oldRefresh = view.refresh("DocumentsTab", "refresh");
    const newRefresh = view.refresh("SettingsTab", "updated");
    const loadingDuringRefresh = view.state.loading.value;
    newer.resolve(ok({ kb_name: "Notes", doc_count: 2 }));
    await newRefresh;
    older.resolve(ok({ kb_name: "Old", doc_count: 1 }));
    await oldRefresh;
    const failedRefresh = view.refresh("DocumentsTab", "refresh");
    failure.resolve({
      data: { status: "error", message: "metadata unavailable" },
    });
    await failedRefresh;
    assert.deepEqual(
      {
        loadingDuringRefresh,
        loadError: view.state.loadError.value,
        documents: view.state.kb.value.doc_count,
        title: view.state.kb.value.kb_name,
      },
      {
        loadingDuringRefresh: false,
        loadError: false,
        documents: 2,
        title: "Notes",
      },
    );
    assert.equal(view.state.snackbar.value.text, "metadata unavailable");
  } finally {
    view.dispose();
  }
});

test("an initial detail error can still be retried", async () => {
  const responses = [
    { data: { status: "error" } },
    ok({ kb_name: "Notes", doc_count: 1 }),
  ];
  const view = setup(detailFile, { get: async () => responses.shift() });
  try {
    await view.state.loadKB();
    assert.equal(view.state.loadError.value, true);
    await view.state.loadKB();
    assert.equal(view.state.loadError.value, false);
    assert.equal(view.state.kb.value.doc_count, 1);
  } finally {
    view.dispose();
  }
});
