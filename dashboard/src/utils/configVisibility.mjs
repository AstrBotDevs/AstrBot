// These UI dependencies do not change stored values or backend metadata.
export const CONFIG_VISIBILITY_RULES = {
  "provider_settings.reachability_check": (config) =>
    config.disable_builtin_commands !== true,
  // Only DeerFlow forwards this per-runner proxy; other clients do not read it.
  "agent_runner.config.proxy": (config) =>
    config.agent_runner?.runner_type === "deerflow",
  // DashScope reads this value but never passes it to Application.call.
  "agent_runner.config.timeout": (config) =>
    ["dify", "coze", "deerflow"].includes(config.agent_runner?.runner_type),
  "provider_settings.image_caption_prompt": (config) =>
    Boolean(
      ((config.agent_runner?.runner_type || "local") === "local" &&
        config.provider_settings?.enable !== false &&
        config.provider_settings?.default_image_caption_provider_id?.trim()) ||
        (config.provider_ltm_settings?.group_icl_enable &&
          config.provider_ltm_settings?.image_caption &&
          config.provider_ltm_settings?.image_caption_provider_id?.trim()),
    ),
  "provider_tts_settings.dual_output": (config) =>
    config.provider_tts_settings?.enable === true,
  ...Object.fromEntries(
    [
      "only_llm_result",
      "interval_method",
      "interval",
      "log_base",
      "words_count_threshold",
      "split_mode",
      "regex",
      "split_words",
      "content_cleanup_rule",
    ].map((key) => [
      `platform_settings.segmented_reply.${key}`,
      (config) => config.platform_settings?.segmented_reply?.enable === true,
    ]),
  ),
  "platform_settings.id_whitelist": (config) =>
    config.platform_settings?.enable_id_white_list === true,
  ...Object.fromEntries(
    [
      "id_whitelist_log",
      "wl_ignore_admin_on_group",
      "wl_ignore_admin_on_friend",
    ].map((key) => [
      `platform_settings.${key}`,
      (config) =>
        config.platform_settings?.enable_id_white_list === true &&
        config.platform_settings?.id_whitelist?.some((id) => String(id).trim()),
    ]),
  ),
  "content_safety.internal_keywords.extra_keywords": (config) =>
    config.content_safety?.internal_keywords?.enable === true,
  "content_safety.also_use_in_response": (config) =>
    config.content_safety?.internal_keywords?.enable === true ||
    config.content_safety?.baidu_aip?.enable === true,
  "agent_runner.config.dify_workflow_output_key": (config) =>
    config.agent_runner?.config?.dify_api_type === "workflow",
  "agent_runner.config.dify_query_input_key": (config) =>
    config.agent_runner?.config?.dify_api_type === "workflow",
  "agent_runner.config.deerflow_max_concurrent_subagents": (config) =>
    config.agent_runner?.config?.deerflow_subagent_enabled === true,
  ...Object.fromEntries(
    ["log_file", "trace_log"].flatMap((prefix) =>
      ["path", "max_mb"].map((key) => [
        `${prefix}_${key}`,
        (config) => config[`${prefix}_enable`] === true,
      ]),
    ),
  ),
  no_proxy: (config) => Boolean(config.http_proxy?.trim()),
  // Session knowledge selection overrides the final count, but still uses fusion limits.
  kb_final_top_k: (config) => Boolean(config.kb_names?.length),
};

/**
 * Apply source conditions and additional core UI dependencies consistently.
 *
 * Args:
 *     item: Field metadata, including conditions and hidden markers.
 *     field: Backend selector for the field.
 *     config: Current editable configuration, never modified here.
 *     groupCondition: Conditions inherited from the containing group.
 *     core: Whether to apply core dependencies rather than plugin metadata alone.
 *
 * Returns:
 *     Whether the field can be displayed and included in search results.
 */
export function isConfigFieldVisible(
  item,
  field,
  config,
  groupCondition = {},
  core = true,
) {
  if (item?.invisible) return false;
  for (const [selector, expected] of Object.entries({
    ...groupCondition,
    ...item?.condition,
  })) {
    // Keep the saved merge option editable; its streaming limitation is shown as a notice.
    if (
      core &&
      field === "provider_settings.buffer_intermediate_messages" &&
      selector === "provider_settings.streaming_response" &&
      expected === false
    )
      continue;
    let value = config;
    for (const part of selector.split(".")) value = value?.[part];
    if (value !== expected) return false;
  }
  return (
    !core ||
    !CONFIG_VISIBILITY_RULES[field] ||
    Boolean(CONFIG_VISIBILITY_RULES[field](config))
  );
}
