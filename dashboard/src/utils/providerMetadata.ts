export interface ProviderModelMetadata {
  modalities?: { input?: string[] }
  tool_call?: boolean
  reasoning?: boolean
  limit?: { context?: number }
}

export interface ProviderMetadataSource {
  modalities?: string[]
  model_metadata?: ProviderModelMetadata | null
  max_context_tokens?: number
  reasoning?: boolean
}

export interface ProviderCapabilityBadge {
  key: string
  icon: string
  enabled: boolean
  tooltip: string
}

export function formatContextLimit(provider: ProviderMetadataSource | null | undefined): string {
  const context = provider?.model_metadata?.limit?.context || provider?.max_context_tokens
  if (!context || typeof context !== 'number') return ''
  if (context >= 1_000_000) return `${Math.round(context / 1_000_000)}M`
  if (context >= 1_000) return `${Math.round(context / 1_000)}K`
  return `${context}`
}

export function providerCapabilityBadges(
  provider: ProviderMetadataSource | null | undefined,
  tm: (key: string, params?: Record<string, string>) => string
): ProviderCapabilityBadge[] {
  const inputs = provider?.model_metadata?.modalities?.input || []
  const providerModalities = provider?.modalities
  const modalities = Array.isArray(providerModalities) ? providerModalities : []
  const definitions = [
    {
      key: 'image',
      icon: 'mdi-image-outline',
      supported: inputs.includes('image'),
      enabled: modalities.includes('image'),
      label: tm('models.metadata.image')
    },
    {
      key: 'audio',
      icon: 'mdi-music-note-outline',
      supported: inputs.includes('audio'),
      enabled: modalities.includes('audio'),
      label: tm('models.metadata.audio')
    },
    {
      key: 'tool_use',
      icon: 'mdi-wrench-outline',
      supported: Boolean(provider?.model_metadata?.tool_call),
      enabled: modalities.includes('tool_use'),
      label: tm('models.metadata.toolUse')
    },
    {
      key: 'reasoning',
      icon: 'mdi-brain',
      supported: Boolean(provider?.model_metadata?.reasoning),
      enabled: Boolean(provider?.reasoning),
      label: tm('models.metadata.reasoning')
    }
  ]

  return definitions
    .filter((item) => item.supported || item.enabled)
    .map((item) => ({
      key: item.key,
      icon: item.icon,
      enabled: !provider?.model_metadata || item.enabled,
      tooltip:
        provider?.model_metadata && !item.enabled
          ? tm('models.metadata.supportedDisabled', { capability: item.label })
          : tm('models.metadata.enabled', { capability: item.label })
    }))
}
