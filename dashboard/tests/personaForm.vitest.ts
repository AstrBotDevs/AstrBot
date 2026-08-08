import { beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises } from '@vue/test-utils';
import PersonaForm from '@/components/shared/PersonaForm.vue';
import { mountWithVuetify } from './utils/mountWithVuetify';

const testState = vi.hoisted(() => ({
  mcpListMock: vi.fn(),
  personaCreateMock: vi.fn(),
  personaDeleteMock: vi.fn(),
  personaListMock: vi.fn(),
  personaUpdateMock: vi.fn(),
  skillListMock: vi.fn(),
  toolListMock: vi.fn(),
  askForConfirmationMock: vi.fn(),
}));

vi.mock('@/api/v1', () => ({
  mcpApi: {
    list: testState.mcpListMock,
  },
  personaApi: {
    create: testState.personaCreateMock,
    delete: testState.personaDeleteMock,
    list: testState.personaListMock,
    update: testState.personaUpdateMock,
  },
  skillApi: {
    list: testState.skillListMock,
  },
  toolApi: {
    list: testState.toolListMock,
  },
}));

vi.mock('@/utils/confirmDialog', () => ({
  askForConfirmation: testState.askForConfirmationMock,
  useConfirmDialog: () => undefined,
}));

describe('PersonaForm', () => {
  beforeEach(() => {
    testState.mcpListMock.mockResolvedValue({
      data: {
        status: 'ok',
        data: [
          { name: 'server-a', tools: ['tool.alpha', 'tool.beta'] },
          { name: 'server-empty', tools: [] },
        ],
      },
    });
    testState.toolListMock.mockResolvedValue({
      data: {
        status: 'ok',
        data: [
          {
            name: 'tool.alpha',
            description: 'Alpha tool',
            mcp_server_name: 'server-a',
          },
          {
            name: 'tool.beta',
            description: 'Beta tool',
            mcp_server_name: 'server-a',
          },
        ],
      },
    });
    testState.skillListMock.mockResolvedValue({
      data: {
        status: 'ok',
        data: {
          skills: [
            {
              name: 'skill.one',
              description: 'First skill',
              active: true,
            },
          ],
        },
      },
    });
    testState.personaListMock.mockResolvedValue({
      data: {
        status: 'ok',
        data: [],
      },
    });
    testState.personaCreateMock.mockResolvedValue({
      data: {
        status: 'ok',
        message: 'Saved',
      },
    });
    testState.personaUpdateMock.mockResolvedValue({
      data: {
        status: 'ok',
        message: 'Updated',
      },
    });
    testState.personaDeleteMock.mockResolvedValue({
      data: {
        status: 'ok',
        message: 'Deleted',
      },
    });
    testState.askForConfirmationMock.mockResolvedValue(true);
  });

  it('renders MCP quick select chips and applies server tools', async () => {
    const wrapper = mountWithVuetify(PersonaForm, {
      props: {
        modelValue: false,
        editingPersona: {
          persona_id: 'helper',
          system_prompt: 'This is a sufficiently long system prompt.',
          custom_error_message: '',
          begin_dialogs: [],
          tools: [],
          skills: [],
          folder_id: null,
        },
      },
      global: {
        stubs: {
          VDialog: {
            props: ['modelValue'],
            template: '<div class="v-dialog-stub"><slot /></div>',
          },
        },
      },
    });

    await wrapper.setProps({ modelValue: true });
    await flushPromises();

    expect(wrapper.text()).toContain('MCP Servers Quick Select');
    expect(wrapper.text()).toContain('server-a');
    expect(wrapper.text()).toContain('No tools selected');

    const serverChip = wrapper
      .findAll('.v-chip')
      .find((chip) => chip.text().includes('server-a'));

    expect(serverChip).toBeDefined();

    await serverChip!.trigger('click');
    await flushPromises();

    expect(wrapper.text()).not.toContain('No tools selected');
    expect(wrapper.text()).toContain('tool.alpha');
    expect(wrapper.text()).toContain('tool.beta');
  });

  it('keeps disabled plugin skills in an existing persona without offering them again', async () => {
    testState.skillListMock.mockResolvedValue({
      data: {
        status: 'ok',
        data: {
          skills: [
            {
              name: 'disabled-plugin-skill',
              description: 'Installed by a disabled plugin',
              active: true,
              source_type: 'plugin',
              plugin_active: false,
            },
            {
              name: 'available-skill',
              description: 'Available local skill',
              active: true,
            },
          ],
        },
      },
    });
    const wrapper = mountWithVuetify(PersonaForm, {
      props: {
        modelValue: false,
        editingPersona: {
          persona_id: 'helper',
          system_prompt: 'This is a sufficiently long system prompt.',
          custom_error_message: '',
          begin_dialogs: [],
          tools: [],
          skills: ['disabled-plugin-skill'],
          folder_id: null,
        },
      },
      global: {
        stubs: {
          VDialog: {
            props: ['modelValue'],
            template: '<div class="v-dialog-stub"><slot /></div>',
          },
        },
      },
    });

    await wrapper.setProps({ modelValue: true });
    await flushPromises();

    expect(wrapper.text()).toContain('disabled-plugin-skill');
    expect(wrapper.text()).toContain('available-skill');
    expect(wrapper.find('.skills-selection').text()).not.toContain(
      'disabled-plugin-skill',
    );

    const saveButton = wrapper
      .findAll('button')
      .find((button) => button.text().trim() === 'Save');
    expect(saveButton).toBeDefined();
    await saveButton!.trigger('click');
    await flushPromises();

    expect(testState.personaUpdateMock).toHaveBeenCalledWith(
      'helper',
      expect.objectContaining({
        skills: ['disabled-plugin-skill'],
      }),
    );
  });
});
