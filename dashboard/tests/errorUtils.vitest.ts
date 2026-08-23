import { describe, expect, it } from 'vitest';
import { resolveErrorMessage } from '@/utils/errorUtils';

describe('resolveErrorMessage', () => {
  it('formats FastAPI validation detail arrays', () => {
    const message = resolveErrorMessage({
      response: {
        data: {
          detail: [
            {
              loc: ['body', 'config'],
              msg: 'Field required',
            },
          ],
        },
      },
    });

    expect(message).toBe('body.config: Field required');
  });

  it('skips non-object validation items and uses message or loc alone', () => {
    expect(
      resolveErrorMessage({
        response: {
          data: {
            detail: [
              null,
              'plain',
              { loc: [], msg: 'only-message' },
              { loc: ['query'], msg: '' },
            ],
          },
        },
      }),
    ).toBe('only-message; query');
  });

  it('prefers string error fields and falls back when no message keys exist', () => {
    expect(
      resolveErrorMessage({
        response: { data: { error: '  boom  ' } },
      }),
    ).toBe('boom');
    expect(
      resolveErrorMessage({ response: { data: { foo: 1 } } }, 'fallback'),
    ).toBe('fallback');
  });
});
