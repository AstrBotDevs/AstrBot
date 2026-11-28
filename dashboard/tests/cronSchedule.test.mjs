import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";

function setup() {
  const source = readFileSync(
    new URL("../src/views/CronJobPage.vue", import.meta.url), "utf8",
  ).split('<script setup lang="ts">')[1].split("</script>")[0];
  const ast = ts.createSourceFile("cron.ts", source, ts.ScriptTarget.Latest, true);
  const names = new Set([
    "buildPayload", "buildCronExpression", "readScheduleFromJob",
    "validateScheduleFields", "scheduleProductLabel", "parseTimeParts",
    "padTimePart", "isCronTime",
  ]);
  const definitions = ast.statements.filter(
    (node) => ts.isFunctionDeclaration(node) && names.has(node.name.text),
  );
  assert.equal(definitions.length, names.size);
  const warnings = [];
  const context = vm.createContext({
    newJob: { value: {
      schedule_mode: "interval", interval_value: 40, interval_unit: "minutes",
      name: "Reminder", note: "Reminder note", cron_expression: "",
      run_at: "2030-01-01T09:00:00Z", timezone: "UTC", session: "session", enabled: true,
      daily_time: "09:00", weekly_time: "09:00", weekly_day: 1,
      monthly_time: "09:00", monthly_day: 15,
    } },
    tm: (key, params) => ({ key, ...params }),
    toast: (message) => warnings.push(message),
    formatTime: (value) => value,
    toIsoDatetime: (value) => value,
  });
  vm.runInContext(ts.transpileModule(
    definitions.map((node) => node.getText(ast)).join("\n"),
    { compilerOptions: { target: ts.ScriptTarget.ES2022 } },
  ).outputText, context);
  return { context, form: context.newJob.value, warnings };
}

for (const [value, unit, seconds] of [
  [40, "minutes", 2400], [60, "minutes", 3600], [24, "hours", 86400],
  [48, "hours", 172800], [31, "days", 2678400], [40, "days", 3456000],
]) {
  test(`${value} ${unit} round-trips as a fixed interval without clipping`, () => {
    const { context, form } = setup();
    Object.assign(form, { interval_value: value, interval_unit: unit });
    assert.equal(context.validateScheduleFields(), true);
    const payload = context.buildPayload();
    assert.equal(payload.interval_seconds, seconds);
    assert.equal(payload.cron_expression, "");
    assert.equal(payload.run_once, false);
    assert.equal(payload.run_at, "");
    Object.assign(form, context.readScheduleFromJob(payload));
    assert.equal(form.schedule_mode, "interval");
    assert.equal(context.buildPayload().interval_seconds, seconds);
    assert.match(context.scheduleProductLabel(payload).key, /^card.every/);
  });
}

for (const expression of ["*/40 * * * *", "*/59 * * * *", "0 */23 * * *", "0 0 */31 * *"]) {
  test(`legacy ${expression} remains a custom Cron schedule when edited`, () => {
    const { context, form } = setup();
    const job = { cron_expression: expression, interval_seconds: null, run_once: false };
    Object.assign(form, context.readScheduleFromJob(job));
    assert.equal(form.schedule_mode, "cron");
    assert.equal(context.scheduleProductLabel(job).key, "card.customCron");
    assert.equal(context.buildPayload().cron_expression, expression);
    assert.equal(context.buildPayload().interval_seconds, null);
  });
}

test("switching away from intervals explicitly clears the backend interval", () => {
  const { context, form } = setup();
  for (const [mode, expression] of [
    ["daily", "0 9 * * *"], ["weekly", "0 9 * * 1"], ["monthly", "0 9 15 * *"],
  ]) {
    form.schedule_mode = mode;
    assert.equal(context.validateScheduleFields(), true);
    assert.equal(context.buildPayload().interval_seconds, null);
    assert.equal(context.buildPayload().cron_expression, expression);
    assert.equal(context.readScheduleFromJob({ cron_expression: expression }).schedule_mode, mode);
  }
  form.schedule_mode = "once";
  assert.equal(context.buildPayload().interval_seconds, null);
  assert.equal(context.buildPayload().run_once, true);
  assert.equal(context.buildPayload().run_at, form.run_at);
});

test("invalid intervals fail validation instead of being coerced or clamped", () => {
  const { context, form, warnings } = setup();
  for (const value of [0, -1, 1.5, NaN, Infinity, 2 ** 31, Number.MAX_SAFE_INTEGER]) {
    form.interval_value = value;
    assert.equal(context.validateScheduleFields(), false);
  }
  form.interval_value = 1;
  form.interval_unit = "invalid";
  assert.equal(context.validateScheduleFields(), false);
  assert.equal(warnings.length, 8);
});
