import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { getConfigEffectNotices } from "../src/utils/configEffects.mjs";
import { isConfigFieldVisible } from "../src/utils/configVisibility.mjs";

test("streaming keeps the saved intermediate-message merge control editable in core only", () => {
  const item = {
    condition: {
      "provider_settings.streaming_response": false,
      "agent_runner.runner_type": "local",
    },
  };
  const config = {
    provider_settings: {
      streaming_response: true,
      buffer_intermediate_messages: true,
    },
    agent_runner: { runner_type: "local" },
  };
  const before = structuredClone({ item, config });
  const field = "provider_settings.buffer_intermediate_messages";
  assert.equal(isConfigFieldVisible(item, field, config), true);
  assert.equal(isConfigFieldVisible(item, field, config, {}, false), false);
  config.agent_runner.runner_type = "dify";
  assert.equal(isConfigFieldVisible(item, field, config), false);
  config.agent_runner.runner_type = "local";
  assert.deepEqual({ item, config }, before);
});

test("streaming notices preserve ordinary and fallback settings and update on toggles", () => {
  const config = {
    provider_settings: {
      enable: true,
      streaming_response: true,
      buffer_intermediate_messages: true,
    },
    platform_settings: {
      reply_prefix: "Bot: ",
      segmented_reply: { enable: true },
    },
    provider_tts_settings: { enable: true },
    t2i: true,
    content_safety: { also_use_in_response: true },
  };
  const before = structuredClone(config);
  for (const [field, notice] of [
    ["platform_settings.reply_prefix", "streamingDecoration"],
    ["platform_settings.segmented_reply.enable", "streamingDecoration"],
    ["provider_tts_settings.enable", "streamingDecoration"],
    ["t2i", "streamingDecoration"],
    ["content_safety.also_use_in_response", "streamingSafety"],
    ["provider_settings.buffer_intermediate_messages", "streamingBuffer"],
  ])
    assert.ok(getConfigEffectNotices(field, config).includes(notice), field);
  assert.deepEqual(config, before);
  config.provider_settings.streaming_response = false;
  assert.deepEqual(
    getConfigEffectNotices("content_safety.also_use_in_response", config),
    [],
  );
  config.provider_settings.streaming_response = true;
  config.provider_settings.enable = false;
  assert.deepEqual(
    getConfigEffectNotices("platform_settings.reply_prefix", config),
    [],
  );
});

test("voice priority notices remain conditional with dual output and disappear at zero probability", () => {
  const config = {
    t2i: true,
    provider_settings: { display_reasoning_text: true },
    provider_tts_settings: {
      enable: true,
      dual_output: true,
      trigger_probability: 0.5,
    },
    platform_settings: { reply_with_quote: true },
  };
  assert.deepEqual(getConfigEffectNotices("t2i", config), ["voiceBeforeImage"]);
  assert.deepEqual(
    getConfigEffectNotices("provider_settings.display_reasoning_text", config),
    ["voiceReasoning"],
  );
  assert.ok(
    getConfigEffectNotices(
      "platform_settings.reply_with_quote",
      config,
    ).includes("voiceDecoration"),
  );
  config.provider_tts_settings.trigger_probability = 0;
  assert.deepEqual(getConfigEffectNotices("t2i", config), []);
  assert.deepEqual(
    getConfigEffectNotices("provider_settings.display_reasoning_text", config),
    [],
  );
});

test("image and forwarding notices explain segment packaging without marking voice segmentation incompatible", () => {
  const config = {
    t2i: true,
    platform_settings: {
      segmented_reply: { enable: true },
      forward_threshold: 1000,
    },
    provider_tts_settings: { enable: true },
  };
  assert.deepEqual(
    getConfigEffectNotices("platform_settings.segmented_reply.enable", config),
    ["imageBeforeSegments"],
  );
  assert.deepEqual(
    getConfigEffectNotices("platform_settings.forward_threshold", config),
    ["forwardBeforeSegments"],
  );
  config.t2i = false;
  assert.deepEqual(
    getConfigEffectNotices("platform_settings.segmented_reply.enable", config),
    [],
  );
  assert.deepEqual(
    getConfigEffectNotices("provider_tts_settings.enable", config),
    [],
  );
});

test("disabled and unrelated fields do not acquire notices", () => {
  const config = {
    provider_settings: { streaming_response: true },
    provider_tts_settings: { enable: true },
  };
  for (const field of [
    "t2i",
    "platform_settings.segmented_reply.enable",
    "content_safety.also_use_in_response",
    "provider_stt_settings.enable",
    "agent_runner.runner_type",
  ])
    assert.deepEqual(getConfigEffectNotices(field, config), []);
});

test("every effect has translations in all supported locales", () => {
  const keys = [
    "conditional",
    "streamingDecoration",
    "streamingSafety",
    "streamingBuffer",
    "streamingPlatform",
    "voiceBeforeImage",
    "voiceReasoning",
    "voiceDecoration",
    "imageBeforeSegments",
    "forwardBeforeSegments",
    "forwardDecoration",
  ];
  for (const locale of ["zh-CN", "en-US", "ja-JP", "ru-RU"]) {
    const messages = JSON.parse(
      readFileSync(
        new URL(
          `../src/i18n/locales/${locale}/features/config.json`,
          import.meta.url,
        ),
        "utf8",
      ),
    ).effects;
    for (const key of keys)
      assert.equal(typeof messages[key], "string", `${locale}: ${key}`);
  }
});
