import { flushPromises } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import LongTermMemoryPage from '@/views/alkaid/LongTermMemoryPage.vue';
import { mountWithVuetify } from './utils/mountWithVuetify';

const apiMocks = vi.hoisted(() => ({
  facts: vi.fn(),
  fact: vi.fn(),
  deleteFact: vi.fn(),
  restoreFact: vi.fn(),
  profiles: vi.fn(),
  refreshProfile: vi.fn(),
  operations: vi.fn(),
  stats: vi.fn(),
}));

vi.mock('@/api/v1', () => ({
  memoryApi: apiMocks,
}));

describe('LongTermMemoryPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMocks.facts.mockResolvedValue({
      data: {
        data: {
          items: [
            {
              id: 7,
              person_id: 'user-a',
              chat_id: 'telegram:GroupMessage:g1',
              scope_id: 'isolated:telegram:GroupMessage:g1',
              fact_text: '用户喜欢猫娘。',
              fact_type: 'preference',
              confidence: 0.64,
              status: 'active',
              updated_at: '2026-07-07T00:00:00Z',
            },
          ],
          total: 1,
          page: 1,
          page_size: 10,
        },
      },
    });
    apiMocks.fact.mockResolvedValue({
      data: {
        data: {
          fact: { id: 7, fact_text: '用户喜欢猫娘。', status: 'active' },
          operation_logs: [],
        },
      },
    });
    apiMocks.deleteFact.mockResolvedValue({ data: { data: {} } });
    apiMocks.restoreFact.mockResolvedValue({ data: { data: {} } });
    apiMocks.profiles.mockResolvedValue({
      data: {
        data: {
          items: [
            {
              id: 1,
              person_id: 'user-a',
              chat_scope: 'isolated:telegram:GroupMessage:g1',
              profile_text: 'Known user profile in this isolated chat',
              source_version: 1,
              is_override: false,
            },
          ],
        },
      },
    });
    apiMocks.operations.mockResolvedValue({
      data: {
        data: {
          items: [
            {
              id: 1,
              operation_id: 'op-1',
              operator: 'dashboard',
              target_type: 'memory_fact',
              target_id: '7',
              action: 'create',
              created_at: '2026-07-07T00:00:00Z',
            },
          ],
        },
      },
    });
    apiMocks.stats.mockResolvedValue({
      data: {
        data: {
          facts: 1,
          deleted_facts: 0,
          profiles: 1,
          worker: { running: true, queue_size: 0, queue_max_size: 256 },
        },
      },
    });
  });

  it('loads memory facts and can submit a delete action', async () => {
    const wrapper = mountWithVuetify(LongTermMemoryPage);
    await flushPromises();

    expect(apiMocks.facts).toHaveBeenCalled();
    expect(apiMocks.facts).toHaveBeenCalledWith(
      expect.objectContaining({ status: 'all' }),
    );
    expect(wrapper.text()).toContain('用户喜欢猫娘。');
    expect(wrapper.text()).toContain('Active');

    await wrapper.find('button[aria-label="Delete"]').trigger('click');
    await flushPromises();

    const buttons = Array.from(
      document.body.querySelectorAll('.v-overlay__content button'),
    );
    const deleteButton = buttons.find(
      (button) => button.textContent?.trim() === 'Delete',
    );
    expect(deleteButton).toBeTruthy();
    deleteButton!.click();
    await flushPromises();

    expect(apiMocks.deleteFact).toHaveBeenCalledWith(7, undefined);
  });

  it('submits all fact filters from the visible filter action', async () => {
    const wrapper = mountWithVuetify(LongTermMemoryPage);
    await flushPromises();

    await wrapper
      .get('[data-testid="memory-person-filter"] input')
      .setValue('person-42');
    await wrapper
      .get('[data-testid="memory-chat-filter"] input')
      .setValue('chat-7');
    await wrapper
      .get('[data-testid="memory-query-filter"] input')
      .setValue('deployment');
    await wrapper.get('[data-testid="memory-filter-submit"]').trigger('click');
    await flushPromises();

    expect(apiMocks.facts).toHaveBeenLastCalledWith({
      page: 1,
      page_size: 10,
      status: 'all',
      person_id: 'person-42',
      chat_id: 'chat-7',
      query: 'deployment',
    });
  });
});
