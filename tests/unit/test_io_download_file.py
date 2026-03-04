from aiohttp import web
import pytest

from astrbot.core.utils.io import download_file


@pytest.mark.asyncio
async def test_download_file_downloads_content(tmp_path):
    payload = b"astrbot-download-payload" * 256

    async def handle(_request):
        return web.Response(body=payload)

    app = web.Application()
    app.router.add_get("/file.bin", handle)
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()

    try:
        sockets = site._server.sockets  # noqa: SLF001
        assert sockets
        port = sockets[0].getsockname()[1]
        url = f"http://127.0.0.1:{port}/file.bin"

        out = tmp_path / "downloaded.bin"
        await download_file(url, str(out))

        assert out.read_bytes() == payload
    finally:
        await runner.cleanup()
