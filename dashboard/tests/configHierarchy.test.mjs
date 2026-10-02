import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import {
  buildConfigHierarchy,
  CONFIG_GROUPS,
  CONFIG_SECTIONS,
  getVisibleConfigGroups,
} from "../src/utils/configHierarchy.mjs";

test("capabilities prioritize tool execution and computer use while context remains separate", () => {
  const fields = [
    "agent_runner.config.misc.max_steps",
    "agent_runner.config.misc.tool_call_timeout",
    "agent_runner.config.misc.tool_schema_mode",
    "provider_settings.show_tool_use_status",
    "provider_settings.show_tool_call_result",
    "provider_settings.buffer_intermediate_messages",
  ];
  const metadata = {
    ai_group: {
      metadata: Object.fromEntries([
        [
          "others",
          {
            items: Object.fromEntries(
              [
                ...fields,
                "agent_runner.config.misc.sanitize_context_by_modalities",
              ].map((field) => [field, { type: "string" }]),
            ),
          },
        ],
        ...[
          "agent_computer_use",
          "knowledgebase",
          "websearch",
          "proactive_capability",
          "truncate_and_compress",
        ].map((key) => [key, { items: { [key]: { type: "bool" } } }]),
      ]),
    },
  };
  const before = structuredClone(metadata);
  const groups = buildConfigHierarchy(metadata).ai_group.metadata;
  assert.deepEqual(
    Object.keys(groups).filter((key) => groups[key].tab === "capabilities"),
    [
      "tool_execution",
      "agent_computer_use",
      "knowledgebase",
      "websearch",
      "proactive_capability",
    ],
  );
  assert.deepEqual(Object.keys(groups.tool_execution.items), fields);
  assert.deepEqual(
    Object.keys(groups).filter((key) => groups[key].tab === "context"),
    ["truncate_and_compress", "context_modalities"],
  );
  assert.equal(groups.tool_execution.runner, "local");
  assert.deepEqual(metadata, before);
});

test("group collection and shared caption prompt remain reachable across runners with AI disabled", () => {
  const collection = Object.fromEntries(
    [
      "group_icl_enable",
      "group_message_max_cnt",
      "image_caption",
      "image_caption_provider_id",
    ].map((key) => [
      `provider_ltm_settings.${key}`,
      {
        type: "bool",
        condition:
          key === "group_icl_enable"
            ? {}
            : {
                "provider_ltm_settings.group_icl_enable": true,
                ...(key === "image_caption_provider_id"
                  ? { "provider_ltm_settings.image_caption": true }
                  : {}),
              },
      },
    ]),
  );
  const metadata = {
    ext_group: { metadata: { ltm: { type: "object", items: collection } } },
    ai_group: {
      metadata: {
        ai: {
          type: "object",
          condition: { "provider_settings.enable": true },
          items: { "provider_settings.image_caption_prompt": { type: "text" } },
        },
      },
    },
  };
  const hierarchy = buildConfigHierarchy(metadata);
  const groups = hierarchy.message_group.metadata;
  assert.equal(groups.group_context.tab, "message_input");
  assert.equal(groups.group_context.runner, undefined);
  assert.equal(
    Object.keys(groups.group_context.items).at(-1),
    "provider_settings.image_caption_prompt",
  );
  for (const runner_type of ["local", "dify"]) {
    for (const enable of [true, false]) {
      const config = {
        agent_runner: { runner_type },
        provider_settings: { enable },
        provider_ltm_settings: {
          group_icl_enable: true,
          image_caption: true,
          image_caption_provider_id: "caption-model",
        },
      };
      const original = structuredClone(config);
      assert.equal(
        Object.keys(getVisibleConfigGroups(groups, config)).length,
        1,
      );
      assert.deepEqual(
        Object.keys(
          getVisibleConfigGroups(groups, config, "image_caption_prompt"),
        ),
        ["group_context"],
      );
      config.provider_ltm_settings.group_icl_enable = false;
      assert.ok(getVisibleConfigGroups(groups, config).group_context);
      assert.deepEqual(
        getVisibleConfigGroups(groups, config, "group_message_max_cnt"),
        {},
      );
      config.provider_ltm_settings.group_icl_enable = true;
      assert.deepEqual(config, original);
    }
  }
});

