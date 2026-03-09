
# 文转图

> [!TIP]
> 为了方便开发，您可以使用 [AstrBot Text2Image Playground](https://t2i-playground.astrbot.app/) 在线可视化编辑和测试 HTML 模板。

## 基本

AstrBot 支持将文字渲染成图片。

```python
@filter.command("image") # 注册一个 /image 指令，接收 text 参数。
async def on_aiocqhttp(self, event: AstrMessageEvent, text: str):
    url = await self.text_to_image(text) # text_to_image() 是 Star 类的一个方法。
    # path = await self.text_to_image(text, return_url = False) # 如果你想保存图片到本地
    yield event.image_result(url)

```

![image](https://files.astrbot.app/docs/source/images/plugin/image-3.png)

## 自定义(基于 HTML)

如果你觉得上面渲染出来的图片不够美观，你可以使用自定义的 HTML 模板来渲染图片。

AstrBot 支持使用 `HTML + Jinja2` 的方式来渲染文转图模板。

```py{7}
# 自定义的 Jinja2 模板，支持 CSS
TMPL = '''
<div style="font-size: 32px;">
<h1 style="color: black">Todo List</h1>

<ul>
{% for item in items %}
    <li>{{ item }}</li>
{% endfor %}
</div>
'''

@filter.command("todo")
async def custom_t2i_tmpl(self, event: AstrMessageEvent):
    options = {} # 可选择传入渲染选项。
    url = await self.html_render(TMPL, {"items": ["吃饭", "睡觉", "玩原神"]}, options=options) # 第二个参数是 Jinja2 的渲染数据
    yield event.image_result(url)
```

返回的结果:

![image](https://files.astrbot.app/docs/source/images/plugin/fcc2dcb472a91b12899f617477adc5c7.png)

这只是一个简单的例子。得益于 HTML 和 DOM 渲染器的强大性，你可以进行更复杂和更美观的的设计。除此之外，Jinja2 支持循环、条件等语法以适应列表、字典等数据结构。你可以从网上了解更多关于 Jinja2 的知识。

**图片渲染选项(options)**：

请参考 Playwright 的 [screenshot](https://playwright.dev/python/docs/api/class-page#page-screenshot) API。

- `timeout` (float, optional): 截图超时时间.
- `type` (Literal["jpeg", "png"], optional): 截图图片类型.
- `quality` (int, optional): 截图质量，仅适用于 JPEG 格式图片.
- `omit_background` (bool, optional): 是否允许隐藏默认的白色背景，这样就可以截透明图了，仅适用于 PNG 格式
- `full_page` (bool, optional): 是否截整个页面而不是仅设置的视口大小，默认为 True.
- `clip` (dict, optional): 截图后裁切的区域。参考 Playwright screenshot API。
- `animations`: (Literal["allow", "disabled"], optional): 是否允许播放 CSS 动画.
- `caret`: (Literal["hide", "initial"], optional): 当设置为 hide 时，截图时将隐藏文本插入符号，默认为 hide.
- `scale`: (Literal["css", "device"], optional): 页面缩放设置. 当设置为 css 时，则将设备分辨率与 CSS 中的像素一一对应，在高分屏上会使得截图变小. 当设置为 device 时，则根据设备的屏幕缩放设置或当前 Playwright 的 Page/Context 中的 device_scale_factor 参数来缩放.
