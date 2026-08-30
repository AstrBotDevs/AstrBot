import { describe, expect, it, vi } from 'vitest';
import { flushPromises } from '@vue/test-utils';
import ThemeAwareMarkdownCodeBlock from '@/components/shared/ThemeAwareMarkdownCodeBlock.vue';
import { mountWithVuetify } from './utils/mountWithVuetify';

vi.mock('markstream-vue', () => ({
  CodeBlockNode: {
    props: ['node', 'isDark'],
    template: '<pre class="code-block-stub">{{ node.language }}</pre>',
  },
}));

describe('ThemeAwareMarkdownCodeBlock fence language', () => {
  it('holds highlight until a prefix language is settled', async () => {
    const wrapper = mountWithVuetify(ThemeAwareMarkdownCodeBlock, {
      props: {
        node: {
          type: 'code_block',
          language: 'c',
          code: '',
          raw: '',
          loading: true,
        },
      },
    });
    await flushPromises();
    expect(wrapper.get('.code-block-stub').text()).toBe('text');

    await wrapper.setProps({
      node: {
        type: 'code_block',
        language: 'cpp',
        code: '',
        raw: '',
        loading: true,
      },
    });
    await flushPromises();
    expect(wrapper.get('.code-block-stub').text()).toBe('cpp');

    await wrapper.setProps({
      node: {
        type: 'code_block',
        language: 'c',
        code: 'int main() { return 0; }\n',
        raw: 'int main() { return 0; }\n',
        loading: true,
      },
    });
    await flushPromises();
    expect(wrapper.get('.code-block-stub').text()).toBe('c');
  });
});
