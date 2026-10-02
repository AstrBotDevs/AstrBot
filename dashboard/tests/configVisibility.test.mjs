import assert from "node:assert/strict";
import test from "node:test";
import { isConfigFieldVisible } from "../src/utils/configVisibility.mjs";
import { getVisibleConfigGroups } from "../src/utils/configHierarchy.mjs";

test("provider command options hide when built-in commands are disabled without clearing values", () => {
  const field = "provider_settings.reachability_check";
  const config = {
    disable_builtin_commands: true,
    provider_settings: { reachability_check: true },
  };
  const before = structuredClone(config);
  const groups = {
    model_commands: {
      tab: "commands",
      items: { [field]: { description: "Reachability" } },
    },
  };
  assert.equal(isConfigFieldVisible({}, field, config), false);
  assert.deepEqual(getVisibleConfigGroups(groups, config, "Reachability"), {});
  config.disable_builtin_commands = false;
  assert.equal(isConfigFieldVisible({}, field, config), true);
  assert.equal(
    Object.keys(getVisibleConfigGroups(groups, config, "Reachability")).length,
    1,
  );
  assert.equal(isConfigFieldVisible({}, field, {}), true);
  config.disable_builtin_commands = true;
  assert.deepEqual(config, before);
});

test("external runners expose only wired proxy and timeout settings without erasing values", () => {
  for (const runner_type of ["dify", "coze", "dashscope", "deerflow"]) {
    const config = {
      agent_runner: {
        runner_type,
        config: { proxy: "http://localhost:7890", timeout: 90 },
      },
    };
    const before = structuredClone(config);
    for (const [key, expected] of [
      ["proxy", runner_type === "deerflow"],
      ["timeout", runner_type !== "dashscope"],
    ]) {
      const field = `agent_runner.config.${key}`;
      assert.equal(isConfigFieldVisible({}, field, config), expected);
      const groups = {
        connection: {
          runner: runner_type,
          items: { [field]: { description: key } },
        },
      };
      assert.equal(
        Object.keys(getVisibleConfigGroups(groups, config, key)).length,
        expected ? 1 : 0,
      );
      assert.equal(isConfigFieldVisible({}, field, config, {}, false), true);
    }
    assert.deepEqual(config, before);
  }
});

test("image prompt requires a caption model and an enabled caption path", () => {
  const field = "provider_settings.image_caption_prompt";
  assert.equal(
    isConfigFieldVisible({}, field, {
      provider_settings: { default_image_caption_provider_id: "" },
    }),
    false,
  );
  assert.equal(
    isConfigFieldVisible({}, field, {
      provider_settings: { default_image_caption_provider_id: "caption-model" },
    }),
    true,
  );
  const config = {
    provider_ltm_settings: {
      group_icl_enable: true,
      image_caption: true,
      image_caption_provider_id: "caption-model",
    },
  };
  assert.equal(isConfigFieldVisible({}, field, config), true);
  config.provider_ltm_settings.image_caption = false;
  assert.equal(isConfigFieldVisible({}, field, config), false);
  assert.equal(
    isConfigFieldVisible({}, field, {
      provider_ltm_settings: {
        group_icl_enable: true,
        image_caption: true,
        image_caption_provider_id: "",
      },
    }),
    false,
  );
  assert.equal(
    isConfigFieldVisible({}, field, {
      provider_ltm_settings: {
        image_caption: true,
        image_caption_provider_id: "model",
        group_icl_enable: false,
        active_reply: { enable: false },
      },
    }),
    false,
  );
});

