import aiohttp, os
from util.general_utils import download_image_by_url, create_markdown_image
from type.config import VERSION

BASE_RENDER_URL = "https://t2i.soulter.top/text2img"
TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "template")

async def text_to_image_base(text: str, return_url: bool = False) -> str:
    '''
    返回图像的文件路径
    '''
    with open(os.path.join(TEMPLATE_PATH, "base.html"), "r") as f:
        tmpl_str = f.read()

    assert(tmpl_str)

    text = text.replace("`", "\`")

    post_data = {
        "tmpl": tmpl_str,
        "json": return_url,
        "tmpldata": {
            "text": text,
            "version": f"v{VERSION}",
        },
        "options": {
            "full_page": True
        }
    }
    
    if return_url:
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{BASE_RENDER_URL}/generate", json=post_data) as resp:
                ret = await resp.json()
                return f"{BASE_RENDER_URL}/{ret['data']['id']}"
    else:
        image_path = ""
        try:
            image_path = await download_image_by_url(f"{BASE_RENDER_URL}/generate", post=True, post_data=post_data)
        except Exception as e:
            print(f"调用 markdown 渲染 API 失败，错误信息：{e}，将使用本地渲染方式。")
            image_path = create_markdown_image(text)
        return image_path