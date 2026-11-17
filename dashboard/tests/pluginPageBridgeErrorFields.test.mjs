import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(
  new URL("../src/views/PluginViewPage.vue", import.meta.url),
  "utf8",
);

const declarations = [
  "sendBridgeResponse",
  "getBridgeErrorMessage",
  "getBridgeErrorFields",
  "handleBridgeRequest",
]
  .map((name) => {
    const start = source.indexOf(`const ${name} = `);
    const end = source.indexOf("\n};", start);
    assert.ok(
      start >= 0 && end > start,
      `Missing production declaration: ${name}`,
    );
    return source.slice(start, end + 3);
  })
  .join("\n");

function loadHost(response, rejectedError) {
  const responses = [];
  const request = async () => {
    if (rejectedError) {
      throw rejectedError;
    }
    return { data: response };
  };
  const host = new Function(
    "axios",
    "buildPluginApiPath",
    "postToIframe",
    "coerceBridgeUploadFile",
    "FormData",
    `${declarations}\nreturn { handleBridgeRequest, getBridgeErrorFields };`,
  )(
    { get: request, post: request },
    (endpoint) => endpoint,
    (payload) => responses.push(payload),
    async () => "upload fixture",
    class {
      append() {}
    },
  );
  return { ...host, responses };
}

for (const action of ["api:get", "api:post", "files:upload"]) {
  test(`${action} forwards explicit structured fields`, async () => {
    const { handleBridgeRequest, responses } = loadHost({
      status: "error",
      message: "The command is invalid.",
      reason: "invalid UTF-8 life command",
      data: { code: "life_command_invalid", confirmed: false },
    });
    await handleBridgeRequest({
      requestId: "request-1",
      action,
      endpoint: "fixture",
    });
    assert.deepEqual(responses, [
      {
        kind: "response",
        requestId: "request-1",
        ok: false,
        error: "The command is invalid.",
        errorCode: "life_command_invalid",
        errorReason: "invalid UTF-8 life command",
        errorConfirmed: false,
      },
    ]);
  });

  test(`${action} does not turn a human-readable message into an error code`, async () => {
    const { handleBridgeRequest, responses } = loadHost({
      status: "error",
      message: "Please select a provider before continuing.",
    });
    await handleBridgeRequest({
      requestId: "request-2",
      action,
      endpoint: "fixture",
    });
    assert.equal(
      responses[0].error,
      "Please select a provider before continuing.",
    );
    assert.equal(Object.hasOwn(responses[0], "errorCode"), false);
  });

  test(`${action} prefers the rejected response's business code over the transport code`, async () => {
    const error = Object.assign(
      new Error("Request failed with status code 400"),
      {
        code: "ERR_BAD_REQUEST",
        response: {
          data: {
            status: "error",
            message: "The command is invalid.",
            reason: "invalid UTF-8 life command",
            data: { code: "life_command_invalid", confirmed: false },
          },
        },
      },
    );
    const { handleBridgeRequest, responses } = loadHost(undefined, error);
    await handleBridgeRequest({
      requestId: "request-3",
      action,
      endpoint: "fixture",
    });
    assert.equal(responses[0].error, "The command is invalid.");
    assert.equal(responses[0].errorCode, "life_command_invalid");
    assert.equal(responses[0].errorReason, "invalid UTF-8 life command");
    assert.equal(responses[0].errorConfirmed, false);
  });
}

test("error without structured fields stays backward compatible", () => {
  const { getBridgeErrorFields } = loadHost();
  assert.equal(getBridgeErrorFields(new Error("plain failure")), undefined);
});

test("partial top-level fields remain available without a response envelope", () => {
  const { getBridgeErrorFields } = loadHost();
  assert.deepEqual(
    getBridgeErrorFields(
      Object.assign(new Error("partial"), { code: "some_code" }),
    ),
    { errorCode: "some_code" },
  );
});

test("confirmed=false is preserved without a response envelope", () => {
  const { getBridgeErrorFields } = loadHost();
  assert.deepEqual(
    getBridgeErrorFields(
      Object.assign(new Error("partial"), { confirmed: false }),
    ),
    { errorConfirmed: false },
  );
});
