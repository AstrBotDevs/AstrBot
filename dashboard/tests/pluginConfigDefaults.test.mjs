import { describe, expect, it } from 'vitest';

import {
  canRestorePluginConfigDefault,
  getPluginConfigDefaultValue,
  isPluginConfigValueModified,
} from '../src/utils/pluginConfigDefaults';

describe('plugin configuration defaults', () => {
  it('uses explicit scalar defaults', () => {
    const meta = { type: 'int', default: 12 };

    expect(isPluginConfigValueModified(12, meta)).toBe(false);
    expect(isPluginConfigValueModified(13, meta)).toBe(true);
    expect(getPluginConfigDefaultValue(meta)).toBe(12);
  });

  it('uses backend-equivalent implicit collection defaults', () => {
    expect(getPluginConfigDefaultValue({ type: 'list' })).toEqual([]);
    expect(getPluginConfigDefaultValue({ type: 'dict' })).toEqual({});
    expect(isPluginConfigValueModified([], { type: 'list' })).toBe(false);
    expect(isPluginConfigValueModified({}, { type: 'dict' })).toBe(false);
  });

  it('recursively builds object values from items', () => {
    const meta = {
      type: 'object',
      default: { ignored: true },
      items: {
        enabled: { type: 'bool', default: true },
        nested: {
          type: 'object',
          items: { retries: { type: 'int' } },
        },
      },
    };

    expect(getPluginConfigDefaultValue(meta)).toEqual({
      enabled: true,
      nested: { retries: 0 },
    });
    expect(
      isPluginConfigValueModified(
        { enabled: true, nested: { retries: 0 } },
        meta,
      ),
    ).toBe(false);
  });

  it('does not mutate schema defaults when restoring deep values', () => {
    const meta = {
      type: 'list',
      default: [{ name: 'alpha', values: [1, 2] }],
    };
    const restored = getPluginConfigDefaultValue(meta);
    restored[0].values.push(3);

    expect(meta.default).toEqual([{ name: 'alpha', values: [1, 2] }]);
  });

  it('hides reset for readonly and unknown fields', () => {
    expect(
      canRestorePluginConfigDefault('changed', {
        type: 'string',
        readonly: true,
      }),
    ).toBe(false);
    expect(getPluginConfigDefaultValue({ type: 'unknown' })).toBeUndefined();
    expect(isPluginConfigValueModified('changed', { type: 'unknown' })).toBe(
      false,
    );
    expect(canRestorePluginConfigDefault('changed', { type: 'unknown' })).toBe(
      false,
    );
  });
});
