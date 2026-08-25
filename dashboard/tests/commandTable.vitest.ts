import { describe, expect, it } from 'vitest';
import { flushPromises } from '@vue/test-utils';
import CommandTable from '@/components/extension/componentPanel/components/CommandTable.vue';
import type { CommandItem } from '@/domain/commands';
import { mountWithVuetify } from './utils/mountWithVuetify';

function makeCommand(overrides: Partial<CommandItem> = {}): CommandItem {
  return {
    command_id: 'demo:demo',
    handler_full_name: 'demo.demo',
    handler_name: 'demo',
    plugin: 'demo',
    plugin_display_name: 'Demo',
    module_path: 'data.plugins.demo.main',
    description: 'Demo command',
    type: 'command',
    parent_signature: '',
    parent_group_handler: '',
    original_command: 'demo',
    current_fragment: 'demo',
    effective_command: 'demo',
    signature: 'demo',
    display_signature: 'demo',
    aliases: [],
    action: null,
    enabled: true,
    plugin_activated: true,
    is_group: false,
    has_conflict: false,
    reserved: false,
    sub_commands: [],
    ...overrides,
  };
}

describe('CommandTable', () => {
  it('disables mutating actions when the owning plugin is inactive', async () => {
    const wrapper = mountWithVuetify(CommandTable, {
      props: {
        items: [makeCommand({ plugin_activated: false })],
        expandedGroups: new Set<string>(),
      },
    });
    await flushPromises();

    expect(wrapper.text()).toContain('Plugin off');
    const disabledButtons = wrapper
      .findAllComponents({ name: 'VBtn' })
      .filter((button) => button.props('disabled') === true);
    expect(disabledButtons.length).toBeGreaterThanOrEqual(2);
  });
});
