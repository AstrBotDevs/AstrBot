import contextlib

import pytest
from aiohttp import web

from astrbot.dashboard.services.plugin_service import PluginService, RegistrySource


@contextlib.asynccontextmanager
async def serve(handler):
    app = web.Application()
    app.router.add_get("/plugins", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    host, port = runner.addresses[0]
    try:
        yield f"http://{host}:{port}/plugins"
    finally:
        await runner.cleanup()


def make_service(urls, cache_file):
    service = PluginService(None, None)
    service.build_registry_source = lambda custom_url: RegistrySource(
        urls=urls,
        cache_file=str(cache_file),
        md5_url=None,
    )
    return service


@pytest.mark.asyncio
async def test_fallback_source_used_after_primary_fails(tmp_path):
    hits = {"primary": 0, "fallback": 0}
    plugins = {
        "plugin-a": {"name": "plugin-a", "desc": "A"},
        "plugin-b": {"name": "plugin-b", "desc": "B"},
    }

    async def primary(request):
        hits["primary"] += 1
        return web.Response(status=500)

    async def fallback(request):
        hits["fallback"] += 1
        return web.json_response(plugins)

    async with serve(primary) as primary_url, serve(fallback) as fallback_url:
        service = make_service([primary_url, fallback_url], tmp_path / "plugins.json")
        data, warning = await service.get_online_plugins(
            custom_registry=None,
            force_refresh=True,
        )

    assert warning is None
    assert data == plugins
    assert hits == {"primary": 1, "fallback": 1}


@pytest.mark.asyncio
async def test_primary_source_served_directly(tmp_path):
    hits = {"primary": 0, "fallback": 0}
    plugins = {"plugin-a": {"name": "plugin-a", "desc": "A"}}

    async def primary(request):
        hits["primary"] += 1
        return web.json_response(plugins)

    async def fallback(request):
        hits["fallback"] += 1
        return web.json_response({})

    async with serve(primary) as primary_url, serve(fallback) as fallback_url:
        service = make_service([primary_url, fallback_url], tmp_path / "plugins.json")
        data, warning = await service.get_online_plugins(
            custom_registry=None,
            force_refresh=True,
        )

    assert warning is None
    assert data == plugins
    assert hits == {"primary": 1, "fallback": 0}
