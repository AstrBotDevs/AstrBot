import { describe, expect, it } from 'vitest';
import {
  buildSuggestionSignature,
  rankSuggestionCommands,
  type SuggestionCommand,
} from '@/components/chat/commandSuggestion';

function normalizeText(value: string) {
  return value.trim().toLowerCase();
}

function makeCommand(
  effective_command: string,
  overrides: Partial<SuggestionCommand> = {},
): SuggestionCommand {
  return {
    handler_full_name: effective_command,
    effective_command,
    display_signature: effective_command,
    description: '',
    plugin_display_name: null,
    enabled: true,
    reserved: false,
    ...overrides,
  };
}

describe('commandSuggestion', () => {
  it('builds alias display signatures from the source command signature', () => {
    expect(
      buildSuggestionSignature(
        '/mp',
        'music play (name(str),force(bool)=False)',
        'music play',
      ),
    ).toBe('/mp (name(str),force(bool)=False)');
    expect(buildSuggestionSignature('/mp', '', '/mp')).toBe('/mp');
    expect(buildSuggestionSignature('/mp', '/mp', '/mp')).toBe('/mp');
    expect(buildSuggestionSignature('/mp', '/other', '/mp')).toBe('/other');
  });

  it('ranks exact matches first, then reserved commands, then shorter signatures', () => {
    const commands: SuggestionCommand[] = [
      makeCommand('/help', { reserved: true, display_signature: '/help' }),
      makeCommand('/helpful', {
        reserved: true,
        display_signature: '/helpful (target(str))',
      }),
      makeCommand('/helpful-extended', {
        reserved: true,
        display_signature: '/helpful-extended (target(str),force(bool)=False)',
      }),
      makeCommand('/helpdesk', {
        reserved: false,
        display_signature: '/helpdesk (target(str))',
      }),
      makeCommand('/tool inspect', {
        plugin_display_name: 'Helper Tools',
        display_signature: '/tool inspect (name(str))',
      }),
      makeCommand('/alpha', {
        description: 'Help workflow bootstrap',
        display_signature: '/alpha (mode(str))',
      }),
    ];

    expect(
      rankSuggestionCommands(commands, '/help', normalizeText).map(
        (command) => command.effective_command,
      ),
    ).toEqual(['/help', '/helpful', '/helpful-extended', '/helpdesk']);
  });

  it('uses the same signature-first ordering when the query is empty', () => {
    const commands: SuggestionCommand[] = [
      makeCommand('/alpha', {
        reserved: true,
        display_signature: '/alpha (mode(str),force(bool)=False)',
      }),
      makeCommand('/beta-tool', {
        reserved: true,
        display_signature: '/beta-tool',
      }),
      makeCommand('/gamma', {
        reserved: false,
        display_signature: '/gamma',
      }),
    ];

    expect(
      rankSuggestionCommands(commands, '', normalizeText).map(
        (command) => command.effective_command,
      ),
    ).toEqual(['/beta-tool', '/alpha', '/gamma']);
  });

  it('falls back to plugin name and description matches after command matches', () => {
    const commands: SuggestionCommand[] = [
      makeCommand('/tool inspect', {
        plugin_display_name: 'Helper Tools',
        display_signature: '/tool inspect (name(str))',
      }),
      makeCommand('/alpha', {
        description: 'Help workflow bootstrap',
        display_signature: '/alpha (mode(str))',
      }),
    ];

    expect(
      rankSuggestionCommands(commands, 'helper', normalizeText).map(
        (command) => command.effective_command,
      ),
    ).toEqual(['/tool inspect']);

    expect(
      rankSuggestionCommands(commands, 'workflow', normalizeText).map(
        (command) => command.effective_command,
      ),
    ).toEqual(['/alpha']);

    expect(
      rankSuggestionCommands(
        [
          makeCommand('/zzz', {
            plugin_display_name: 'My Helper Pack',
            description: '',
          }),
        ],
        'helper',
        normalizeText,
      ).map((command) => command.effective_command),
    ).toEqual(['/zzz']);
  });

  it('breaks remaining ties by command length then lexicographic order', () => {
    const emptyQuery = [
      makeCommand('/ab', {
        reserved: true,
        display_signature: '/x',
      }),
      makeCommand('/aa', {
        reserved: true,
        display_signature: '/x',
      }),
      makeCommand('/b', {
        reserved: true,
        display_signature: '/x',
      }),
    ];
    expect(
      rankSuggestionCommands(emptyQuery, '', normalizeText).map(
        (command) => command.effective_command,
      ),
    ).toEqual(['/b', '/aa', '/ab']);

    expect(
      rankSuggestionCommands(
        [
          makeCommand('/long-name', {
            reserved: true,
            display_signature: '',
          }),
          makeCommand('/z', { reserved: true, display_signature: '' }),
        ],
        '',
        normalizeText,
      ).map((command) => command.effective_command),
    ).toEqual(['/z', '/long-name']);

    const ranked = [
      makeCommand('/help-b', {
        reserved: true,
        display_signature: '/help',
      }),
      makeCommand('/help-a', {
        reserved: true,
        display_signature: '/help',
      }),
      makeCommand('/h', {
        reserved: true,
        display_signature: '/help',
      }),
    ];
    expect(
      rankSuggestionCommands(ranked, 'h', normalizeText).map(
        (command) => command.effective_command,
      ),
    ).toEqual(['/h', '/help-a', '/help-b']);
  });
});
