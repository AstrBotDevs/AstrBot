import geminiThinkingLevels from "./geminiThinkingLevels.json";
import type { ProviderModelMetadata } from "./providerMetadata";

// Known model levels mirror GEMINI_4_THINKING_LEVELS in gemini_source.py.
export const GEMINI_4_REASONING_LEVELS: Record<string, string[]> =
  geminiThinkingLevels.models;
// Offer only the shared levels until a model's xhigh support is known.
export const GEMINI_4_FALLBACK_REASONING_LEVELS: string[] =
  geminiThinkingLevels.fallback;

// Ordered reasoning effort spectrum (weakest to strongest).
export const REASONING_EFFORT_LEVELS = [
  "none",
  "minimal",
  "low",
  "medium",
  "high",
  "xhigh",
  "max",
] as const;
export type ReasoningEffort = (typeof REASONING_EFFORT_LEVELS)[number];

/** Return the menu options and the active preference for this model. */
export function resolveReasoningEffort(
  provider: {
    type?: string;
    model?: string;
    provider?: string;
    ollama_disable_thinking?: boolean | string;
  } | null | undefined,
  metadata: ProviderModelMetadata | null | undefined,
  manual?: string | null,
): { levels: ReasoningEffort[]; effort: ReasoningEffort | null } {
  if (!provider) return { levels: [], effort: null };

  if (provider.provider === "ollama") {
    const disabled = provider.ollama_disable_thinking;
    const thinkingDisabled = typeof disabled === "string"
      ? ["1", "true", "yes", "on"].includes(disabled.trim().toLowerCase())
      : disabled;
    if (thinkingDisabled) {
      return { levels: [], effort: null };
    }
  }

  let supported = metadata?.reasoning_efforts ?? [];
  if (provider.type === "googlegenai_chat_completion") {
    const model = provider.model?.toLowerCase().split("/").pop() ?? "";
    supported = model.startsWith("gemini-4")
      ? Object.entries(GEMINI_4_REASONING_LEVELS).find(
          ([id]) => model === id || model.startsWith(`${id}-`),
        )?.[1] ?? GEMINI_4_FALLBACK_REASONING_LEVELS
      : [];
  }
  const offValue = metadata?.reasoning_off_value;
  if (offValue) {
    supported = supported.map((value) => value === offValue ? "none" : value);
  }
  const levels = REASONING_EFFORT_LEVELS.filter((level) =>
    supported.includes(level),
  );
  return { levels, effort: levels.find((level) => level === manual) ?? null };
}
