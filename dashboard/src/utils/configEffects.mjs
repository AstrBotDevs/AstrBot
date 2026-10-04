/**
 * Describe runtime-dependent output effects without changing configuration.
 *
 * Args:
 *     field: Full backend selector for a displayed field.
 *     config: Current editable core configuration.
 *
 * Returns:
 *     Translation keys for effects that apply to the enabled field.
 */
export function getConfigEffectNotices(field, config) {
  const notices = [];
  const platform = config.platform_settings || {};
  const provider = config.provider_settings || {};
  const tts = config.provider_tts_settings || {};
  const segmented = platform.segmented_reply?.enable === true;
  const streaming =
    provider.streaming_response === true && provider.enable !== false;
  const voice = tts.enable === true && Number(tts.trigger_probability ?? 1) > 0;
  const enabled = {
    "platform_settings.reply_prefix": Boolean(platform.reply_prefix),
    "platform_settings.segmented_reply.enable": segmented,
    "provider_tts_settings.enable": tts.enable === true,
    t2i: config.t2i === true,
    "content_safety.also_use_in_response":
      config.content_safety?.also_use_in_response === true,
    "provider_settings.buffer_intermediate_messages":
      provider.buffer_intermediate_messages === true,
    "provider_settings.display_reasoning_text":
      provider.display_reasoning_text === true,
    "platform_settings.reply_with_mention":
      platform.reply_with_mention === true,
    "platform_settings.reply_with_quote": platform.reply_with_quote === true,
    "platform_settings.forward_threshold": Number.isFinite(
      Number(platform.forward_threshold),
    ),
  };
  if (!enabled[field]) return notices;

  if (
    streaming &&
    [
      "platform_settings.reply_prefix",
      "platform_settings.segmented_reply.enable",
      "provider_tts_settings.enable",
      "t2i",
      "platform_settings.forward_threshold",
    ].includes(field)
  )
    notices.push("streamingDecoration");
  if (streaming && field === "content_safety.also_use_in_response")
    notices.push("streamingSafety");
  if (streaming && field === "provider_settings.buffer_intermediate_messages")
    notices.push("streamingBuffer");
  if (
    streaming &&
    [
      "platform_settings.reply_with_mention",
      "platform_settings.reply_with_quote",
    ].includes(field)
  )
    notices.push("streamingPlatform");
  if (voice && field === "t2i" && provider.enable !== false)
    notices.push("voiceBeforeImage");
  if (
    voice &&
    field === "provider_settings.display_reasoning_text" &&
    provider.enable !== false
  )
    notices.push("voiceReasoning");
  if (
    voice &&
    [
      "platform_settings.reply_with_mention",
      "platform_settings.reply_with_quote",
    ].includes(field) &&
    provider.enable !== false
  )
    notices.push("voiceDecoration");
  if (
    segmented &&
    config.t2i === true &&
    field === "platform_settings.segmented_reply.enable"
  )
    notices.push("imageBeforeSegments");
  if (segmented && field === "platform_settings.forward_threshold")
    notices.push("forwardBeforeSegments");
  if (
    Number.isFinite(Number(platform.forward_threshold)) &&
    [
      "platform_settings.reply_with_mention",
      "platform_settings.reply_with_quote",
    ].includes(field)
  )
    notices.push("forwardDecoration");
  return notices;
}
