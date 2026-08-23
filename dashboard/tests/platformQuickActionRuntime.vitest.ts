import { describe, expect, it } from 'vitest';
import {
  buildQuickActionPayload,
  buildQuickActionResultSummary,
  createInitialQuickActionForm,
  tryParseJsonRecord,
} from '@/components/platform/platformQuickActionRuntime';
import {
  buildQuickActionDefinitions,
  type QuickActionName,
} from '@/components/platform/platformQuickActions';

const tm = (key: string) => key;
const definitions = buildQuickActionDefinitions(tm);

describe('platformQuickActionRuntime', () => {
  it('creates initial form values from field defaults', () => {
    expect(createInitialQuickActionForm('', definitions)).toEqual({});
    expect(createInitialQuickActionForm('send_like', definitions)).toEqual({
      user_id: '',
      times: 1,
    });
  });

  it('builds payload objects and normalizes string lists', () => {
    const payload = buildQuickActionPayload(
      'kick_group_members',
      {
        group_id: '654321',
        user_ids: '10001,\n10002',
        reject_add_request: true,
      },
      definitions,
      tm,
    );

    expect(payload).toEqual({
      group_id: '654321',
      user_ids: ['10001', '10002'],
      reject_add_request: true,
    });
  });

  it('rejects invalid number inputs with a field-specific message', () => {
    const actionName: QuickActionName = 'send_like';
    expect(() =>
      buildQuickActionPayload(
        actionName,
        {
          user_id: '445566',
          times: 'oops' as unknown as number,
        },
        definitions,
        tm,
      ),
    ).toThrow('quickActions.fields.times: quickActions.validation.number');
  });

  it('parses result text and extracts summary chips', () => {
    expect(tryParseJsonRecord('')).toBeNull();
    expect(tryParseJsonRecord('{')).toBeNull();

    const summary = buildQuickActionResultSummary(
      JSON.stringify({
        status: 'ok',
        retcode: 0,
        wording: 'done',
        data: {
          message_id: '12345',
        },
      }),
      tm,
    );

    expect(summary).toEqual([
      { label: 'quickActions.summary.status', value: 'ok' },
      { label: 'quickActions.summary.retcode', value: '0' },
      { label: 'quickActions.summary.message', value: 'done' },
      { label: 'message_id', value: '12345' },
    ]);
  });

  it('rejects arrays, skips blank numbers, and returns no summary for invalid JSON', () => {
    expect(tryParseJsonRecord('[1]')).toBeNull();
    expect(buildQuickActionResultSummary('not-json', tm)).toEqual([]);
    expect(
      buildQuickActionPayload(
        'send_like',
        { user_id: '1', times: '   ' },
        definitions,
        tm,
      ),
    ).toEqual({ user_id: '1' });
  });
});