test("message speech remains editable with conversational AI disabled, preserving its own conditions", () => {
  const metadata = {
    ai_group: {
      metadata: {
        ai: {
          type: "object",
          condition: { "provider_settings.enable": true },
          items: {
            "provider_stt_settings.enable": { type: "bool" },
            "provider_stt_settings.provider_id": {
              type: "string",
              condition: { "provider_stt_settings.enable": true },
            },
            "provider_tts_settings.enable": { type: "bool" },
            "provider_tts_settings.provider_id": {
              type: "string",
              condition: { "provider_tts_settings.enable": true },
            },
          },
        },
      },
    },
  };
  const grouped = buildConfigHierarchy(metadata);
  const groups = grouped.message_group.metadata;
  for (const runner_type of ["local", "dify"]) {
    assert.equal(
      Object.keys(
        getVisibleConfigGroups(groups, {
          agent_runner: { runner_type },
          provider_settings: { enable: false },
          provider_stt_settings: { enable: false },
          provider_tts_settings: { enable: false },
        }),
      ).length,
      2,
    );
  }
  assert.deepEqual(
    groups.speech_input.items["provider_stt_settings.provider_id"].condition,
    { "provider_stt_settings.enable": true },
  );
  assert.deepEqual(
    groups.speech_output.items["provider_tts_settings.provider_id"].condition,
    { "provider_tts_settings.enable": true },
  );
});

test("search finds collapsed items across groups and excludes hidden or inactive fields", () => {
  const groups = {
    compression: {
      description: "Context",
      items: {
        "agent_runner.config.compression.instruction": {
          description: "Compression prompt",
          collapsed: true,
          condition: { "agent_runner.runner_type": "local" },
        },
        hidden: { description: "Compression secret", invisible: true },
      },
    },
    voice: {
      description: "Speech",
      items: { voice: { description: "Speech Recognition" } },
    },
  };
  assert.deepEqual(
    Object.keys(
      getVisibleConfigGroups(
        groups,
        { agent_runner: { runner_type: "local" } },
        "compression",
      ),
    ),
    ["compression"],
  );
  assert.deepEqual(
    Object.keys(
      getVisibleConfigGroups(
        groups,
        { agent_runner: { runner_type: "dify" } },
        "compression",
      ),
    ),
    [],
  );
  assert.deepEqual(
    Object.keys(getVisibleConfigGroups(groups, {}, "secret")),
    [],
  );
  assert.deepEqual(Object.keys(getVisibleConfigGroups(groups, {}, "Speech")), [
    "voice",
  ]);
});

test("search uses translated metadata and group labels", () => {
  const groups = {
    speech: {
      description: "speech.title",
      items: { enable: { description: "speech.enable" } },
    },
  };
  const translations = { "speech.title": "语音识别", "speech.enable": "启用" };
  assert.equal(
    Object.keys(
      getVisibleConfigGroups(
        groups,
        {},
        "语音",
        (key) => translations[key] || key,
      ),
    ).length,
    1,
  );
});

test("new metadata is kept reachable without retaining the ambiguous extensions category", () => {
  const grouped = buildConfigHierarchy({
    ext_group: {
      name: "Extensions",
      metadata: {
        future: { type: "object", items: { new_setting: { type: "bool" } } },
      },
    },
  });
  assert.equal(grouped.ext_group, undefined);
  assert.equal(grouped.message_group.name, "hierarchy.sections.message_group");
  assert.equal(
    grouped.message_group.metadata.ext_group_future.items.new_setting.type,
    "bool",
  );
});

test("all hierarchy labels resolve in every supported locale", () => {
  for (const locale of ["zh-CN", "en-US", "ja-JP", "ru-RU"]) {
    const { hierarchy } = JSON.parse(
      readFileSync(
        new URL(
          `../src/i18n/locales/${locale}/features/config.json`,
          import.meta.url,
        ),
        "utf8",
      ),
    );
    for (const [key, section] of Object.entries(CONFIG_SECTIONS)) {
      assert.ok(hierarchy.sections[key], `${locale}: ${key}`);
      assert.ok(hierarchy.descriptions[key], `${locale}: ${key} description`);
      for (const tab of section.tabs)
        assert.ok(hierarchy.tabs[tab], `${locale}: ${tab}`);
    }
    for (const group of CONFIG_GROUPS) {
      assert.ok(hierarchy.groups[group.key]?.title, `${locale}: ${group.key}`);
      assert.ok(
        hierarchy.groups[group.key]?.hint,
        `${locale}: ${group.key} hint`,
      );
      assert.ok(
        hierarchy.tabs[group.tab] || !group.tab,
        `${locale}: ${group.tab}`,
      );
    }
  }
});
