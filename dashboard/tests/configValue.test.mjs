import assert from "node:assert/strict";
import test from "node:test";
import {
  getConfigTemplateValue,
  normalizeConfigValue,
} from "../src/utils/configValue.mjs";

test("model presets supply defaults without replacing explicit values", () => {
  const temperature = {
    type: "float",
    default: 0.6,
    slider: { min: 0, max: 2 },
  };
  assert.equal(getConfigTemplateValue(undefined, temperature), 0.6);
  assert.equal(getConfigTemplateValue(0, temperature), 0);
  assert.equal(
    getConfigTemplateValue("xhigh", { type: "string", default: "high" }),
    "xhigh",
  );
});

test("model values use the gear editor conversions and slider bounds", () => {
  const temperature = { type: "float", slider: { min: 0, max: 2 } };
  assert.equal(normalizeConfigValue("0", temperature), 0);
  assert.equal(normalizeConfigValue("3", temperature), 2);
  assert.equal(normalizeConfigValue("-1", temperature), 0);
  assert.equal(normalizeConfigValue("8192.5", { type: "int" }), 8192);
  assert.equal(normalizeConfigValue("xhigh", { type: "string" }), "xhigh");
  assert.deepEqual(normalizeConfigValue('{"enabled":true}', { type: "json" }), {
    enabled: true,
  });
  assert.equal(normalizeConfigValue(false, { type: "bool" }), false);
  assert.throws(() => normalizeConfigValue("{", { type: "json" }), SyntaxError);
});

test("integer parameters preserve scientific notation before truncating", () => {
  for (const [value, expected] of [
    ["1e5", 100000],
    ["8.192e3", 8192],
    ["-1e3", -1000],
    [1e21, 1e21],
    ["1e-3", 0],
    ["invalid", 0],
    ["Infinity", 0],
  ]) {
    assert.equal(normalizeConfigValue(value, { type: "int" }), expected);
  }
});
