import sys
from types import ModuleType
import asyncio
from pyppeteer import launch


async def template_to_pic(template_path, template_name, templates, pages, wait, type, quality, device_scale_factor):
    browser = await launch()
    page = await browser.newPage()
    await page.setViewport(pages["viewport"])
    await page.goto(pages["base_url"])
    await asyncio.sleep(wait)
    await page.evaluate('''(templates) => {
        // 在页面中执行 JavaScript 代码，将数据注入到模板中
        // 这里的示例代码仅供参考，具体需要根据实际情况修改
        document.getElementById('css').innerText = templates.css;
        document.getElementById('data').innerText = JSON.stringify(templates.data);
        document.getElementById('detail').innerText = templates.detail;
    }''', templates)
    screenshot = await page.screenshot({
        'type': type,
        'quality': quality,
        'deviceScaleFactor': device_scale_factor
    })
    await browser.close()
    return screenshot

def require(module_str: str):
    module = ModuleType(module_str)
    sys.modules[module_str] = module
    if module_str == 'nonebot_plugin_htmlrender':
        module.template_to_pic = template_to_pic
