import { beforeEach, describe, expect, it, vi } from "vitest";
import { ref } from "vue";
import { providerApi as api } from "../src/api/v1.ts";
import { useProviderModelConfigDialog } from "../src/composables/useProviderModelConfigDialog";
import { mountComposable } from "./helpers/mountComposable.mjs";

beforeEach(() => {
  vi.spyOn(api, "createInSource");
  vi.spyOn(api, "update");
});

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}

function setup() {
  const selectedProviderSource = ref({ id: "source-A" });
  const loadConfig = vi.fn(async () => {});
  const showMessage = vi.fn();
  const app = mountComposable(() =>
    useProviderModelConfigDialog({
      selectedProviderSource,
      configSchema: ref({}),
      buildModelProviderConfig: (model) => ({ id: "new-A", model, custom_extra_body: { temperature: 1 } }),
      modelAlreadyConfigured: () => false,
      loadConfig,
      showMessage,
      tm: (key, params) => (params ? `${key}:${JSON.stringify(params)}` : key),
    }),
  );
  return { dialog: app.result, selectedProviderSource, loadConfig, showMessage, unmount: app.unmount };
}

const provider = (id) => ({
  id,
  model: `model-${id}`,
  provider_source_id: `source-${id}`,
  custom_extra_body: { temperature: 1 },
});
const success = () => ({ data: { status: "ok" } });

describe("provider save ownership", () => {
  it("snapshots A and preserves a newer B dialog/loading state when A finishes", async () => {
    const a = deferred();
    const b = deferred();
    api.update.mockImplementation((id) => (id === "A" ? a.promise : b.promise));
    const { dialog, selectedProviderSource, loadConfig, showMessage } = setup();
    dialog.openProviderEdit(provider("A"));
    const savingA = dialog.saveEditedProvider();
    dialog.providerEditData.value.custom_extra_body.temperature = 9;
    expect(api.update.mock.calls[0][1].custom_extra_body.temperature).toBe(1);

    selectedProviderSource.value = { id: "source-B" };
    dialog.openProviderEdit(provider("B"));
    const savingB = dialog.saveEditedProvider();
    expect(dialog.savingProviders.value).toEqual(["A", "B"]);
    a.resolve(success());
    await savingA;
    expect(dialog.providerEditData.value.id).toBe("B");
    expect(dialog.showProviderEditDialog.value).toBe(true);
    expect(dialog.savingProviders.value).toEqual(["B"]);
    expect(showMessage).not.toHaveBeenCalled();
    expect(loadConfig).not.toHaveBeenCalled();

    b.resolve(success());
    await savingB;
    expect(dialog.savingProviders.value).toEqual([]);
    expect(dialog.showProviderEditDialog.value).toBe(false);
    expect(showMessage).toHaveBeenCalledTimes(1);
    expect(loadConfig).toHaveBeenCalledTimes(1);
  });

  it("ignores an old rejection after reopening the same provider", async () => {
    const pending = deferred();
    api.update.mockReturnValue(pending.promise);
    const { dialog, loadConfig, showMessage } = setup();
    dialog.openProviderEdit(provider("A"));
    const saving = dialog.saveEditedProvider();
    dialog.showProviderEditDialog.value = false;
    dialog.openProviderEdit({ ...provider("A"), model: "new-editor-model" });
    pending.reject(new Error("old request failed"));
    await saving;
    expect(dialog.providerEditData.value.model).toBe("new-editor-model");
    expect(dialog.showProviderEditDialog.value).toBe(true);
    expect(dialog.savingProviders.value).toEqual([]);
    expect(showMessage).not.toHaveBeenCalled();
    expect(loadConfig).not.toHaveBeenCalled();
  });

  it("captures creation source/payload and ignores a later source selection", async () => {
    const pending = deferred();
    api.createInSource.mockReturnValue(pending.promise);
    const { dialog, selectedProviderSource, loadConfig, showMessage } = setup();
    dialog.openModelAddDialog("initial-model");
    const saving = dialog.saveEditedProvider();
    dialog.providerEditData.value.model = "unsaved-model";
    selectedProviderSource.value = { id: "source-B" };
    expect(api.createInSource.mock.calls[0][0]).toBe("source-A");
    expect(api.createInSource.mock.calls[0][1].model).toBe("initial-model");
    pending.resolve(success());
    await saving;
    expect(dialog.providerEditData.value.model).toBe("unsaved-model");
    expect(dialog.showProviderEditDialog.value).toBe(true);
    expect(dialog.savingProviders.value).toEqual([]);
    expect(showMessage).not.toHaveBeenCalled();
    expect(loadConfig).not.toHaveBeenCalled();
  });

  it("cleans pending state without UI work after scope disposal", async () => {
    const pending = deferred();
    api.update.mockReturnValue(pending.promise);
    const { dialog, unmount, loadConfig, showMessage } = setup();
    dialog.openProviderEdit(provider("A"));
    const saving = dialog.saveEditedProvider();
    unmount();
    pending.resolve(success());
    await saving;
    expect(dialog.savingProviders.value).toEqual([]);
    expect(showMessage).not.toHaveBeenCalled();
    expect(loadConfig).not.toHaveBeenCalled();
  });
});
