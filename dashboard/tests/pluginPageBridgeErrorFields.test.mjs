import assert from "node:assert/strict";
import test from "node:test";

const makeError = (data) => {
  const err = new Error(data.message || "request failed");
  err.code = data.data?.code ?? data.message;
  err.reason = data.reason;
  err.confirmed = data.data?.confirmed ?? data.confirmed;
  return err;
};

const extractErrorFields = (error) => {
  const fields = {};
  if (typeof error?.code === "string" && error.code) {
    fields.errorCode = error.code;
  }
  if (typeof error?.reason === "string" && error.reason) {
    fields.errorReason = error.reason;
  }
  if (typeof error?.confirmed === "boolean") {
    fields.errorConfirmed = error.confirmed;
  }
  return Object.keys(fields).length > 0 ? fields : undefined;
};

test("structured error fields survive the host-to-bridge round trip", () => {
  const serverResponse = {
    status: "error",
    message: "life_command_invalid",
    reason: "invalid UTF-8 life command",
    data: { code: "life_command_invalid", confirmed: false },
  };

  const err = makeError(serverResponse);
  assert.equal(err.message, "life_command_invalid");
  assert.equal(err.code, "life_command_invalid");
  assert.equal(err.reason, "invalid UTF-8 life command");
  assert.equal(err.confirmed, false);

  const fields = extractErrorFields(err);
  assert.deepEqual(fields, {
    errorCode: "life_command_invalid",
    errorReason: "invalid UTF-8 life command",
    errorConfirmed: false,
  });
});

test("error without structured fields yields undefined so the bridge stays backward compatible", () => {
  const err = new Error("plain failure");
  const fields = extractErrorFields(err);
  assert.equal(fields, undefined);
});

test("partial structured fields are forwarded individually", () => {
  const err = new Error("partial");
  err.code = "some_code";
  const fields = extractErrorFields(err);
  assert.deepEqual(fields, { errorCode: "some_code" });
});

test("confirmed=false is forwarded because the type check is boolean not truthy", () => {
  const err = new Error("x");
  err.confirmed = false;
  const fields = extractErrorFields(err);
  assert.deepEqual(fields, { errorConfirmed: false });
});