test("proactive replies alone do not activate group collection parameters or its caption prompt", () => {
  const config = {
    agent_runner: { runner_type: "dify" },
    provider_settings: {
      enable: false,
      default_image_caption_provider_id: "local-model",
    },
    provider_ltm_settings: {
      group_icl_enable: false,
      active_reply: { enable: true },
      group_message_max_cnt: 300,
      image_caption: true,
      image_caption_provider_id: "caption-model",
    },
  };
  const before = structuredClone(config);
  const condition = { "provider_ltm_settings.group_icl_enable": true };
  for (const field of [
    "provider_ltm_settings.group_message_max_cnt",
    "provider_ltm_settings.image_caption",
    "provider_ltm_settings.image_caption_provider_id",
  ]) {
    const item = {
      condition: {
        ...condition,
        ...(field.endsWith("provider_id")
          ? { "provider_ltm_settings.image_caption": true }
          : {}),
      },
    };
    assert.equal(isConfigFieldVisible(item, field, config), false);
    config.provider_ltm_settings.group_icl_enable = true;
    assert.equal(isConfigFieldVisible(item, field, config), true);
    config.provider_ltm_settings.group_icl_enable = false;
  }
  const prompt = "provider_settings.image_caption_prompt";
  assert.equal(isConfigFieldVisible({}, prompt, config), false);
  config.provider_ltm_settings.group_icl_enable = true;
  assert.equal(isConfigFieldVisible({}, prompt, config), true);
  config.provider_ltm_settings.image_caption = false;
  assert.equal(isConfigFieldVisible({}, prompt, config), false);
  config.provider_ltm_settings.image_caption = true;
  config.provider_ltm_settings.group_icl_enable = false;
  assert.deepEqual(config, before);
});

test("all required conditions must hold, including existing branch conditions", () => {
  const field = "platform_settings.segmented_reply.interval";
  const item = {
    condition: {
      "platform_settings.segmented_reply.interval_method": "random",
    },
  };
  const config = {
    platform_settings: {
      segmented_reply: {
        enable: false,
        interval_method: "random",
        interval: "1,2",
      },
    },
  };
  assert.equal(isConfigFieldVisible(item, field, config), false);
  config.platform_settings.segmented_reply.enable = true;
  assert.equal(isConfigFieldVisible(item, field, config), true);
  config.platform_settings.segmented_reply.interval_method = "log";
  assert.equal(isConfigFieldVisible(item, field, config), false);
  assert.equal(config.platform_settings.segmented_reply.interval, "1,2");
  assert.equal(isConfigFieldVisible({ invisible: true }, field, config), false);
  assert.equal(
    isConfigFieldVisible(
      {},
      "log_file_path",
      { log_file_enable: true },
      { "provider_settings.enable": true },
    ),
    false,
  );
  assert.equal(isConfigFieldVisible({}, "log_file_path", {}, {}, false), true);
});

test("search and rendered fields share visibility and hidden values survive toggling", () => {
  const groups = {
    voice: {
      items: {
        "provider_tts_settings.enable": { description: "Enable speech" },
        "provider_tts_settings.dual_output": {
          description: "Dual speech output",
        },
      },
    },
  };
  const config = {
    provider_tts_settings: { enable: false, dual_output: true },
  };
  const before = structuredClone(config);
  assert.deepEqual(getVisibleConfigGroups(groups, config, "Dual"), {});
  config.provider_tts_settings.enable = true;
  assert.equal(
    Object.keys(getVisibleConfigGroups(groups, config, "Dual")).length,
    1,
  );
  config.provider_tts_settings.enable = false;
  assert.deepEqual(config, before);
  assert.equal(Object.keys(getVisibleConfigGroups(groups, config)).length, 1);
});

test("empty allowlists and whitespace-only proxy addresses do not enable dependent fields", () => {
  for (const id_whitelist of [[], ["", "  "]]) {
    const config = {
      platform_settings: { enable_id_white_list: true, id_whitelist },
    };
    assert.equal(
      isConfigFieldVisible({}, "platform_settings.id_whitelist", config),
      true,
    );
    assert.equal(
      isConfigFieldVisible({}, "platform_settings.id_whitelist_log", config),
      false,
    );
  }
  assert.equal(
    isConfigFieldVisible({}, "no_proxy", { http_proxy: "  " }),
    false,
  );
});
