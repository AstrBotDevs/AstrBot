import { isConfigFieldVisible } from "./configVisibility.mjs";

// Field paths remain backend selectors; this table only defines their UI ownership.
export const CONFIG_SECTIONS = {
  ai_group: {
    icon: "mdi-auto-fix",
    tabs: [],
  },
  message_group: {
    icon: "mdi-message-text-outline",
    tabs: ["message_input", "ai_trigger", "commands", "safety", "output"],
  },
  session_group: {
    icon: "mdi-account-lock-outline",
    tabs: ["access", "session"],
  },
  platform_group: {
    icon: "mdi-robot-outline",
    tabs: [
      "platform_common",
      "platform_onebot",
      "platform_lark",
      "platform_telegram",
      "platform_discord",
    ],
  },
  plugin_group: { icon: "mdi-puzzle-outline", tabs: [] },
  system_group: {
    icon: "mdi-cog-outline",
    tabs: ["security", "logs", "network", "runtime"],
  },
};

export const CONFIG_GROUPS = [
  {
    section: "ai_group",
    key: "agent_runner",
    source: ["ai_group", "agent_runner"],
    tab: "runner",
  },
  ...["dify", "coze", "dashscope", "deerflow"].flatMap((runner) => [
    {
      section: "ai_group",
      key: `${runner}_connection`,
      source: ["ai_group", `${runner}_runner`],
      tab: "connection",
      runner,
      fields: [
        "timeout",
        "proxy",
        `${runner}_api_key`,
        `${runner}_api_base`,
        "deerflow_auth_header",
      ].map((key) => `agent_runner.config.${key}`),
    },
    {
      section: "ai_group",
      key: `${runner}_application`,
      source: ["ai_group", `${runner}_runner`],
      tab: "application",
      runner,
    },
  ]),
  {
    section: "ai_group",
    key: "local_model",
    source: ["ai_group", "ai"],
    tab: "model",
    runner: "local",
    fields: ["provider_id", "fallback_provider_ids", "request_max_retries"].map(
      (key) => `agent_runner.config.model.${key}`,
    ),
  },
  {
    section: "ai_group",
    key: "persona",
    source: ["ai_group", "persona"],
    tab: "persona",
    runner: "local",
  },
  {
    section: "ai_group",
    key: "local_prompt",
    source: ["ai_group", "others"],
    tab: "persona",
    runner: "local",
    fields: [
      "identifier",
      "group_name_display",
      "datetime_system_prompt",
      "prompt_prefix",
    ].map((key) => `provider_settings.${key}`),
  },
  {
    section: "ai_group",
    key: "tool_execution",
    source: ["ai_group", "others"],
    tab: "capabilities",
    runner: "local",
    fields: [
      "agent_runner.config.misc.max_steps",
      "agent_runner.config.misc.tool_call_timeout",
      "agent_runner.config.misc.tool_schema_mode",
      "provider_settings.show_tool_use_status",
      "provider_settings.show_tool_call_result",
      "provider_settings.buffer_intermediate_messages",
    ],
  },
  ...[
    "agent_computer_use",
    "knowledgebase",
    "websearch",
    "proactive_capability",
  ].map((key) => ({
    section: "ai_group",
    key,
    source: ["ai_group", key],
    tab: "capabilities",
    runner: "local",
  })),
  {
    section: "ai_group",
    key: "truncate_and_compress",
    source: ["ai_group", "truncate_and_compress"],
    tab: "context",
    runner: "local",
  },
  {
    section: "ai_group",
    key: "context_modalities",
    source: ["ai_group", "others"],
    tab: "context",
    runner: "local",
    fields: ["agent_runner.config.misc.sanitize_context_by_modalities"],
  },
  {
    section: "message_group",
    key: "wake",
    source: ["platform_group", "general"],
    tab: "ai_trigger",
    fields: [
      "wake_prefix",
      "platform_settings.friend_message_needs_wake_prefix",
      "platform_settings.empty_mention_waiting",
    ],
  },
  {
    section: "message_group",
    key: "wake",
    source: ["platform_group", "others"],
    tab: "ai_trigger",
    fields: ["platform_settings.ignore_at_all"],
  },
  {
    section: "message_group",
    key: "ai_request",
    source: ["ai_group", "others"],
    tab: "ai_trigger",
    fields: ["provider_settings.wake_prefix"],
  },
  {
    section: "message_group",
    key: "builtin_commands",
    source: ["platform_group", "general"],
    tab: "commands",
    fields: ["disable_builtin_commands"],
  },
  {
    section: "message_group",
    key: "model_commands",
    source: ["ai_group", "others"],
    tab: "commands",
    fields: ["provider_settings.reachability_check"],
  },
  {
    section: "message_group",
    key: "group_context",
    source: ["ext_group", "ltm"],
    tab: "message_input",
    fields: [
      "group_icl_enable",
      "group_message_max_cnt",
      "image_caption",
      "image_caption_provider_id",
    ].map((key) => `provider_ltm_settings.${key}`),
  },
  {
    section: "message_group",
    key: "group_context",
    source: ["ai_group", "ai"],
    tab: "message_input",
    fields: ["provider_settings.image_caption_prompt"],
  },
  {
    section: "message_group",
    key: "active_reply",
    source: ["ext_group", "ltm"],
    tab: "ai_trigger",
    fields: ["enable", "method", "possibility_reply", "whitelist"].map(
      (key) => `provider_ltm_settings.active_reply.${key}`,
    ),
  },

  {
    section: "message_group",
    key: "rate_limit",
    source: ["platform_group", "rate_limit"],
    tab: "message_input",
  },
  {
    section: "message_group",
    key: "message_admission",
    source: ["platform_group", "others"],
    tab: "message_input",
    fields: ["platform_settings.ignore_bot_self_message"],
  },
  {
    section: "message_group",
    key: "speech_input",
    source: ["ai_group", "ai"],
    tab: "message_input",
    fields: [
      "provider_stt_settings.enable",
      "provider_stt_settings.provider_id",
    ],
  },
  {
    section: "ai_group",
    key: "image_input",
    source: ["ai_group", "ai"],
    tab: "input",
    runner: "local",
    fields: ["provider_settings.default_image_caption_provider_id"],
  },
  {
    section: "ai_group",
    key: "image_input",
    source: ["ai_group", "others"],
    tab: "input",
    runner: "local",
    fields: ["provider_settings.image_compress_options.max_size"],
  },
  {
    section: "ai_group",
    key: "quoted_input",
    source: ["ai_group", "others"],
    tab: "input",
    runner: "local",
    fields: [
      "provider_settings.max_quoted_fallback_images",
      ...[
        "max_component_chain_depth",
        "max_forward_node_depth",
        "max_forward_fetch",
        "warn_on_action_failure",
      ].map((key) => `provider_settings.quoted_message_parser.${key}`),
    ],
  },
  {
    section: "message_group",
    key: "content_safety",
    source: ["platform_group", "content_safety"],
    tab: "safety",
  },
  {
    section: "message_group",
    key: "text_output",
    source: ["platform_group", "general"],
    tab: "output",
    fields: ["platform_settings.reply_prefix"],
  },
  {
    section: "message_group",
    key: "streaming_output",
    source: ["ai_group", "others"],
    tab: "output",
    fields: [
      "provider_settings.streaming_response",
      "provider_settings.unsupported_streaming_strategy",
    ],
  },
  {
    section: "message_group",
    key: "reasoning_output",
    source: ["ai_group", "others"],
    tab: "output",
    fields: ["provider_settings.display_reasoning_text"],
  },
  {
    section: "message_group",
    key: "speech_output",
    source: ["ai_group", "ai"],
    tab: "output",
    fields: [
      "provider_tts_settings.enable",
      "provider_tts_settings.provider_id",
      "provider_tts_settings.trigger_probability",
    ],
  },
  {
    section: "message_group",
    key: "speech_output",
    source: ["ai_group", "others"],
    tab: "output",
    fields: ["provider_tts_settings.dual_output"],
  },
  {
    section: "message_group",
    key: "segmented_reply",
    source: ["ext_group", "segmented_reply"],
    tab: "output",
  },
  {
    section: "message_group",
    key: "t2i",
    source: ["ext_group", "t2i"],
    tab: "output",
  },

  {
    section: "session_group",
    key: "permissions",
    source: ["platform_group", "general"],
    tab: "access",
    fields: ["admins_id"],
  },
  {
    section: "session_group",
    key: "permissions",
    source: ["platform_group", "others"],
    tab: "access",
    fields: ["platform_settings.no_permission_reply"],
  },
  {
    section: "session_group",
    key: "whitelist",
    source: ["platform_group", "whitelist"],
    tab: "access",
  },
  {
    section: "session_group",
    key: "session_isolation",
    source: ["platform_group", "general"],
    tab: "session",
    fields: ["platform_settings.unique_session"],
  },
  {
    section: "session_group",
    key: "group_history",
    source: ["ext_group", "ltm"],
    tab: "session",
    fields: [
      "provider_ltm_settings.group_message_history_enable",
      "provider_ltm_settings.group_message_history_max_cnt",
    ],
  },

  {
    section: "platform_group",
    key: "platform_delivery",
    source: ["platform_group", "general"],
    tab: "platform_common",
    fields: [
      "platform_settings.reply_with_mention",
      "platform_settings.reply_with_quote",
    ],
  },
  {
    section: "platform_group",
    key: "onebot_delivery",
    source: ["platform_group", "general"],
    tab: "platform_onebot",
    fields: ["platform_settings.forward_threshold"],
  },
  ...["lark", "telegram", "discord"].map((platform) => ({
    section: "platform_group",
    key: `${platform}_feedback`,
    source: ["platform_group", "others"],
    tab: `platform_${platform}`,
    fields: ["enable", "emojis"].map(
      (key) => `platform_specific.${platform}.pre_ack_emoji.${key}`,
    ),
  })),
  {
    section: "plugin_group",
    key: "plugin",
    source: ["plugin_group", "plugin"],
  },

  {
    section: "system_group",
    key: "webui_security",
    source: ["system_group", "system"],
    tab: "security",
    fields: [
      "dashboard.ssl.enable",
      "dashboard.ssl.cert_file",
      "dashboard.ssl.key_file",
      "dashboard.ssl.ca_certs",
      "dashboard.trust_proxy_headers",
      "dashboard.auth_rate_limit.enable",
      "dashboard.auth_rate_limit.average_interval",
      "dashboard.auth_rate_limit.max_burst",
      "dashboard.totp.enable",
    ],
  },
  {
    section: "system_group",
    key: "logging",
    source: ["system_group", "system"],
    tab: "logs",
    fields: [
      "log_level",
      "log_file_enable",
      "log_file_path",
      "log_file_max_mb",
      "trace_log_enable",
      "trace_log_path",
      "trace_log_max_mb",
    ],
  },
  {
    section: "system_group",
    key: "network",
    source: ["system_group", "system"],
    tab: "network",
    fields: ["callback_api_base", "http_proxy", "no_proxy"],
  },
  {
    section: "system_group",
    key: "dependencies",
    source: ["system_group", "system"],
    tab: "runtime",
    fields: ["pip_install_arg", "pypi_index_url"],
  },
  {
    section: "system_group",
    key: "storage",
    source: ["system_group", "system"],
    tab: "runtime",
    fields: ["temp_dir_max_size"],
  },
  {
    section: "system_group",
    key: "time",
    source: ["system_group", "system"],
    tab: "runtime",
    fields: ["timezone"],
  },
];

