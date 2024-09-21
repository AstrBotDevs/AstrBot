
import aiohttp
import pytest

BASE_URL = "http://0.0.0.0:6185/api"

async def get_url(url):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            return await response.json()
        
async def post_url(url, data):
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=data) as response:
            return await response.json()

class TestHTTPServer:
    @pytest.mark.asyncio
    async def test_config(self):
        configs = await get_url(f"{BASE_URL}/configs")
        assert 'data' in configs and 'metadata' in configs['data'] \
            and 'config' in configs['data']
        config = configs['data']['config']
        # test post config
        await post_url(f"{BASE_URL}/astrbot-configs", config)
        # text post config with invalid data
        assert 'rate_limit' in config['platform_settings']
        config['platform_settings']['rate_limit'] = "invalid"
        ret = await post_url(f"{BASE_URL}/astrbot-configs", config)
        assert 'status' in ret and ret['status'] == 'error'
    
    @pytest.mark.asyncio
    async def test_update(self):
        await get_url(f"{BASE_URL}/check_update")
    
    @pytest.mark.asyncio
    async def test_plugins(self):
        pname = "astrbot_plugin_bilibili"
        url = f"https://github.com/Soulter/{pname}"

        await get_url(f"{BASE_URL}/extensions")

        # test install plugin
        await post_url(f"{BASE_URL}/extensions/install", {
            "url": url
        })
        
        # test uninstall plugin
        await post_url(f"{BASE_URL}/extensions/uninstall", {
            "name": pname
        })