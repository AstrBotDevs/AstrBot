import { describe, expect, it, vi } from 'vitest';
import { runProviderMutationWithStepUp } from '@/utils/providerStepUp';

describe('runProviderMutationWithStepUp', () => {
  it('retries a protected provider mutation with the issued credential', async () => {
    const operation = vi
      .fn()
      .mockRejectedValueOnce({
        response: {
          data: {
            data: { requires_step_up: true },
          },
        },
      })
      .mockResolvedValueOnce('completed');
    const requestStepUp = vi.fn().mockResolvedValue('step-up-token');

    await expect(
      runProviderMutationWithStepUp(operation, 'provider-1', requestStepUp),
    ).resolves.toBe('completed');
    expect(requestStepUp).toHaveBeenCalledWith({
      action: 'provider.credentials.write',
      resourceType: 'provider',
      resourceId: 'provider-1',
      configId: 'default',
    });
    expect(operation).toHaveBeenNthCalledWith(1);
    expect(operation).toHaveBeenNthCalledWith(2, 'step-up-token');
  });

  it('returns null when the user cancels step-up', async () => {
    const operation = vi.fn().mockRejectedValue({
      response: {
        data: {
          data: { requires_step_up: true },
        },
      },
    });
    const requestStepUp = vi.fn().mockResolvedValue(null);

    await expect(
      runProviderMutationWithStepUp(operation, 'provider-1', requestStepUp),
    ).resolves.toBeNull();
    expect(operation).toHaveBeenCalledOnce();
  });
});