/**
 * Build the UI tree without modifying backend metadata or stored values.
 *
 * Args:
 *     metadata: Original core configuration sections returned by the API.
 *
 * Returns:
 *     Sections containing independently owned groups with inherited conditions.
 */
export function buildConfigHierarchy(metadata = {}) {
  const sections = {};
  const assigned = new Set();
  for (const rule of CONFIG_GROUPS) {
    const [sourceSection, sourceKey] = rule.source;
    const source = metadata[sourceSection]?.metadata?.[sourceKey];
    if (!source) continue;
    const items = {};
    for (const [field, item] of Object.entries(source.items || {})) {
      const identity = `${sourceSection}/${sourceKey}/${field}`;
      if (
        assigned.has(identity) ||
        (rule.fields && !rule.fields.includes(field))
      )
        continue;
      assigned.add(identity);
      const condition = { ...source.condition, ...item.condition };
      // Speech conversion and message presentation are independent of conversational AI.
      if (rule.section === "message_group")
        delete condition["provider_settings.enable"];
      items[field] = { ...item, condition };
    }
    if (!Object.keys(items).length) continue;
    const section = (sections[rule.section] ||= {
      name: `hierarchy.sections.${rule.section}`,
      metadata: {},
    });
    const group = (section.metadata[rule.key] ||= {
      ...source,
      condition: undefined,
      items: {},
      tab: rule.tab,
      runner: rule.runner,
      description: `hierarchy.groups.${rule.key}.title`,
      hint: `hierarchy.groups.${rule.key}.hint`,
    });
    Object.assign(group.items, items);
  }

  // Keep future or plugin-injected metadata reachable rather than silently dropping it.
  for (const [sourceSection, section] of Object.entries(metadata)) {
    for (const [sourceKey, group] of Object.entries(section.metadata || {})) {
      const items = Object.fromEntries(
        Object.entries(group.items || {}).filter(
          ([field]) => !assigned.has(`${sourceSection}/${sourceKey}/${field}`),
        ),
      );
      if (!Object.keys(items).length) continue;
      const destination =
        sourceSection === "ext_group" ? "message_group" : sourceSection;
      const target = (sections[destination] ||= {
        ...section,
        name: CONFIG_SECTIONS[destination]
          ? `hierarchy.sections.${destination}`
          : section.name,
        metadata: {},
      });
      target.metadata[`${sourceSection}_${sourceKey}`] = { ...group, items };
    }
  }
  return sections;
}

/**
 * Match visible fields using the same conditions and text as the configuration editor.
 *
 * Args:
 *     groups: Configuration group metadata.
 *     config: Current configuration values.
 *     keyword: Search text, including field paths or translated labels.
 *     translate: Resolver for metadata translation keys.
 *
 * Returns:
 *     Groups with at least one visible matching field.
 */
export function getVisibleConfigGroups(
  groups,
  config,
  keyword = "",
  translate = (value) => value,
) {
  const search = String(keyword).trim().toLowerCase();
  const visible = {};
  for (const [key, group] of Object.entries(groups || {})) {
    if (
      group.runner &&
      group.runner !== (config.agent_runner?.runner_type || "local")
    )
      continue;
    const groupText = [
      translate(group.description || ""),
      translate(group.hint || ""),
    ]
      .join(" ")
      .toLowerCase();
    const matches = Object.entries(group.items || {}).some(([field, item]) => {
      if (!isConfigFieldVisible(item, field, config, group.condition))
        return false;
      const text = [
        field,
        translate(item.description || ""),
        translate(item.hint || ""),
      ]
        .join(" ")
        .toLowerCase();
      return !search || groupText.includes(search) || text.includes(search);
    });
    if (matches) visible[key] = group;
  }
  return visible;
}
