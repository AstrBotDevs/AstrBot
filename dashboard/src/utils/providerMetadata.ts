export interface ProviderModelMetadata {
  modalities?: { input?: string[] }
  tool_call?: boolean
  reasoning?: boolean
  limit?: { context?: number }
}

export interface ProviderMetadataSource {
  model?: string
  modalities?: string[]
  max_context_tokens?: number
  reasoning?: boolean
}

export interface ProviderCapabilityBadge {
  key: string
  icon: string
  enabled: boolean
  tooltip: string
}

export function contextLimit(
  provider: ProviderMetadataSource | null | undefined,
  metadata?: ProviderModelMetadata | null
): number {
  const context = Number(provider?.max_context_tokens) || Number(metadata?.limit?.context) || 0
  return Number.isFinite(context) && context > 0 ? context : 0
}

export function formatTokenCount(value: number): string {
  if (!Number.isFinite(value)) return ''
  const absValue = Math.abs(value)
  if (absValue >= 1_000_000) return `${formatCompactNumber(value / 1_000_000)}M`
  if (absValue >= 1_000) return `${formatCompactNumber(value / 1_000)}K`
  return `${Math.round(value)}`
}

export function formatContextLimit(
  provider: ProviderMetadataSource | null | undefined,
  metadata?: ProviderModelMetadata | null
): string {
  const context = contextLimit(provider, metadata)
  return context ? formatTokenCount(context) : ''
}

export function providerCapabilityBadges(
  provider: ProviderMetadataSource | null | undefined,
  metadata: ProviderModelMetadata | null | undefined,
  tm: (key: string, params?: Record<string, string>) => string
): ProviderCapabilityBadge[] {
  const inputs = metadata?.modalities?.input || []
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
      supported: Boolean(metadata?.tool_call),
      enabled: modalities.includes('tool_use'),
      label: tm('models.metadata.toolUse')
    },
    {
      key: 'reasoning',
      icon: 'mdi-brain',
      supported: Boolean(metadata?.reasoning),
      enabled: Boolean(provider?.reasoning),
      label: tm('models.metadata.reasoning')
    }
  ]

  return definitions
    .filter((item) => item.supported || item.enabled)
    .map((item) => ({
      key: item.key,
      icon: item.icon,
      enabled: !metadata || item.enabled,
      tooltip:
        metadata && !item.enabled
          ? tm('models.metadata.supportedDisabled', { capability: item.label })
          : tm('models.metadata.enabled', { capability: item.label })
    }))
}

function formatCompactNumber(value: number): string {
  const absValue = Math.abs(value)
  const rounded = absValue >= 10 ? Math.round(value) : Math.round(value * 10) / 10
  return String(rounded).replace(/\.0$/, '')
}
