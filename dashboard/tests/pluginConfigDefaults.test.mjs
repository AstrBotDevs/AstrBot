import assert from "node:assert/strict";
import test from "node:test";

import {
  getPluginConfigDefaultValue,
  isPluginConfigValueModified,
} from "../src/utils/pluginConfigDefaults.mjs";

test("detects values that differ from an explicit plugin default", () => {
  const metadata = {
    type: "dict",
    default: { enabled: true, labels: ["alpha", "beta"] },
  };

  assert.equal(
    isPluginConfigValueModified(
      { labels: ["alpha", "beta"], enabled: true },
      metadata,
    ),
    false,
  );
  assert.equal(
    isPluginConfigValueModified(
      { enabled: false, labels: ["alpha", "beta"] },
      metadata,
    ),
    true,
  );
});

test("uses the same implicit defaults as the backend schema parser", () => {
  const defaults = {
    int: 0,
    float: 0,
    bool: false,
    string: "",
    text: "",
    list: [],
    file: [],
    object: {},
    template_list: [],
    dict: {},
  };

  for (const [type, value] of Object.entries(defaults)) {
    assert.equal(isPluginConfigValueModified(value, { type }), false);
  }
  assert.equal(
    isPluginConfigValueModified("changed", { type: "string" }),
    true,
  );
  assert.equal(isPluginConfigValueModified(null, { type: "unknown" }), false);
});

test("returns an independent copy of collection defaults", () => {
  const metadata = {
    type: "list",
    default: [{ name: "alpha", values: [1, 2] }],
  };

  const restored = getPluginConfigDefaultValue(metadata);
  restored[0].values.push(3);

  assert.deepEqual(metadata.default, [{ name: "alpha", values: [1, 2] }]);
});
