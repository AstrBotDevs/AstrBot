import { createPinia, setActivePinia } from 'pinia';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/api/v1', () => ({
  providerApi: {
    schema: vi.fn().mockResolvedValue({
      data: {
        data: {
          templates: {
            openai: {
              provider_type: 'chat_completion',
              provider: 'openai',
            },
          },
          sources: [],
          providers: [],
        },
      },
    }),
    list: vi.fn().mockResolvedValue({ data: { data: [] } }),
    models: vi.fn().mockResolvedValue({ data: { data: [] } }),
    test: vi.fn().mockResolvedValue({ data: { status: 'ok' } }),
  },
}));

vi.mock('@/utils/confirmDialog', () => ({
  askForConfirmation: vi.fn().mockResolvedValue(true),
  useConfirmDialog: () => undefined,
}));

import { useProviderSources } from '@/composables/useProviderSources';

describe('useProviderSources', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it('exposes computed collections and helper formatters', async () => {
    const sources = useProviderSources({
      tm: (key: string) => key,
      showMessage: vi.fn(),
    });
    await sources.loadProviderTemplate();
    expect(sources.providerTypes.value.length).toBeGreaterThan(0);
    expect(Array.isArray(sources.availableSourceTypes.value)).toBe(true);
    expect(Array.isArray(sources.displayedProviderSources.value)).toBe(true);
    expect(sources.sourceProviders.value).toEqual([]);
    expect(sources.mergedModelEntries.value).toEqual(expect.any(Array));
    expect(sources.filteredMergedModelEntries.value).toEqual(expect.any(Array));
    expect(sources.filteredProviders.value).toEqual(expect.any(Array));
    sources.updateDefaultTab('chat_completion');
    expect(
      sources.getSourceDisplayName({ id: 'openai', name: 'OpenAI' }),
    ).toBeDefined();
    expect(sources.resolveSourceIcon({ provider: 'openai' })).toBeDefined();
    expect(sources.supportsImageInput({})).toBe(false);
    expect(sources.supportsAudioInput({})).toBe(false);
    expect(sources.supportsToolCall({})).toBe(false);
    expect(sources.supportsReasoning({})).toBe(false);
    expect(sources.formatContextLimit({})).toBeDefined();
    expect(sources.modelAlreadyConfigured('gpt')).toBe(false);
    sources.selectProviderSource(null);
    sources.addProviderSource();
  });
});
