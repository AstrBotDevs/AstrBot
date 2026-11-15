from types import SimpleNamespace
import pytest
from astrbot.core.platform.sources.discord import discord_platform_adapter as module
from astrbot.core.star.filter.command import CommandFilter

@pytest.mark.parametrize('guild_id', [None, 123])
def test_duplicate_names_preserve_first_priority_handler(monkeypatch, guild_id):
    payloads=[]
    class Client:
        def add_application_command(self, command):
            # Pycord resolves inherited global contexts when the client queues a command.
            if command.contexts is None:
                command.contexts = {module.discord.InteractionContextType.guild}
            if command.integration_types is None:
                command.integration_types = {module.discord.IntegrationType.guild_install}
            payloads.append(command.to_dict())
        async def sync_commands(self):
            assert len({row['name'] for row in payloads}) == len(payloads)
    handlers=[]
    for owner,name,description in [('high','reset','High priority'),('low','reset','Low priority'),('third','stats','Stats')]:
        handlers.append(SimpleNamespace(handler_module_path=owner,enabled=True,desc=description,event_filters=[CommandFilter(name,None,None)]))
    monkeypatch.setattr(module,'star_handlers_registry',handlers)
    monkeypatch.setattr(module,'star_map',{h.handler_module_path:SimpleNamespace(activated=True) for h in handlers})
    adapter=object.__new__(module.DiscordPlatformAdapter)
    adapter.client=Client();adapter.guild_id=guild_id
    import asyncio
    asyncio.run(adapter._collect_and_register_commands())
    assert [row['name'] for row in payloads] == ['reset','stats']
    assert payloads[0]['description'] == 'High priority'
